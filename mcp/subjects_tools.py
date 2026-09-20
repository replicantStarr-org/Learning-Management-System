"""
MCP tools for the subjects microservice.

The tools call into the backend API to avoid duplicating business logic.
"""

import json
import os
from typing import Any

import requests


class SubjectsApiError(RuntimeError):
    """An error returned by, or while reaching, the subjects API."""


class SubjectsApiClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (
            base_url or os.getenv(
                "SUBJECTS_API_URL", "http://127.0.0.1:5001/api/v1"
            )
        ).rstrip("/")
        self.timeout = timeout or float(os.getenv("SUBJECTS_API_TIMEOUT_SECONDS", "10"))

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise SubjectsApiError(
                "The subjects service is unavailable. "
                "Make sure the subjects containers are running."
            ) from exc

        if not response.ok:
            try:
                body = response.json()
            except ValueError:
                body = {}
            message = body.get("error", response.reason or "Subjects API request failed")
            if isinstance(message, dict):
                message = message.get("message", "Subjects API request failed")
            details = body.get("details")
            if details:
                message = f"{message} ({json.dumps(details, ensure_ascii=False)})"
            raise SubjectsApiError(f"HTTP {response.status_code}: {message}")

        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise SubjectsApiError("The subjects service returned invalid JSON.") from exc


def _json_result(value: Any) -> str:
    if value is None:
        value = {"ok": True}
    return json.dumps(value, ensure_ascii=False)


def register_subject_tools(mcp):
    client = SubjectsApiClient()

    @mcp.tool(name="subjects_list")
    def subjects_list() -> str:
        """List all subjects."""
        return _json_result(client.request("GET", "/subjects"))

    @mcp.tool(name="subjects_get")
    def subjects_get(subject_id: int) -> str:
        """Get one subject, including its assigned tags."""
        return _json_result(client.request("GET", f"/subjects/{subject_id}"))

    @mcp.tool(name="subjects_create")
    def subjects_create(
        code: str,
        name: str,
        description: str,
        semester: str,
        coordinator: str,
        status: str,
    ) -> str:
        """Create a subject with all required subject fields."""
        return _json_result(
            client.request(
                "POST",
                "/subjects",
                json={
                    "code": code,
                    "name": name,
                    "description": description,
                    "semester": semester,
                    "coordinator": coordinator,
                    "status": status,
                },
            )
        )

    @mcp.tool(name="subjects_update")
    def subjects_update(
        subject_id: int,
        code: str | None = None,
        name: str | None = None,
        description: str | None = None,
        semester: str | None = None,
        coordinator: str | None = None,
        status: str | None = None,
    ) -> str:
        """Update one or more fields on an existing subject."""
        fields = {
            key: value
            for key, value in {
                "code": code,
                "name": name,
                "description": description,
                "semester": semester,
                "coordinator": coordinator,
                "status": status,
            }.items()
            if value is not None
        }
        return _json_result(
            client.request("PATCH", f"/subjects/{subject_id}", json=fields)
        )

    @mcp.tool(name="subjects_delete")
    def subjects_delete(subject_id: int) -> str:
        """Delete a subject and its related stored summaries."""
        return _json_result(
            client.request("DELETE", f"/subjects/{subject_id}")
        )

    @mcp.tool(name="subjects_tags_list")
    def subjects_tags_list() -> str:
        """List all tags and their subject counts."""
        return _json_result(client.request("GET", "/tags"))

    @mcp.tool(name="subjects_tag_get")
    def subjects_tag_get(tag_id: int) -> str:
        """Get one tag and its subject count."""
        return _json_result(client.request("GET", f"/tags/{tag_id}"))

    @mcp.tool(name="subjects_tag_create")
    def subjects_tag_create(name: str) -> str:
        """Create a tag."""
        return _json_result(client.request("POST", "/tags", json={"name": name}))

    @mcp.tool(name="subjects_tag_update")
    def subjects_tag_update(tag_id: int, name: str) -> str:
        """Rename a tag."""
        return _json_result(
            client.request("PUT", f"/tags/{tag_id}", json={"name": name})
        )

    @mcp.tool(name="subjects_tag_delete")
    def subjects_tag_delete(tag_id: int) -> str:
        """Delete a tag."""
        return _json_result(client.request("DELETE", f"/tags/{tag_id}"))

    @mcp.tool(name="subjects_subject_tags_list")
    def subjects_subject_tags_list(subject_id: int) -> str:
        """List the tags assigned to one subject."""
        return _json_result(
            client.request("GET", f"/subjects/{subject_id}/tags")
        )

    @mcp.tool(name="subjects_subject_tags_set")
    def subjects_subject_tags_set(subject_id: int, tag_ids: list[int]) -> str:
        """Replace all tags assigned to a subject with the supplied tag IDs."""
        return _json_result(
            client.request(
                "PUT",
                f"/subjects/{subject_id}/tags",
                json={"tag_ids": tag_ids},
            )
        )

    @mcp.tool(name="subjects_subject_tag_remove")
    def subjects_subject_tag_remove(subject_id: int, tag_id: int) -> str:
        """Remove one tag assignment from a subject."""
        return _json_result(
            client.request(
                "DELETE", f"/subjects/{subject_id}/tags/{tag_id}"
            )
        )
