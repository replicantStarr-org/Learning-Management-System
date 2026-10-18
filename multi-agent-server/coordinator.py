"""Evidence -> plan -> work -> independent review -> explicit human decision."""

import logging
import time
import uuid
from datetime import datetime, timezone

from agents.planner_agent import plan_workflow
from agents.worker_agent import generate_output
from agents.reviewer_agent import review_output
from connectors import CONNECTORS
from storage import LOCK, latest_workflows, read_jsonl, save_workflow

DECISIONS = ["Accept", "Partially Accept", "Reject"]


class WorkflowError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_workflow(service: str, user_request: str, record_id=None) -> dict:
    start = time.monotonic()
    workflow_id = str(uuid.uuid4())
    timestamp = now_iso()
    results = {
        f"{role}_result": {"status": "skipped", "agent": f"{role}_agent", "human_approval_required": True}
        for role in ("planner", "worker", "reviewer")
    }
    stage = "evidence"
    evidence = {"evidence": [], "evidence_count": 0, "limitations": []}
    error = None
    try:
        evidence = CONNECTORS[service](record_id)
        if not evidence["evidence_count"]:
            raise ValueError("No database evidence was found")
        stage = "planner"
        results["planner_result"] = plan_workflow(user_request, evidence)
        stage = "worker"
        results["worker_result"] = generate_output(user_request, results["planner_result"], evidence)
        stage = "reviewer"
        results["reviewer_result"] = review_output(user_request, results["planner_result"], results["worker_result"])
    except Exception as exc:
        logging.getLogger(__name__).exception("Workflow %s stage failed for %s", stage, service)
        error = f"{stage} failed ({type(exc).__name__}). Check the service logs and dependencies before retrying."
        if stage != "evidence":
            results[f"{stage}_result"] = {
                "status": "error", "agent": f"{stage}_agent", "error": error, "human_approval_required": True,
            }
        else:
            results["worker_result"].update(evidence=[], evidence_count=0)
    result = {
        "status": "error" if error else "success",
        "workflow_id": workflow_id,
        "service": service,
        "timestamp": timestamp,
        "duration_ms": int((time.monotonic() - start) * 1000),
        "user_request": user_request,
        "record_id": record_id,
        "evidence_result": evidence,
        "participating_agents": ["planner_agent", "worker_agent", "reviewer_agent"],
        **results,
        "human_decision": {"required": True, "status": "pending", "allowed_values": DECISIONS},
    }
    if error:
        result["error"] = error
    save_workflow(result, "workflow_completed" if not error else "workflow_failed")
    return result


def workflow_status(service: str) -> dict:
    with LOCK:
        records = [row for row in read_jsonl("workflow_history.jsonl") if row["service"] == service]
        return {
            "status": "success", "service": service,
            "workflow_history_count": len(records),
            "audit_record_count": sum(row["service"] == service for row in read_jsonl("coordination_audit.jsonl")),
            "latest_workflow": records[-1] if records else None,
        }


def get_workflow(service: str, workflow_id: str) -> dict:
    with LOCK:
        result = latest_workflows(service).get(workflow_id)
        if result is None:
            raise WorkflowError("Workflow not found for this service", 404)
        return result


def record_decision(service: str, workflow_id: str, decision: str, reviewer: str, reason: str, evidence_used: str) -> dict:
    with LOCK:
        result = get_workflow(service, workflow_id)
        if result["human_decision"]["status"] != "pending":
            raise WorkflowError("A human decision has already been recorded", 409)
        if result["status"] != "success" and decision != "Reject":
            raise WorkflowError("Failed workflows cannot be accepted; retry the workflow", 409)
        result["human_decision"] = {
            "required": True, "status": decision, "reviewer": reviewer,
            "reason": reason, "evidence_used": evidence_used, "timestamp": now_iso(),
        }
        save_workflow(result, "human_decision")
        return result
