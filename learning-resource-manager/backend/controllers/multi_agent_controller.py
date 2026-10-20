import os
from functools import wraps

from flask import Blueprint, jsonify, request

from services import multi_agent_service

multi_agent_bp = Blueprint('multi_agent', __name__)

# The switch, status endpoint and 403 follow the subjects service's multi-agent
# routes (subjects/backend/routes/multi_agent.py). On unless configured off:
# compose.yml passes the flag through, and CI turns it off so no run needs the
# multi-agent server.
TRUE_VALUES = {"1", "true", "yes", "on"}


def multi_agent_is_enabled():
    return os.getenv("MULTI_AGENT_ENABLED", "true").strip().lower() in TRUE_VALUES


def _mode_is_requested():
    # A caller can opt a single request out; without the header it is on.
    return request.headers.get("X-Multi-Agent-Mode", "on").strip().lower() in TRUE_VALUES


def multi_agent_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not multi_agent_is_enabled() or not _mode_is_requested():
            return jsonify({
                "status": "error",
                "error": "Multi-Agent integration is disabled.",
                "enabled": False,
            }), 403
        return view(*args, **kwargs)

    return wrapped


def _relay(call):
    """The multi-agent server's answer with its own status code, or a 503 when
    there was no usable answer at all."""
    try:
        status, body = call()
        return jsonify(body), status
    except multi_agent_service.MultiAgentError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503


def _body():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


@multi_agent_bp.route('/status', methods=['GET'])
def status():
    enabled = multi_agent_is_enabled()
    state = "enabled" if enabled else "disabled"
    return jsonify({"enabled": enabled, "message": f"Multi-Agent integration is {state}."})


@multi_agent_bp.route('/workflow', methods=['POST'])
@multi_agent_required
def workflow():
    payload = _body()
    if payload is None:
        return jsonify({"status": "error", "error": "Request body must be a JSON object"}), 400
    return _relay(lambda: multi_agent_service.run_workflow(payload))


@multi_agent_bp.route('/workflow/status', methods=['GET'])
@multi_agent_required
def workflow_status():
    return _relay(multi_agent_service.workflow_status)


@multi_agent_bp.route('/workflow/<uuid:workflow_id>', methods=['GET'])
@multi_agent_required
def workflow_detail(workflow_id):
    return _relay(lambda: multi_agent_service.get_workflow(str(workflow_id)))


@multi_agent_bp.route('/workflow/<uuid:workflow_id>/decision', methods=['POST'])
@multi_agent_required
def decision(workflow_id):
    payload = _body()
    if payload is None:
        return jsonify({"status": "error", "error": "Request body must be a JSON object"}), 400
    return _relay(lambda: multi_agent_service.record_decision(str(workflow_id), payload))
