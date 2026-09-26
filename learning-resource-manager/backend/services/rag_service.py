import os

import requests

# The RAG server runs on the host rather than in Docker, so from inside this
# container it is reached through host.docker.internal (see compose.yml).
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:5010")

# Rag Mode is only ever about this service's own records, indexed by the
# learning_resources connector in rag-server/pipeline/connectors/. Fixed here
# rather than taken from the page, so it cannot be used to touch another
# service's index.
SERVICE = "learning-resources"

TIMEOUT_SECONDS = 10
# Ingesting reads the whole library back and then chunks and indexes it, so it
# grows with the library; a health check has no such work to wait on.
INGEST_TIMEOUT_SECONDS = 60

class RagError(RuntimeError):
    pass

def _request(method, path, payload=None, timeout=TIMEOUT_SECONDS):
    """The RAG server's status code and JSON body, passed back as they came.

    Its error responses are already JSON explaining what went wrong, so they are
    handed to the page unchanged. Only failing to get an answer at all is an
    error here.
    """
    try:
        response = requests.request(
            method, f"{RAG_SERVER_URL}{path}", json=payload, timeout=timeout
        )
    except requests.RequestException as exc:
        raise RagError("The RAG server is unavailable.") from exc

    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise RagError("The RAG server returned a malformed response.") from exc

def health():
    return _request("GET", "/health")

def retrieve(query, k=None):
    """The k indexed chunks closest to the query, closest first.

    A missing k is sent as null, which the RAG server reads as its configured
    default. Both values are checked there rather than here.
    """
    return _request("POST", "/retrieve", {"query": query, "k": k, "service": SERVICE})

def ingest():
    """Re-index this service's records from the library as it is now.

    While this waits, the RAG server calls back into this backend for
    /api/resources/all, which is answered by another gunicorn worker. With a
    single worker the two would wait on each other until the timeout.
    """
    return _request(
        "POST", "/ingest", {"service": SERVICE}, timeout=INGEST_TIMEOUT_SECONDS
    )
