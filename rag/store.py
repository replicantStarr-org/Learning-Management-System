import threading

import chromadb

from config import resolve_path, settings

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
