import os

import requests


RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:5010").rstrip("/")
SERVICE = "timetable"
TIMEOUT = float(os.getenv("RAG_TIMEOUT_SECONDS", "10"))
INGEST_TIMEOUT = float(os.getenv("RAG_INGEST_TIMEOUT_SECONDS", "60"))
ANSWER_TIMEOUT = float(os.getenv("RAG_ANSWER_TIMEOUT_SECONDS", "150"))

TRUE_VALUES = {"1", "true", "yes", "on"}


class RagError(RuntimeError):
    pass


def rag_is_enabled():
    return os.getenv("RAG_ENABLED", "false").strip().lower() in TRUE_VALUES


def _request(method, path, payload=None, timeout=TIMEOUT):
    try:
        response = requests.request(method, f"{RAG_SERVER_URL}{path}", json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise RagError("The RAG server is unavailable. Make sure it is running on the host.") from exc

    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise RagError("The RAG server returned a malformed response.") from exc


def health():
    return _request("GET", "/health")


def retrieve(query, k=None):
    return _request("POST", "/retrieve", {"query": query, "k": k, "service": SERVICE})


def answer(query, k=None):
    return _request(
        "POST", "/answer", {"query": query, "k": k, "service": SERVICE}, timeout=ANSWER_TIMEOUT
    )


def ingest():
    return _request("POST", "/ingest", {"service": SERVICE}, timeout=INGEST_TIMEOUT)


def clear():
    return _request("POST", "/clear", {"service": SERVICE})
