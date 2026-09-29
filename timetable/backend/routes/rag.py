from flask import Blueprint, jsonify, request

from services import rag_client
from services.rag_client import RagError


rag_bp = Blueprint("rag", __name__)


def _relay(call):
    try:
        status, body = call()
    except RagError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503
    return jsonify(body), status


def _query_and_k():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    return body.get("query"), body.get("k")


@rag_bp.get("/rag/health")
def rag_health():
    return _relay(rag_client.health)


@rag_bp.post("/rag/retrieve")
def rag_retrieve():
    query, k = _query_and_k()
    return _relay(lambda: rag_client.retrieve(query, k))


@rag_bp.post("/rag/answer")
def rag_answer():
    query, k = _query_and_k()
    return _relay(lambda: rag_client.answer(query, k))


@rag_bp.post("/rag/ingest")
def rag_ingest():
    return _relay(rag_client.ingest)


@rag_bp.post("/rag/clear")
def rag_clear():
    return _relay(rag_client.clear)
