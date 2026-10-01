"""HTTP endpoints used by the Subjects RAG page."""

import os
from functools import wraps

from flask import Blueprint, jsonify, request

from services import rag_service
from services.rag_service import RagError


rag_bp = Blueprint("rag", __name__)


def rag_is_enabled() -> bool:
    return os.getenv("RAG_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _mode_is_requested() -> bool:
    return request.headers.get("X-RAG-Mode", "on").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _disabled():
    return jsonify(
        {
            "error": "RAG integration is disabled.",
            "enabled": False,
            "message": "Enable RAG integration before using RAG tools.",
        }
    ), 403


def rag_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not rag_is_enabled() or not _mode_is_requested():
            return _disabled()
        return view(*args, **kwargs)

    return wrapped


@rag_bp.get("/rag/status")
@rag_bp.get("/rag/mode")
def rag_status():
    enabled = rag_is_enabled()
    return jsonify(
        {
            "enabled": enabled,
            "rag_enabled": enabled,
            "message": "RAG integration is enabled."
            if enabled
            else "RAG integration is disabled.",
        }
    )


def _relay(call):
    """Return the RAG response unchanged, or explain connection failures."""
    try:
        status, body = call()
    except RagError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503
    return jsonify(body), status


@rag_bp.get("/rag/health")
@rag_bp.get("/api/rag/health")
@rag_required
def health():
    return _relay(rag_service.health)


def _query_and_k():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    return payload.get("query"), payload.get("k")


@rag_bp.post("/rag/retrieve")
@rag_bp.post("/api/rag/retrieve")
@rag_required
def retrieve():
    query, k = _query_and_k()
    return _relay(lambda: rag_service.retrieve(query, k))


@rag_bp.post("/rag/answer")
@rag_bp.post("/api/rag/answer")
@rag_required
def answer():
    query, k = _query_and_k()
    return _relay(lambda: rag_service.answer(query, k))


@rag_bp.post("/rag/ingest")
@rag_bp.post("/api/rag/ingest")
@rag_required
def ingest():
    return _relay(rag_service.ingest)


@rag_bp.post("/rag/clear")
@rag_bp.post("/api/rag/clear")
@rag_required
def clear():
    return _relay(rag_service.clear)
