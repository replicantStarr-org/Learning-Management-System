"""
MCP tools for the learning resource manager.

The tools call the learning resource manager's backend API rather than its
database, so the MCP server sees the library exactly as the page does.
"""

import json
import os
from typing import Any

import requests


class LearningResourcesApiError(RuntimeError):
    """An error returned by, or while reaching, the learning resources API."""


class LearningResourcesApiClient:
    def __init__(self):
        # The backend's published port on the host (see
        # learning-resource-manager/compose.yml).
        self.base_url = os.getenv(
            "LEARNING_RESOURCES_API_URL", "http://127.0.0.1:7050/api/resources"
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
