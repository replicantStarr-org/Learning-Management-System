import os
from functools import wraps

from flask import Blueprint, jsonify, request

from services.integration import IntegrationError, call_mcp, call_rag


integration_bp = Blueprint("integration", __name__, url_prefix="/integration")
TRUE_VALUES = {"1", "true", "yes", "on"}


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in TRUE_VALUES


def _required(name: str):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not _enabled(name, "true" if name == "RAG_ENABLED" else "false"):
                return jsonify({"status": "error", "error": f"{name.removesuffix('_ENABLED')} integration is disabled.", "enabled": False}), 403
            mode_header = "X-MCP-Mode" if name == "MCP_ENABLED" else "X-RAG-Mode"
            if request.headers.get(mode_header, "on").strip().lower() not in TRUE_VALUES:
                return jsonify({"status": "error", "error": "Integration mode is disabled for this request.", "enabled": False}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorate


def _relay(call):
    try:
        status, response = call()
        return jsonify(response), status
    except IntegrationError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503


@integration_bp.get("/mcp/status")
def mcp_status():
    enabled = _enabled("MCP_ENABLED")
    return jsonify({"enabled": enabled, "mcp_enabled": enabled})


@integration_bp.post("/mcp/assignments")
@_required("MCP_ENABLED")
def mcp_assignments():
    body = request.get_json(silent=True) or {}
    action = body.get("action", "list")
    tools = {
        "list": ("assignments_list", {key: body[key] for key in ("status", "subject_id") if key in body}),
        "upcoming": ("assignments_upcoming", {"days": body.get("days", 7)}),
        "get": ("assignments_get", {"assignment_id": body.get("assignment_id")}),
    }
    if action not in tools:
        return jsonify({"status": "error", "error": "action must be list, upcoming, or get"}), 400
    tool, arguments = tools[action]
    try:
        result = call_mcp(tool, arguments)
    except IntegrationError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503
    return jsonify({"status": "success", "tool": tool, "result": result})


@integration_bp.get("/rag/status")
def rag_status():
    enabled = _enabled("RAG_ENABLED", "true")
    return jsonify({"enabled": enabled, "rag_enabled": enabled})


@integration_bp.get("/rag/health")
@_required("RAG_ENABLED")
def rag_health():
    return _relay(lambda: call_rag("/health"))


@integration_bp.post("/rag/answer")
@_required("RAG_ENABLED")
def rag_answer():
    body = request.get_json(silent=True) or {}
    return _relay(lambda: call_rag("/answer", {"query": body.get("query"), "k": body.get("k"), "service": "assignments"}, float(os.getenv("RAG_ANSWER_TIMEOUT_SECONDS", "150"))))


@integration_bp.post("/rag/retrieve")
@_required("RAG_ENABLED")
def rag_retrieve():
    body = request.get_json(silent=True) or {}
    return _relay(lambda: call_rag("/retrieve", {"query": body.get("query"), "k": body.get("k"), "service": "assignments"}))


@integration_bp.post("/rag/ingest")
@_required("RAG_ENABLED")
def rag_ingest():
    return _relay(lambda: call_rag("/ingest", {"service": "assignments"}, 60))