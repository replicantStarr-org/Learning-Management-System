"""Feature-scoped clients for the shared local MCP and RAG servers."""

import asyncio
import json
import os
from typing import Any

import requests
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


MCP_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
RAG_URL = os.getenv("RAG_SERVER_URL", "http://127.0.0.1:5010").rstrip("/")
TIMEOUT = float(os.getenv("INTEGRATION_TIMEOUT_SECONDS", "15"))


class IntegrationError(RuntimeError):
    pass


async def _call_mcp_async(name: str, arguments: dict[str, Any]) -> Any:
    async with streamable_http_client(MCP_URL) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments, read_timeout_seconds=TIMEOUT)
            if result.is_error:
                text = "; ".join(item.text for item in result.content if hasattr(item, "text"))
                raise IntegrationError(text or "MCP tool call failed")
            value = getattr(result, "structuredContent", None)
            if value is not None:
                return value
            text = next((item.text for item in result.content if hasattr(item, "text")), "null")
            try:
                return json.loads(text)
            except ValueError:
                return text


def call_mcp(name: str, arguments: dict[str, Any] | None = None) -> Any:
    try:
        return asyncio.run(_call_mcp_async(name, arguments or {}))
    except Exception as exc:
        raise IntegrationError("The shared MCP server is unavailable or rejected the request.") from exc


def call_rag(path: str, payload: dict[str, Any] | None = None, timeout: float = TIMEOUT):
    try:
        response = requests.request(
            "GET" if payload is None else "POST",
            f"{RAG_URL}{path}",
            json=payload,
            timeout=timeout,
        )
        return response.status_code, response.json()
    except requests.RequestException as exc:
        raise IntegrationError("The shared RAG server is unavailable.") from exc
    except ValueError as exc:
        raise IntegrationError("The shared RAG server returned invalid JSON.") from exc