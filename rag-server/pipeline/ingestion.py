"""Pulls records from each service's database API and indexes them in Chroma.

Services are only ever read through their HTTP API, never their SQLite file:
the files live in Docker volumes and design.md forbids direct querying. What to
read from each service is defined by its connector in pipeline/connectors/.
"""

import time
from datetime import datetime, timezone
from typing import Any

import requests

from .audit import append_audit
from .common import settings
from .connector import Connector, Record, connectors
from .vectors import embed_texts, get_collection


def ingest_services(service_name: str | None = None) -> dict[str, Any]:
    """Re-index one service, or every service when no name is given."""
    start = time.time()
    available = connectors()
    if service_name is not None and service_name not in available:
        return {
            "status": "error",
            "error": f"unknown service {service_name!r}",
            "available": sorted(available),
        }

    targets = [available[service_name]] if service_name else list(available.values())
    results = [ingest_service(connector) for connector in targets]
    # Unimplemented connectors are neither successes nor failures, so the
    # overall status only reflects the services that were actually attempted.
    attempted = [r for r in results if r["status"] != "skipped"]
    failed = sum(1 for r in attempted if r["status"] == "error")
    if not attempted:
        status = "skipped"
    elif failed == 0:
        status = "success"
    elif failed == len(attempted):
        status = "error"
    else:
        status = "partial"

    output = {"status": status, "services": results}
    append_audit("ingest", {"service": service_name}, output, status, start)
    return output


def ingest_service(connector: Connector) -> dict[str, Any]:
    # A connector with no entity functions is unimplemented, not empty; treating
    # it as zero records would delete everything previously indexed for it.
    if not connector.entities:
        return {"service": connector.name, "status": "skipped", "reason": "connector has no entity functions"}

    # Everything is fetched before the collection is touched, so an unreachable
    # service keeps its previous chunks instead of being emptied.
    indexed_at = datetime.now(timezone.utc).isoformat()
    try:
        chunks = [
            chunk for record in connector.records() for chunk in record_chunks(connector.name, record, indexed_at)
        ]
    except requests.RequestException as exc:
        return {"service": connector.name, "status": "error", "error": f"fetch failed: {exc}"}
    except Exception as exc:
        # Connectors are arbitrary code over someone else's API, so a renamed
        # column surfaces here as a KeyError; report it rather than crash.
        return {"service": connector.name, "status": "error", "error": f"connector failed: {exc!r}"}

    collection = get_collection()
    existing = set(collection.get(where={"service": connector.name}, include=[])["ids"])
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
        "service": connector.name,
        "status": "success",
        "chunk_count": len(chunks),
        "removed_count": len(stale),
    }


def record_chunks(service: str, record: Record, indexed_at: str) -> list[dict[str, Any]]:
    header = f"{record.label}: {record.title}"
    blocks = render(record.fields)

    chunks = []
    for index, body in enumerate(group_blocks(blocks, settings()["chunking"]["max_words"])):
        chunks.append(
            {
                "id": f"{service}:{record.entity}:{record.id}:{index}",
                "text": header + "\n" + "\n".join(body),
                "metadata": {
                    "service": service,
                    "entity": record.entity,
                    "record_id": str(record.id),
                    "title": record.title,
                    "indexed_at": indexed_at,
                },
            }
        )
    return chunks


def render(fields: dict[str, Any], depth: int = 0) -> list[list[str]]:
    """Turn a record's fields into blocks of `key: value` lines.

    Each top-level field is one block, and so is each item of a list of
    objects, so chunking can split between quiz questions but never inside one.
    """
    pad = "  " * depth
    blocks: list[list[str]] = []
    for key, value in fields.items():
        if value is None or value == "" or value == []:
            continue
        label = key.replace("_", " ")

        if isinstance(value, dict):
            blocks.append([f"{pad}{label}:", *flatten(render(value, depth + 1))])
        elif isinstance(value, list) and all(isinstance(v, dict) for v in value):
            item_blocks = []
            for item in value:
                lines = flatten(render(item, depth + 1))
                if lines:
                    lines[0] = f"{pad}- " + lines[0].lstrip()
                    item_blocks.append(lines)
            if item_blocks:
                item_blocks[0].insert(0, f"{pad}{label}:")
            blocks.extend(item_blocks)
        elif isinstance(value, list):
            # Semicolons, because the values themselves often contain commas.
            blocks.append([f"{pad}{label}: " + "; ".join(str(v) for v in value)])
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
