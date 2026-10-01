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
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"status": "error", "error": "Request body must be a JSON object"}), 400

    action = body.get("action", "list")
    if action == "list":
        status = body.get("status")
        subject_id = body.get("subject_id")
        if status is not None and not isinstance(status, str):
            return jsonify({"status": "error", "error": "status must be a string"}), 400
        if subject_id is not None and (
            isinstance(subject_id, bool) or not isinstance(subject_id, int) or subject_id < 1
        ):
            return jsonify({"status": "error", "error": "subject_id must be a positive integer"}), 400
        tool = "assignments_list"
        arguments = {key: body[key] for key in ("status", "subject_id") if key in body}
    elif action == "upcoming":
        days = body.get("days", 7)
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365:
            return jsonify({"status": "error", "error": "days must be an integer from 1 to 365"}), 400
        tool = "assignments_upcoming"
        arguments = {"days": days}
    elif action == "get":
        assignment_id = body.get("assignment_id")
        if isinstance(assignment_id, bool) or not isinstance(assignment_id, int) or assignment_id < 1:
            return jsonify({"status": "error", "error": "assignment_id must be a positive integer"}), 400
        tool = "assignments_get"
        arguments = {"assignment_id": assignment_id}
    else:
        return jsonify({"status": "error", "error": "action must be list, upcoming, or get"}), 400

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