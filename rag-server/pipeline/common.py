"""Settings and paths shared by every part of the pipeline."""

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


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path
