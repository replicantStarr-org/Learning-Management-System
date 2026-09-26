"""One function per HTTP endpoint, routed to by http_server.ROUTES.

Each takes the request's JSON body (empty for GET) and returns
(status code, JSON body). Invalid requests raise ApiError, which the server
turns into the response, so no endpoint builds its own error bodies.
"""

from typing import Any

from pipeline.connector import connectors
from pipeline.ingestion import ingest_services
from pipeline.querying import answer_question, retrieve_context

# 502 for errors: the RAG server is fine, the service it read from was not.
INGEST_STATUS_CODES = {"success": 200, "skipped": 200, "partial": 207, "error": 502}


class ApiError(Exception):
    def __init__(self, status: int, error: str, **extra: Any):
        super().__init__(error)
        self.status = status
        self.body = {"status": "error", "error": error, **extra}


# -------------------------------------------------------------------- endpoints


def health(payload):
    """GET /health: whether the RAG server is up."""
    return 200, {"status": "ok", "service": "rag-server"}


def services(payload):
    """GET /services: the service names that can be ingested and filtered on."""
    return 200, {"status": "ok", "services": sorted(connectors())}


def ingest(payload):
    """POST /ingest: re-index one service, or every service when none is named."""
    result = ingest_services(requested_service(payload))
    return INGEST_STATUS_CODES[result["status"]], result


def retrieve(payload):
    """POST /retrieve: the closest chunks to a query, without asking the model."""
    result = retrieve_context(
        query=required_query(payload),
        k=requested_k(payload),
        service=requested_service(payload),
    )
    return 200 if result["status"] == "success" else 500, result


def answer(payload):
    """POST /answer: retrieve chunks for a query and have the model answer from them."""
    result = answer_question(
        query=required_query(payload),
        k=requested_k(payload),
        service=requested_service(payload),
    )
    return 200 if result["status"] == "success" else 500, result


# ----------------------------------------------------------------------- checks


def requested_service(payload: dict[str, Any]) -> str | None:
    """The optional `service` name, which must match a connector."""
    service = (payload.get("service") or "").strip() or None
    if service and service not in connectors():
        raise ApiError(404, f"unknown service {service!r}", available=sorted(connectors()))
    return service


def required_query(payload: dict[str, Any]) -> str:
    query = (payload.get("query") or "").strip()
    if not query:
        raise ApiError(400, "query is required")
    return query


def requested_k(payload: dict[str, Any]) -> int | None:
    """The optional `k`, a positive whole number; missing or null means the default from config.toml."""
    k = payload.get("k")
    if k is None:
        return None
    if isinstance(k, str) and k.strip().isdigit():
        k = int(k)
    # bool is a subclass of int, so true/false would otherwise pass as 1/0.
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise ApiError(400, "k must be a positive integer")
    return k
