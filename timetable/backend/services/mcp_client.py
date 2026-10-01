"""Client for the shared MCP server, used by the backend's /mcp routes.

The timetable tools live on the MCP server (mcp/timetable_tools.py); the
backend only connects to it and returns the tool's result, so the page reaches
MCP through the backend like every other feature.
"""

import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent


MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
MCP_TIMEOUT_SECONDS = float(os.getenv("MCP_TIMEOUT_SECONDS", "10"))

TRUE_VALUES = {"1", "true", "yes", "on"}


class MCPError(RuntimeError):
    pass


class MCPToolError(MCPError):
    """The tool ran and refused the request, such as an unknown username."""


def mcp_is_enabled():
    return os.getenv("MCP_ENABLED", "false").strip().lower() in TRUE_VALUES


def _text(result):
    return "\n".join(item.text for item in result.content if isinstance(item, TextContent))


async def _call_tool_async(tool_name, arguments):
    async with streamable_http_client(MCP_SERVER_URL) as streams:
        read_stream, write_stream = streams[:2]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                tool_name, arguments, read_timeout_seconds=MCP_TIMEOUT_SECONDS
            )

    if not isinstance(result, CallToolResult):
        raise MCPError("The MCP server returned an unsupported result.")
    if result.is_error:
        raise MCPToolError(_text(result) or f"{tool_name} failed.")
    try:
        return json.loads(_text(result))
    except ValueError as exc:
        raise MCPError(f"{tool_name} returned a result that is not JSON.") from exc


def call_tool(tool_name, arguments=None):
    try:
        return asyncio.run(_call_tool_async(tool_name, arguments or {}))
    except MCPError:
        raise
    except Exception as exc:
        raise MCPError(
            "The MCP server is unavailable. Make sure it is running on the host."
        ) from exc
