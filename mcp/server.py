import os

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sys import stderr

from learning_resources_tools import register_learning_resource_tools
from subjects_tools import register_subject_tools

# All interfaces, like the RAG server: the learning resource manager's backend
# runs on a Docker bridge network and reaches the host through
# host.docker.internal, which a server bound to 127.0.0.1 never hears.
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT = 8000

# Binding beyond localhost turns off the SDK's default Host header check, so it
# is kept here with the containers' name for the host added to it.
TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", "host.docker.internal:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
)

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
    mcp.run(
        "streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        streamable_http_path="/mcp",
        transport_security=TRANSPORT_SECURITY,
    )
