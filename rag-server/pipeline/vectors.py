"""The embedding and the Chroma collection its vectors are stored in.

Ingestion and querying must embed with exactly the same function, which is why
it lives here rather than in either of them.

The embedding is feature hashing: each token is hashed to one signed
dimension. Deterministic and dependency free, so ingestion and querying always
agree as long as `dimensions` and the tokeniser are unchanged. It matches on
shared words rather than meaning, so "exam" will not find "assessment".
"""

import hashlib
import math
import re
import threading

import chromadb

from .common import resolve_path, settings

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

_lock = threading.Lock()
_collection = None


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
