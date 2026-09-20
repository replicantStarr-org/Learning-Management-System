import asyncio
import os
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
ECHO_MESSAGE = "agentic-loop-mcp-probe"


async def _probe(url: str) -> tuple[list[str], str]:
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [tool.name for tool in listed.tools]

            if "echo" not in names:
                raise RuntimeError("server did not advertise the required echo tool")

            result = await session.call_tool("echo", {"message": ECHO_MESSAGE})
            if result.is_error:
                raise RuntimeError("echo tool returned an error")
            if not result.content or not hasattr(result.content[0], "text"):
                raise RuntimeError("echo tool returned no text content")
            response = result.content[0].text
            if response != ECHO_MESSAGE:
                raise RuntimeError(f"echo returned {response!r}, expected {ECHO_MESSAGE!r}")
            return names, response


def collect(repo_root: Path, _service=None) -> tuple[bool, str]:
    server_dir = repo_root / "mcp"
    if not server_dir.is_dir():
        return False, f"MCP server directory is missing: {server_dir}"

    url = os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL).rstrip("/")
    try:
        names, response = asyncio.run(asyncio.wait_for(_probe(url), timeout=6.0))
    except Exception as exc:
        return False, (
            f"MCP server did not respond at {url}. Start ../mcp before running the review. "
            f"({type(exc).__name__}: {exc})"
        )

    return True, (
        f"MCP endpoint: {url}\n"
        f"Tools listed by the running server: {', '.join(names) or '(none)'}\n"
        f"Echo tool response: {response}"
    )
