"""HTTP endpoints used by the Subjects RAG page."""

from flask import Blueprint, jsonify, request

from services import rag_service
from services.rag_service import RagError


rag_bp = Blueprint("rag", __name__)


def _relay(call):
    """Return the RAG response unchanged, or explain connection failures."""
    try:
        status, body = call()
    except RagError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503
    return jsonify(body), status


@rag_bp.get("/rag/health")
@rag_bp.get("/api/rag/health")
def health():
    return _relay(rag_service.health)


def _query_and_k():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    return payload.get("query"), payload.get("k")


@rag_bp.post("/rag/retrieve")
@rag_bp.post("/api/rag/retrieve")
def retrieve():
    query, k = _query_and_k()
    return _relay(lambda: rag_service.retrieve(query, k))


@rag_bp.post("/rag/answer")
@rag_bp.post("/api/rag/answer")
def answer():
    query, k = _query_and_k()
    return _relay(lambda: rag_service.answer(query, k))


@rag_bp.post("/rag/ingest")
@rag_bp.post("/api/rag/ingest")
def ingest():
    return _relay(rag_service.ingest)


@rag_bp.post("/rag/clear")
@rag_bp.post("/api/rag/clear")
def clear():
    return _relay(rag_service.clear)
