import asyncio
from sys import stderr

from mcp.server import MCPServer

from subjects_tools import register_subject_tools
from learning_resources_tools import register_learning_resource_tools
from timetable_tools import register_timetable_tools
from assignments_tools import register_assignment_tools

MCP_HOST = "127.0.0.1"
MCP_PORT = 8000

mcp = MCPServer("LMS MCP Server")


register_subject_tools(mcp)
register_learning_resource_tools(mcp)
register_timetable_tools(mcp)
register_assignment_tools(mcp)


# MCP server may use stdout for JSON-RPC messages
def log(message):
    print(message, file=stderr)

if __name__ == "__main__":
    tools = asyncio.run(mcp.list_tools())
    log(f"Available tools ({len(tools)}):")
    for tool in tools:
        log(f"  - {tool.name}")

    log(f"Starting LMS MCP Server on http://{MCP_HOST}:{MCP_PORT}/mcp...")
    mcp.run("streamable-http", host=MCP_HOST, port=MCP_PORT, streamable_http_path="/mcp")
