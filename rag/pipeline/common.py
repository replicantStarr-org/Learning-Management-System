"""What ingestion and querying share: settings, the connector framework, the
embedding, the Chroma collection and the audit log.

Ingestion and querying must embed with exactly the same function, which is why
it lives here rather than in either of them.
"""

import hashlib
import importlib
import json
import math
import pkgutil
import re
import threading
import time
import tomllib
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any

import chromadb
import requests

# rag/, not rag/pipeline/: config and data live at the top.
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.toml"
AUDIT_PATH = BASE_DIR / "rag-audit.jsonl"
CONNECTORS_PACKAGE = f"{__package__}.connectors"
REQUEST_TIMEOUT_SECONDS = 10


@cache
def settings() -> dict[str, Any]:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


# ------------------------------------------------------------------- connectors


@dataclass(frozen=True)
class Record:
    """One thing to index, e.g. one quiz. `fields` is rendered in its own order."""

    entity: str
    id: str | int
    title: str
    fields: dict[str, Any]

    @property
    def label(self) -> str:
        return self.entity.replace("_", " ").capitalize()


Get = Callable[..., Any]
EntityFunction = Callable[[Get], Iterable[Record]]


class Connector:
    """One service: where its database API lives and a function per entity.

    Each module in pipeline/connectors/ creates one as `connector` and
    registers entity functions on it with @connector.entity. An entity function
    is given `get(path, **params)`, which returns the service's parsed JSON.
    """

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.entities: list[EntityFunction] = []

    def entity(self, function: EntityFunction) -> EntityFunction:
        self.entities.append(function)
        return function

    def get(self, path: str, **params: Any) -> Any:
        response = requests.get(self.base_url + path, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def records(self) -> Iterable[Record]:
        for function in self.entities:
            yield from function(self.get)


def pick(row: dict[str, Any], *keys: str) -> dict[str, Any]:
    """The named keys of a row, in that order. A missing key raises, so a
    renamed column fails the ingest loudly instead of quietly vanishing."""
    return {key: row[key] for key in keys}


@cache
def connectors() -> dict[str, Connector]:
    """Every connector in pipeline/connectors/, keyed by service name."""
    package = importlib.import_module(CONNECTORS_PACKAGE)
    loaded: dict[str, Connector] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        module = importlib.import_module(f"{CONNECTORS_PACKAGE}.{module_info.name}")
        connector = getattr(module, "connector", None)
        if not isinstance(connector, Connector):
            raise TypeError(f"{module.__name__} must define `connector = Connector(...)`")
        if connector.name in loaded:
            raise ValueError(f"Duplicate service name {connector.name!r} in {module.__name__}")
        loaded[connector.name] = connector
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
