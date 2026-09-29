"""Client for the RAG server, scoped to subject records.

The browser never chooses a RAG service. Keeping the service name here means
this page can only ingest, clear, retrieve and answer questions about subjects.
"""

import os

import requests


RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:5010").rstrip("/")
SERVICE = "subjects"
REQUEST_TIMEOUT_SECONDS = float(os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "10"))
INGEST_TIMEOUT_SECONDS = float(os.getenv("RAG_INGEST_TIMEOUT_SECONDS", "60"))
ANSWER_TIMEOUT_SECONDS = float(os.getenv("RAG_ANSWER_TIMEOUT_SECONDS", "150"))


class RagError(RuntimeError):
    """Raised when the RAG server cannot be reached or returns invalid JSON."""


def _request(method, path, payload=None, timeout=REQUEST_TIMEOUT_SECONDS):
    try:
        response = requests.request(
            method,
            f"{RAG_SERVER_URL}{path}",
            json=payload,
            timeout=timeout,
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
    return _request(
        "POST",
        "/retrieve",
        {"query": query, "k": k, "service": SERVICE},
    )


def answer(query, k=None):
    return _request(
        "POST",
        "/answer",
        {"query": query, "k": k, "service": SERVICE},
        timeout=ANSWER_TIMEOUT_SECONDS,
    )


def ingest():
    return _request(
        "POST",
        "/ingest",
        {"service": SERVICE},
        timeout=INGEST_TIMEOUT_SECONDS,
    )


def clear():
    return _request("POST", "/clear", {"service": SERVICE})
