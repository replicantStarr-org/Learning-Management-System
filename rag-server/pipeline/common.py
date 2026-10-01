"""Settings and paths shared by every part of the pipeline."""

import os
import tomllib
from functools import cache
from pathlib import Path
from typing import Any

# rag-server/, not rag-server/pipeline/: config and data live at the top.
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.toml"


@cache
def settings() -> dict[str, Any]:
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


TRUE_VALUES = {"1", "true", "yes", "on"}


def rag_is_enabled() -> bool:
    """Whether RAG_ENABLED lets clients use the RAG endpoints and MCP tools.

    Follows the hub's MCP_ENABLED switch (subjects/backend/routes/mcp.py). On
    unless set otherwise, since the learning resource manager relies on it; set
    RAG_ENABLED=false to switch it off. Read on every call, like MCP_ENABLED.
    """
    return os.getenv("RAG_ENABLED", "true").strip().lower() in TRUE_VALUES


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path
