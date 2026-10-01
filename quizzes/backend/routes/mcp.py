from functools import wraps

from flask import Blueprint, jsonify, request

from services.mcp_client import MCPError, MCPToolError, call_tool, mcp_is_enabled


mcp_bp = Blueprint("mcp", __name__)

DIFFICULTIES = {"Easy", "Medium", "Hard"}


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


def _text(body, name):
    return str(body.get(name) or "").strip()


def _bad_request(message):
    return jsonify({"status": "error", "error": message}), 400


def _quiz_id(body):
    value = _text(body, "quiz_id")
    return int(value) if value.isdigit() and int(value) >= 1 else None


def _run(tool_name, arguments=None):
    """Call one quiz tool and return its structured result to the page."""
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


def _filters(body):
    """The optional subject and difficulty filters, or None if difficulty is invalid."""
    arguments = {}
    subject = _text(body, "subject")
    if subject:
        arguments["subject"] = subject
    difficulty = _text(body, "difficulty")
    if difficulty:
        if difficulty not in DIFFICULTIES:
            return None
        arguments["difficulty"] = difficulty
    return arguments


@mcp_bp.post("/mcp/quizzes")
@mcp_required
def mcp_quizzes():
    arguments = _filters(_body())
    if arguments is None:
        return _bad_request("difficulty must be Easy, Medium or Hard")
    return _run("quizzes_list", arguments)


@mcp_bp.post("/mcp/quiz")
@mcp_required
def mcp_quiz():
    quiz_id = _quiz_id(_body())
    if quiz_id is None:
        return _bad_request("quiz_id must be a positive integer")
    return _run("quizzes_get", {"quiz_id": quiz_id})


@mcp_bp.post("/mcp/practice")
@mcp_required
def mcp_practice():
    arguments = _filters(_body())
    if arguments is None:
        return _bad_request("difficulty must be Easy, Medium or Hard")
    return _run("quizzes_practice_question", arguments)


@mcp_bp.post("/mcp/search")
@mcp_required
def mcp_search():
    keyword = _text(_body(), "keyword")
    if not keyword:
        return _bad_request("keyword is required")
    return _run("quizzes_search_questions", {"keyword": keyword})
