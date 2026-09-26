"""An append-only JSON Lines log of every ingest, retrieval and answer."""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .common import BASE_DIR

AUDIT_PATH = BASE_DIR / "rag-audit.jsonl"


def append_audit(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any],
    outcome: str,
    start_time: float,
) -> None:
    record = {
        "request_id": str(uuid.uuid4()),
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output": tool_output,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": int((time.time() - start_time) * 1000),
        "outcome": outcome,
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
