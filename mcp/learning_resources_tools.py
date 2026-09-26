"""
MCP tools for the learning resource manager.

The tools call the learning resource manager's backend API rather than its
database, so the MCP server sees the library exactly as the page does.
"""

import json
import os
from typing import Any

import requests
from mcp.server.mcpserver.exceptions import ToolError


class LearningResourcesApiError(ToolError):
    """An error returned by, or while reaching, the learning resources API.

    A ToolError, so the MCP SDK passes this message on to the caller rather
    than replacing it with a generic one.
    """


class LearningResourcesApiClient:
    def __init__(self):
        # The backend's port on the host (see learning-resource-manager/compose.yml).
        self.base_url = os.getenv(
            "LEARNING_RESOURCES_API_URL", "http://127.0.0.1:5002/api/resources"
        ).rstrip("/")
        self.timeout = float(os.getenv("LEARNING_RESOURCES_API_TIMEOUT_SECONDS", "10"))

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = requests.request(
                method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs
            )
        except requests.RequestException as exc:
            raise LearningResourcesApiError(
                "The learning resource manager is unavailable. "
                "Make sure its containers are running."
            ) from exc

        if not response.ok:
            raise LearningResourcesApiError(
                f"HTTP {response.status_code}: learning resources API request failed"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise LearningResourcesApiError(
                "The learning resource manager returned invalid JSON."
            ) from exc


def register_learning_resource_tools(mcp):
    client = LearningResourcesApiClient()

    @mcp.tool(name="learning_resources_list")
    def learning_resources_list() -> str:
        """List every learning resource in the library (textbooks and papers),
        with its title, author, medium, description and tags."""
        # /catalogue rather than /all: it returns objects with their tags,
        # where /all returns bare arrays without them.
        return json.dumps(client.request("GET", "/catalogue"), ensure_ascii=False)

    @mcp.tool(name="learning_resources_tags_list")
    def learning_resources_tags_list() -> str:
        """List every tag in the library, such as "Deep Learning" or "Physics".

        Tags record a resource's subject area. Use these names with
        learning_resources_by_tag, which only matches a tag name in full.
        """
        tags = client.request("GET", "/tags")
        return json.dumps(sorted(tags, key=lambda tag: tag["name"].casefold()), ensure_ascii=False)

    @mcp.tool(name="learning_resources_by_tag")
    def learning_resources_by_tag(tag: str) -> str:
        """Find the learning resources carrying a tag, such as "Deep Learning".

        The tag must match a tag name in full, ignoring case. Tags record a
        resource's subject area, so this is how to find what the library holds
        on a topic. An empty list means no resource has that tag.
        """
        wanted = tag.strip().casefold()
        if not wanted:
            raise ToolError("A tag is required.")

        # The backend has no tag filter, and the library is small enough to
        # filter here rather than add one.
        matches = [
            resource
            for resource in client.request("GET", "/catalogue")
            if wanted in (name.casefold() for name in resource["tags"])
        ]
        return json.dumps(matches, ensure_ascii=False)
