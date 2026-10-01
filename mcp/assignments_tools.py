"""Read-only MCP tools for assignment records."""

import json
import os

import requests
from mcp.server.mcpserver.exceptions import ToolError


BASE_URL = os.getenv("ASSIGNMENTS_DATABASE_API_URL", "http://127.0.0.1:6003").rstrip("/")
TIMEOUT = float(os.getenv("ASSIGNMENTS_API_TIMEOUT_SECONDS", "10"))
PUBLIC_ASSIGNMENT_FIELDS = (
    "assignment_id",
    "subject_id",
    "subject_name",
    "title",
    "description",
    "requirements",
    "due_at",
    "status",
    "priority",
    "weighting",
)


def _get(path, **params):
    try:
        response = requests.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise ToolError("The assignments service is unavailable.") from exc
    except ValueError as exc:
        raise ToolError("The assignments service returned invalid JSON.") from exc


def register_assignment_tools(mcp):
    @mcp.tool(name="assignments_list")
    def assignments_list(status: str | None = None, subject_id: int | None = None) -> str:
        """List assignments, optionally filtered by status and subject."""
        params = {}
        if status:
            params["status"] = status
        if subject_id is not None:
            params["subject_id"] = subject_id
        return json.dumps(_get("/assignments", **params), ensure_ascii=False)

    @mcp.tool(name="assignments_upcoming")
    def assignments_upcoming(days: int = 7) -> str:
        """List unsubmitted assignments due within the next number of days."""
        if days < 1 or days > 365:
            raise ToolError("days must be between 1 and 365")
        return json.dumps(_get("/assignments/upcoming", days=days), ensure_ascii=False)

    @mcp.tool(name="assignments_get")
    def assignments_get(assignment_id: int) -> str:
        """Get one assignment's source details by ID."""
        if assignment_id < 1:
            raise ToolError("assignment_id must be a positive integer")
        assignment = _get(f"/assignments/{assignment_id}")
        public = {key: assignment[key] for key in PUBLIC_ASSIGNMENT_FIELDS if key in assignment}
        return json.dumps(public, ensure_ascii=False)