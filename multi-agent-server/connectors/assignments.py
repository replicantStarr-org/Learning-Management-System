"""Fetch authoritative assignment evidence through its database HTTP API."""

import os

import requests

FIELDS = (
    "assignment_id", "subject_id", "subject_name", "title", "description",
    "requirements", "due_at", "status", "priority", "weighting",
)
MAX_RECORDS = 50
MAX_TEXT = 2000


def collect_evidence(record_id=None) -> dict:
    base = os.getenv("ASSIGNMENTS_DATABASE_URL", "http://localhost:6003").rstrip("/")
    path = f"/assignments/{record_id}" if record_id is not None else "/assignments"
    response = requests.get(base + path, timeout=float(os.getenv("EVIDENCE_TIMEOUT_SECONDS", "10")))
    response.raise_for_status()
    payload = response.json()
    records = [payload] if record_id is not None else payload
    if not isinstance(records, list) or any(
        not isinstance(row, dict) or type(row.get("assignment_id")) is not int
        or not isinstance(row.get("title"), str) or not isinstance(row.get("requirements"), str)
        for row in records
    ):
        raise ValueError("Invalid Assignments evidence response")

    limitations = []
    if len(records) > MAX_RECORDS:
        limitations.append(f"Only the first {MAX_RECORDS} assignment records are included.")
    evidence = []
    for row in records[:MAX_RECORDS]:
        fields = {key: row[key] for key in FIELDS if key in row}
        for key, value in list(fields.items()):
            if isinstance(value, str) and len(value) > MAX_TEXT:
                fields[key] = value[:MAX_TEXT]
                limitations.append(f"Assignment {row['assignment_id']} field {key} was truncated.")
        evidence.append({
            "source": f"assignments:/assignments/{row['assignment_id']}",
            "fields": fields,
        })
    if not evidence:
        limitations.append("No assignment records were found.")
    return {"evidence": evidence, "evidence_count": len(evidence), "limitations": limitations}