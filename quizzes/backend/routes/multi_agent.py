import os
from functools import wraps

from flask import Blueprint, jsonify, request

from services import multi_agent_service

multi_agent_bp = Blueprint("multi_agent", __name__)
TRUE_VALUES = {"1", "true", "yes", "on"}


def is_enabled():
    cloud = os.getenv("CLOUD_DEPLOYMENT", "false").strip().lower() in TRUE_VALUES
    return os.getenv("MULTI_AGENT_ENABLED", "false" if cloud else "true").strip().lower() in TRUE_VALUES


def required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_enabled() or request.headers.get("X-Multi-Agent-Mode", "on").strip().lower() not in TRUE_VALUES:
            return jsonify(status="error", error="Multi-Agent integration is disabled."), 403
        return view(*args, **kwargs)
    return wrapped


def _relay(call):
    try:
        status, body = call()
        return jsonify(body), status
    except multi_agent_service.MultiAgentError as exc:
        return jsonify(status="error", error=str(exc)), 503


def _body():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


@multi_agent_bp.get("/multi-agent/status")
def mode_status():
    return jsonify(enabled=is_enabled())


@multi_agent_bp.post("/multi-agent/workflow")
@required
def workflow():
    payload = _body()
    if payload is None:
        return jsonify(error="Request body must be a JSON object"), 400
    return _relay(lambda: multi_agent_service.run_workflow(payload))


@multi_agent_bp.get("/multi-agent/workflow/status")
@required
def workflow_status():
    return _relay(multi_agent_service.workflow_status)


@multi_agent_bp.get("/multi-agent/workflow/<uuid:workflow_id>")
@required
def workflow_detail(workflow_id):
    return _relay(lambda: multi_agent_service.get_workflow(str(workflow_id)))


@multi_agent_bp.post("/multi-agent/workflow/<uuid:workflow_id>/decision")
@required
def decision(workflow_id):
    payload = _body()
    if payload is None:
        return jsonify(error="Request body must be a JSON object"), 400
    return _relay(lambda: multi_agent_service.record_decision(str(workflow_id), payload))
