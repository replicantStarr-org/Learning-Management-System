from flask import Blueprint, jsonify

from services import mcp_service
from services.mcp_service import McpError, McpToolError

mcp_bp = Blueprint('mcp', __name__)

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
def tools():
    return _relay(lambda: {"tools": mcp_service.list_tools()})

@mcp_bp.route('/resources', methods=['GET'])
def resources():
    return _relay(lambda: {"resources": mcp_service.list_resources()})
