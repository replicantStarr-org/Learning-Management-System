import os
from functools import wraps

from flask import Blueprint, jsonify, request

from services import mcp_service
from services.mcp_service import McpError, McpToolError

mcp_bp = Blueprint('mcp', __name__)

# The switch, status endpoint and 403 follow the subjects service's MCP routes
# (subjects/backend/routes/mcp.py), the hub's standard for MCP integration.
TRUE_VALUES = {"1", "true", "yes", "on"}

def mcp_is_enabled():
    """Whether MCP is turned on for this service. Off unless configured on:
    compose.yml turns it on, and CI turns it off so no run needs the MCP server."""
    return os.getenv("MCP_ENABLED", "false").strip().lower() in TRUE_VALUES

def _mode_is_requested():
    # A caller can opt a single request out; without the header it is on.
    return request.headers.get("X-MCP-Mode", "on").strip().lower() in TRUE_VALUES

def mcp_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not mcp_is_enabled() or not _mode_is_requested():
            return jsonify({
                "status": "error",
                "error": "MCP integration is disabled.",
                "enabled": False,
            }), 403
        return view(*args, **kwargs)

    return wrapped

@mcp_bp.route('/status', methods=['GET'])
def status():
    enabled = mcp_is_enabled()
    return jsonify({
        "enabled": enabled,
        "mcp_enabled": enabled,
        "message": "MCP integration is enabled." if enabled else "MCP integration is disabled.",
    })

def _relay(call):
    """The tool's result for the page, or why there is none.

    A tool that ran and failed is a 502, since the MCP server answered but what
    it depends on did not; no answer from the MCP server at all is a 503.
    """
    try:
        return jsonify(call())
    except McpToolError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 502
    except McpError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 503

@mcp_bp.route('/tools', methods=['GET'])
@mcp_required
def tools():
    return _relay(lambda: {"tools": mcp_service.list_tools()})

@mcp_bp.route('/resources', methods=['GET'])
@mcp_required
def resources():
    return _relay(lambda: {"resources": mcp_service.list_resources()})

@mcp_bp.route('/tags', methods=['GET'])
@mcp_required
def tags():
    return _relay(lambda: {"tags": mcp_service.list_tags()})

@mcp_bp.route('/resources/by_tag', methods=['POST'])
@mcp_required
def resources_by_tag():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}

    # Checked here as well as by the tool: a missing tag is the page's mistake,
    # so it should be a 400 rather than the 502 a failing tool is relayed as.
    tag = str(payload.get("tag") or "").strip()
    if not tag:
        return jsonify({"status": "error", "error": "A tag is required."}), 400

    return _relay(lambda: {"tag": tag, "resources": mcp_service.resources_by_tag(tag)})
