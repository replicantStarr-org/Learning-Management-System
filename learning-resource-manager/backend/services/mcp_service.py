import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

# The shared MCP server (mcp/server.py) runs on the host rather than in Docker,
# so from inside this container it is reached through host.docker.internal (see
# compose.yml).
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")

TIMEOUT_SECONDS = 10

class McpError(RuntimeError):
    """The MCP server could not be reached, or did not answer."""

class McpToolError(McpError):
    """The MCP server was reached, but the tool itself reported a failure."""

def _decode(value):
    """Tools return JSON as text, so it is parsed back into a value here."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return value

def _value(result):
    """The tool's return value, unwrapped from the MCP result around it.

    A tool that returns a string has it wrapped as {"result": "..."} in the
    structured content, so that wrapper is taken off too.
    """
    if result.structured_content is not None:
        value = _decode(result.structured_content)
        if isinstance(value, dict) and set(value) == {"result"}:
            return _decode(value["result"])
        return value

    texts = [item.text for item in result.content if isinstance(item, TextContent)]
    return _decode(texts[0]) if len(texts) == 1 else texts

async def _with_session(work):
    async with streamable_http_client(MCP_SERVER_URL) as streams:
        read_stream, write_stream = streams[:2]
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await work(session)

def _run(work):
    """Run work against a fresh MCP session.

    A session per call keeps this simple under gunicorn's sync workers, at the
    cost of a handshake each time.
    """
    try:
        return asyncio.run(_with_session(work))
    except Exception as exc:
        raise McpError("The MCP server is unavailable.") from exc

def list_tools():
    """Every tool the MCP server offers, as a model would see them."""
    async def work(session):
        result = await session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in result.tools
        ]

    return _run(work)

def call_tool(name, arguments=None):
    """The value the named tool returned.

    Only ever called with a tool name fixed in this backend, never one taken
    from the page, since the MCP server also holds other services' tools.
    """
    async def work(session):
        return await session.call_tool(name, arguments or {}, read_timeout_seconds=TIMEOUT_SECONDS)

    # Checked once the session has closed: raised inside it, the error would
    # come out wrapped in the client's ExceptionGroup and read as the server
    # being unavailable.
    result = _run(work)
    if not isinstance(result, CallToolResult):
        raise McpError("The MCP server returned an unsupported result.")
    if result.is_error:
        raise McpToolError(str(_value(result)))
    return _value(result)

def list_resources():
    """Every learning resource, with its tags, fetched through the MCP server."""
    return call_tool("learning_resources_list")

def list_tags():
    """Every tag in the library, by name, fetched through the MCP server."""
    return call_tool("learning_resources_tags_list")

def resources_by_tag(tag):
    """The learning resources carrying the tag, fetched through the MCP server."""
    return call_tool("learning_resources_by_tag", {"tag": tag})
