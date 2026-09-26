"""The MCP server: the same pipeline as the HTTP server, as MCP tools over stdio.

Run from rag/ with: .venv_rag/bin/python -m server.mcp_server
"""

import sys

from mcp.server.fastmcp import FastMCP

from pipeline.ingestion import ingest_services as ingest_services_impl
from pipeline.querying import answer_question as answer_question_impl
from pipeline.querying import retrieve_context as retrieve_context_impl

mcp = FastMCP("Learning Hub RAG MCP")
AVAILABLE_TOOLS = ["ingest", "retrieve_context", "answer_question"]


@mcp.tool()
def ingest(service: str | None = None):
    """Re-index one service's records, or every configured service if none is given."""
    return ingest_services_impl(service)


@mcp.tool()
def retrieve_context(query: str, k: int | None = None, service: str | None = None):
    """Return the chunks closest to the query, optionally from one service only."""
    return retrieve_context_impl(query=query, k=k, service=service)


@mcp.tool()
def answer_question(query: str, k: int | None = None, service: str | None = None):
    """Answer the query from retrieved chunks using the local Ollama model."""
    return answer_question_impl(query=query, k=k, service=service)


if __name__ == "__main__":
    # stdout is the MCP protocol channel over stdio, so anything else printed
    # there corrupts it; human-facing messages go to stderr.
    print("Starting Learning Hub RAG MCP Server...", file=sys.stderr)
    print("Available tools: " + ", ".join(AVAILABLE_TOOLS), file=sys.stderr)
    mcp.run()
