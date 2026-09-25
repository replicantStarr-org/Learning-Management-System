"""Pulls records from each service's database API and indexes them in Chroma.

Services are only ever read through their HTTP API, never their SQLite file:
the files live in Docker volumes and design.md forbids direct querying.
"""

from datetime import datetime, timezone
from typing import Any

import requests

from config import Service, Source, services, settings
from embedding import embed_texts
from store import get_collection

REQUEST_TIMEOUT_SECONDS = 10


def ingest(service_name: str | None = None) -> dict[str, Any]:
    """Re-index one service, or every configured service when no name is given."""
    configured = services()
    if service_name is not None and service_name not in configured:
        return {
            "status": "error",
            "error": f"unknown service {service_name!r}",
            "available": sorted(configured),
        }

    targets = [configured[service_name]] if service_name else list(configured.values())
    results = [ingest_service(service) for service in targets]
    failed = sum(1 for r in results if r["status"] != "success")
    if failed == 0:
        status = "success"
    elif failed == len(results):
        status = "error"
    else:
        status = "partial"
    return {"status": status, "services": results}


def ingest_service(service: Service) -> dict[str, Any]:
    # Everything is fetched before the collection is touched, so an unreachable
    # service keeps its previous chunks instead of being emptied.
    try:
        chunks = [chunk for source in service.sources for chunk in load_source(service, source)]
    except requests.RequestException as exc:
        return {"service": service.name, "status": "error", "error": f"fetch failed: {exc}"}
    except (KeyError, ValueError) as exc:
        return {"service": service.name, "status": "error", "error": f"bad response or config: {exc}"}

    collection = get_collection()
    existing = set(collection.get(where={"service": service.name}, include=[])["ids"])
    new_ids = [c["id"] for c in chunks]

    if chunks:
        collection.upsert(
            ids=new_ids,
            documents=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
            embeddings=embed_texts([c["text"] for c in chunks]),
        )
    stale = sorted(existing - set(new_ids))
    if stale:
        collection.delete(ids=stale)

    return {
        "service": service.name,
        "status": "success",
        "chunk_count": len(chunks),
        "removed_count": len(stale),
    }


def load_source(service: Service, source: Source) -> list[dict[str, Any]]:
    records = fetch_json(service.base_url + source.path, source.params)
    if not isinstance(records, list):
        raise ValueError(f"{source.path} did not return a JSON list")

    indexed_at = datetime.now(timezone.utc).isoformat()
    chunks = []
    for record in records:
        if source.detail:
            record = fetch_json(service.base_url + source.detail.format_map(record))
        chunks.extend(record_chunks(service, source, record, indexed_at))
    return chunks


def fetch_json(url: str, params: dict[str, Any] | None = None) -> Any:
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def record_chunks(
    service: Service, source: Source, record: dict[str, Any], indexed_at: str
) -> list[dict[str, Any]]:
    record_id = str(record[source.id_field])
    title = source.title.format_map(record)
    header = f"{source.label}: {title}"

    blocks = render(record, source.fields)

    chunks = []
    for index, body in enumerate(group_blocks(blocks, settings()["chunking"]["max_words"])):
        chunks.append(
            {
                "id": f"{service.name}:{source.entity}:{record_id}:{index}",
                "text": header + "\n" + "\n".join(body),
                "metadata": {
                    "service": service.name,
                    "entity": source.entity,
                    "record_id": record_id,
                    "title": title,
                    "indexed_at": indexed_at,
                },
            }
        )
    return chunks


def select(record: dict[str, Any], fields: list[str] | None) -> dict[str, Any]:
    """Keep only the listed keys, in the listed order. None keeps everything."""
    if fields is None:
        return record
    return {key: record[key] for key in fields if key in record}


def render(record: dict[str, Any], fields: list[str] | None, depth: int = 0) -> list[list[str]]:
    """Turn a JSON record into blocks of `key: value` lines.

    Each top-level field is one block, and so is each item of a list of
    objects, so chunking can split between quiz questions but never inside one.
    """
    pad = "  " * depth
    blocks: list[list[str]] = []
    for key, value in select(record, fields).items():
        if value is None or value == "" or value == []:
            continue
        label = key.replace("_", " ")

        if isinstance(value, dict):
            blocks.append([f"{pad}{label}:", *flatten(render(value, fields, depth + 1))])
        elif isinstance(value, list) and all(isinstance(v, dict) for v in value):
            items = [select(item, fields) for item in value]
            # Objects reduced to a single field, like tags, read better inline.
            if all(len(item) == 1 for item in items):
                blocks.append([f"{pad}{label}: " + ", ".join(str(*item.values()) for item in items)])
                continue
            item_blocks = []
            for item in items:
                lines = flatten(render(item, fields, depth + 1))
                if lines:
                    lines[0] = f"{pad}- " + lines[0].lstrip()
                    item_blocks.append(lines)
            if item_blocks:
                item_blocks[0].insert(0, f"{pad}{label}:")
            blocks.extend(item_blocks)
        elif isinstance(value, list):
            blocks.append([f"{pad}{label}: " + ", ".join(str(v) for v in value)])
        else:
            blocks.append([f"{pad}{label}: {value}"])
    return blocks


def flatten(blocks: list[list[str]]) -> list[str]:
    return [line for block in blocks for line in block]


def group_blocks(blocks: list[list[str]], max_words: int) -> list[list[str]]:
    """Pack whole blocks into chunks of roughly max_words; a block is never split."""
    chunks: list[list[str]] = []
    current: list[str] = []
    count = 0
    for block in blocks:
        words = sum(len(line.split()) for line in block)
        if current and count + words > max_words:
            chunks.append(current)
            current, count = [], 0
        current.extend(block)
        count += words
    if current:
        chunks.append(current)
    return chunks
