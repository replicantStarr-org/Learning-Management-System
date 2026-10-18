"""Append-only JSONL snapshots and audit events with concurrency support."""

import json
import os
from pathlib import Path
from threading import RLock

LOCK = RLock()


def data_dir() -> Path:
    return Path(os.getenv("MULTI_AGENT_DATA_DIR", str(Path(__file__).resolve().parent)))


def read_jsonl(name: str) -> list[dict]:
    path = data_dir() / name
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def append_jsonl(name: str, record: dict) -> None:
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / name).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def latest_workflows(service: str) -> dict[str, dict]:
    latest = {}
    for record in read_jsonl("workflow_history.jsonl"):
        if record["service"] == service:
            latest[record["workflow_id"]] = record
    return latest


def save_workflow(result: dict, event: str) -> None:
    with LOCK:
        append_jsonl("workflow_history.jsonl", result)
        append_jsonl("coordination_audit.jsonl", {
            "event": event,
            "workflow_id": result["workflow_id"],
            "service": result["service"],
            "timestamp": result.get("human_decision", {}).get("timestamp", result["timestamp"]),
            "status": result["status"],
            "duration_ms": result["duration_ms"],
            "participating_agents": result["participating_agents"],
            "human_approval_required": True,
            "worker_status": result["worker_result"]["status"],
            "agent_statuses": {
                role: result[f"{role}_result"]["status"] for role in ("planner", "worker", "reviewer")
            },
            "evidence_count": result["worker_result"].get("evidence_count", 0),
            "human_decision": result["human_decision"],
        })
