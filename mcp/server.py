from mcp.server import MCPServer
from sys import stderr

from subjects_tools import register_subject_tools
from learning_resources_tools import register_learning_resource_tools

MCP_HOST = "127.0.0.1"
MCP_PORT = 8000

mcp = MCPServer("LMS MCP Server")


register_subject_tools(mcp)
register_learning_resource_tools(mcp)

@mcp.tool()
def echo(message: str) -> str:
    return message


# MCP server may use stdout for JSON-RPC messages
def log(message):
    print(message, file=stderr)

if __name__ == "__main__":
    log(f"Starting LMS MCP Server on http://{MCP_HOST}:{MCP_PORT}/mcp...")
    mcp.run("streamable-http", host=MCP_HOST, port=MCP_PORT, streamable_http_path="/mcp")
