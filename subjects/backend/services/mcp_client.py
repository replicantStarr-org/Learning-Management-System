"""
Small MCP client used to expose MCP functionality to the app through the backend.

The subject application deliberately does not implement the query logic here.
It connects to the running MCP server and returns the result of the requested
MCP tool.
"""

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent


class MCPClientError(RuntimeError):
    """An error connecting to the MCP server or calling an MCP tool."""


MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
MCP_TIMEOUT_SECONDS = float(os.getenv("MCP_TIMEOUT_SECONDS", "10"))


def _decode_json_text(value: Any) -> Any:
    """Unwrap JSON returned as a string by an MCP tool."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value


def _content_to_value(result: CallToolResult) -> Any:
    """Unwrap the MCP result while preserving the returned JSON value."""
    if result.structured_content is not None:
        value = _decode_json_text(result.structured_content)
        if (
            isinstance(value, dict)
            and set(value) == {"result"}
            and isinstance(value["result"], str)
        ):
            return _decode_json_text(value["result"])
        return value

    values = [item.text for item in result.content if isinstance(item, TextContent)]
    if len(values) == 1:
        return _decode_json_text(values[0])
    return values


def _error_text(result: CallToolResult) -> str:
    value = _content_to_value(result)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


async def _call_tool_async(tool_name: str, arguments: dict[str, Any]) -> Any:
    try:
        async with streamable_http_client(MCP_SERVER_URL) as streams:
            read_stream, write_stream = streams[:2]
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    tool_name,
                    arguments,
                    read_timeout_seconds=MCP_TIMEOUT_SECONDS,
                )
                if not isinstance(result, CallToolResult):
                    raise MCPClientError("The MCP server returned an unsupported result.")
                if result.is_error:
                    raise MCPClientError(_error_text(result))
                return _content_to_value(result)
    except Exception as exc:
        raise MCPClientError(
            "The MCP server is unavailable or rejected the tool request."
        ) from exc


def call_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """Call one tool on the configured MCP server from a Flask route."""
    try:
        return asyncio.run(_call_tool_async(tool_name, arguments))
    except Exception as exc:
        raise MCPClientError("The MCP tool request could not be completed.") from exc
