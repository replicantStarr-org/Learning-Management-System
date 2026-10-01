from functools import wraps

from flask import Blueprint, jsonify, request

from services.mcp_client import MCPError, MCPToolError, call_tool, mcp_is_enabled


mcp_bp = Blueprint("mcp", __name__)


def mcp_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not mcp_is_enabled():
            return jsonify(
                {
                    "status": "error",
                    "error": "MCP integration is disabled.",
                    "enabled": False,
                }
            ), 403
        return view(*args, **kwargs)

    return wrapped


def _body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _bad_request(message):
    return jsonify({"status": "error", "error": message}), 400


def _run(tool_name, arguments=None):
    """Call one timetable tool and return its structured result to the page."""
    arguments = arguments or {}
    try:
        result = call_tool(tool_name, arguments)
    except MCPToolError as exc:
        return jsonify(
            {"status": "error", "tool": tool_name, "arguments": arguments, "error": str(exc)}
        ), 400
    except MCPError as exc:
        return jsonify({"status": "error", "tool": tool_name, "error": str(exc)}), 503
    return jsonify(
        {"status": "success", "tool": tool_name, "arguments": arguments, "result": result}
    )


@mcp_bp.get("/mcp/status")
def mcp_status():
    enabled = mcp_is_enabled()
    return jsonify(
        {
            "enabled": enabled,
            "mcp_enabled": enabled,
            "message": "MCP integration is enabled." if enabled else "MCP integration is disabled.",
        }
    )


@mcp_bp.post("/mcp/users")
@mcp_required
def mcp_users():
    return _run("timetable_users_list")


@mcp_bp.post("/mcp/entries")
@mcp_required
def mcp_entries():
    body = _body()
    username = str(body.get("username") or "").strip()
    if not username:
        return _bad_request("username is required")
    arguments = {"username": username}
    week_of = str(body.get("week_of") or "").strip()
    if week_of:
        arguments["week_of"] = week_of
    return _run("timetable_entries_list", arguments)


@mcp_bp.post("/mcp/entry")
@mcp_required
def mcp_entry():
    timetable_id = str(_body().get("timetable_id") or "").strip()
    if not timetable_id.isdigit() or int(timetable_id) < 1:
        return _bad_request("timetable_id must be a positive integer")
    return _run("timetable_entry_get", {"timetable_id": int(timetable_id)})


@mcp_bp.post("/mcp/free-time")
@mcp_required
def mcp_free_time():
    body = _body()
    username = str(body.get("username") or "").strip()
    on_date = str(body.get("on_date") or "").strip()
    if not username:
        return _bad_request("username is required")
    if not on_date:
        return _bad_request("on_date is required")
    return _run("timetable_free_time", {"username": username, "on_date": on_date})
