"""What ingestion and querying share: configuration, the embedding, the Chroma
collection and the audit log.

Ingestion and querying must embed with exactly the same function, which is why
it lives here rather than in either of them.
"""

import hashlib
import json
import math
import re
import threading
import time
import tomllib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import chromadb

# rag/, not rag/pipeline/: config, service files and data all live at the top.
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.toml"
SERVICES_DIR = BASE_DIR / "services"
AUDIT_PATH = BASE_DIR / "rag-audit.jsonl"


# ---------------------------------------------------------------- configuration


@dataclass(frozen=True)
class Source:
    entity: str
    label: str
    path: str
    id_field: str
    title: str
    detail: str | None = None
    # Query string for the list request. A list value makes one request per
    # item, for APIs that only return one user's (or one thing's) rows at a time.
    params: dict[str, Any] = field(default_factory=dict)
    # Names for the values of an API that returns rows as arrays, not objects.
    columns: list[str] | None = None
    # Keys to keep, in display order, applied at every nesting depth.
    fields: list[str] | None = None


@dataclass(frozen=True)
class Service:
    name: str
    base_url: str
    sources: list[Source]


@cache
def settings() -> dict[str, Any]:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@cache
def services() -> dict[str, Service]:
    """Every service in services/*.toml, keyed by name. Read once per process."""
    loaded: dict[str, Service] = {}
    for path in sorted(SERVICES_DIR.glob("*.toml")):
        with path.open("rb") as f:
            raw = tomllib.load(f)
        service = Service(
            name=raw["name"],
            base_url=raw["base_url"].rstrip("/"),
            sources=[Source(**source) for source in raw.get("sources", [])],
        )
        if service.name in loaded:
            raise ValueError(f"Duplicate service name {service.name!r} in {path.name}")
        loaded[service.name] = service
    return loaded


# -------------------------------------------------------------------- embedding
#
# Feature hashing: each token is hashed to one signed dimension. Deterministic
# and dependency free, so ingestion and querying always agree as long as
# `dimensions` and the tokeniser are unchanged. It matches on shared words
# rather than meaning, so "exam" will not find "assessment".

TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

# Words that appear in almost every question and record and would otherwise
# pull every chunk towards every query.
STOPWORDS = frozenset(
    """
    a an and are as at be by can do does for from has have how i in is it its
    me my of on or that the their there these this to was what when where which
    who why will with you your
    """.split()
)


def tokenise(text: str) -> list[str]:
    return [t for t in TOKEN_PATTERN.findall((text or "").lower()) if t not in STOPWORDS]


def embed_texts(texts: list[str]) -> list[list[float]]:
    dimensions = settings()["embedding"]["dimensions"]
    return [_embed(text, dimensions) for text in texts]


def _embed(text: str, dimensions: int) -> list[float]:
    values = [0.0] * dimensions
    for token in tokenise(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        # A second hash bit picks the sign so collisions cancel out on average
        # instead of always inflating similarity.
        values[index] += 1.0 if digest[4] & 1 else -1.0

    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return values
    return [v / norm for v in values]


# ------------------------------------------------------------------ vector store

_lock = threading.Lock()
_collection = None


def embedding_signature() -> str:
    embedding = settings()["embedding"]
    return f"{embedding['version']}-{embedding['dimensions']}"


def get_collection():
    """The shared collection, recreated empty if it was built with another embedding."""
    global _collection
    with _lock:
        if _collection is not None:
            return _collection

        chroma = settings()["chroma"]
        client = chromadb.PersistentClient(path=str(resolve_path(chroma["path"])))
        metadata = {"hnsw:space": "cosine", "embedding": embedding_signature()}
        collection = client.get_or_create_collection(name=chroma["collection"], metadata=metadata)

        # Vectors from a different embedding are meaningless to the current
        # one, so they are dropped rather than silently mixed in.
        if (collection.metadata or {}).get("embedding") != embedding_signature():
            client.delete_collection(name=chroma["collection"])
            collection = client.create_collection(name=chroma["collection"], metadata=metadata)

        _collection = collection
        return _collection


# -------------------------------------------------------------------- audit log


def append_audit(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any],
    outcome: str,
    start_time: float,
) -> None:
    record = {
        "request_id": str(uuid.uuid4()),
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output": tool_output,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": int((time.time() - start_time) * 1000),
        "outcome": outcome,
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
