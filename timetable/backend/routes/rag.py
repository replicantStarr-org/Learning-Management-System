from functools import wraps

from flask import Blueprint, jsonify, request

from services import rag_client
from services.rag_client import RagError, rag_is_enabled


rag_bp = Blueprint("rag", __name__)


def rag_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not rag_is_enabled():
            return jsonify(
                {
                    "status": "error",
                    "error": "RAG integration is disabled.",
                    "enabled": False,
                }
            ), 403
        return view(*args, **kwargs)

    return wrapped


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


@rag_bp.get("/rag/status")
def rag_status():
    enabled = rag_is_enabled()
    return jsonify(
        {
            "enabled": enabled,
            "rag_enabled": enabled,
            "service": rag_client.SERVICE,
            "message": "RAG integration is enabled." if enabled else "RAG integration is disabled.",
        }
    )


@rag_bp.get("/rag/health")
@rag_required
def rag_health():
    return _relay(rag_client.health)


@rag_bp.post("/rag/retrieve")
@rag_required
def rag_retrieve():
    query, k = _query_and_k()
    return _relay(lambda: rag_client.retrieve(query, k))


@rag_bp.post("/rag/answer")
@rag_required
def rag_answer():
    query, k = _query_and_k()
    return _relay(lambda: rag_client.answer(query, k))


@rag_bp.post("/rag/ingest")
@rag_required
def rag_ingest():
    return _relay(rag_client.ingest)


@rag_bp.post("/rag/clear")
@rag_required
def rag_clear():
    return _relay(rag_client.clear)
