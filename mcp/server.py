from mcp.server import MCPServer
from sys import stderr

mcp = MCPServer("LMS MCP Server")


@mcp.tool()
def echo(message: str) -> str:
    return message


# MCP server may use stdout for JSON-RPC messages
def log(message):
    print(message, file=stderr)

if __name__ == "__main__":
    log("Starting LMS MCP Server...")
    mcp.run()