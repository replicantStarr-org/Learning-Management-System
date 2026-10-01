"""HTTP API for the subject application's MCP-only query tools."""

import html
import json
import os
from functools import wraps

from flask import Blueprint, jsonify, request

from services.mcp_client import MCPClientError, call_tool


mcp_bp = Blueprint("mcp", __name__)
QUERY_FIELDS = {"code", "name", "semester", "coordinator", "status"}


def mcp_is_enabled() -> bool:
    return os.getenv("MCP_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _mode_is_requested() -> bool:
    return request.headers.get("X-MCP-Mode", "on").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def mcp_render_json(title: str, payload):
    """Render an MCP result as an HTML fragment for the MCP page."""
    rendered_payload = html.escape(json.dumps(payload, indent=2), quote=False)
    return f"<h3>{html.escape(title)}</h3><pre>{rendered_payload}</pre>"


def _disabled():
    return mcp_render_json(
        "MCP integration is disabled",
        {
            "error": "MCP integration is disabled.",
            "enabled": False,
            "message": "Enable MCP integration before using MCP tools.",
        },
    ), 403


def mcp_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not mcp_is_enabled() or not _mode_is_requested():
            return _disabled()
        return view(*args, **kwargs)

    return wrapped


def _payload():
    body = request.get_json(silent=True)
    if isinstance(body, dict):
        return body
    return request.form.to_dict()


def _tool_error(tool_name, exc):
    return (
        f"<p>MCP {html.escape(tool_name)} failed.</p>"
        f"<pre>{html.escape(str(exc))}</pre>",
        503,
    )


@mcp_bp.get("/mcp/status")
@mcp_bp.get("/mcp/mode")
def mcp_status():
    enabled = mcp_is_enabled()
    return jsonify(
        {
            "enabled": enabled,
            "mcp_enabled": enabled,
            "message": "MCP integration is enabled."
            if enabled
            else "MCP integration is disabled.",
        }
    )


@mcp_bp.post("/mcp/query/tag")
@mcp_bp.post("/mcp/subjects/query/tag")
@mcp_required
def query_by_tag():
    tag = str(_payload().get("tag", "")).strip()
    if not tag:
        return mcp_render_json("MCP Tool Error", {"error": "tag is required"}), 400

    try:
        result = call_tool("subjects_query_by_tag", {"tag": tag})
        return mcp_render_json("MCP Tool: subjects_query_by_tag", result), 200
    except MCPClientError as exc:
        return _tool_error("subjects_query_by_tag", exc)


@mcp_bp.post("/mcp/query/field")
@mcp_bp.post("/mcp/subjects/query/field")
@mcp_required
def query_by_field():
    payload = _payload()
    field = str(payload.get("field", "")).strip().lower()
    value = str(payload.get("value", "")).strip()
    if field not in QUERY_FIELDS:
        return mcp_render_json(
            "MCP Tool Error",
            {"error": "field must be one of: " + ", ".join(sorted(QUERY_FIELDS))},
        ), 400
    if not value:
        return mcp_render_json("MCP Tool Error", {"error": "value is required"}), 400

    try:
        result = call_tool(
            "subjects_query_by_field", {"field": field, "value": value}
        )
        return mcp_render_json("MCP Tool: subjects_query_by_field", result), 200
    except MCPClientError as exc:
        return _tool_error("subjects_query_by_field", exc)
