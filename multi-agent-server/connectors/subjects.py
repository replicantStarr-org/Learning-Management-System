"""Fetch authoritative Subjects evidence through its database HTTP API."""

import os

import requests

FIELDS = ("subject_id", "code", "name", "description", "semester", "coordinator", "status")
MAX_RECORDS = 50
MAX_TEXT = 2000


def collect_evidence(record_id=None) -> dict:
    base = os.getenv("SUBJECTS_DATABASE_URL", "http://localhost:6001").rstrip("/")
    path = f"/subjects/{record_id}" if record_id is not None else "/subjects"
    response = requests.get(
        base + path, timeout=float(os.getenv("EVIDENCE_TIMEOUT_SECONDS", "10")),
    )
    response.raise_for_status()
    payload = response.json()
    records = [payload] if record_id is not None else payload
    if not isinstance(records, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("subject_id"), int)
        or not isinstance(row.get("code"), str) or not isinstance(row.get("name"), str)
        for row in records
    ):
        raise ValueError("Invalid Subjects evidence response")
    limitations = []
    if record_id is None:
        limitations.append("Catalogue evidence contains codes, names and tags only; descriptions, semesters, coordinators and statuses are not included.")
    if len(records) > MAX_RECORDS:
        limitations.append(f"Only the first {MAX_RECORDS} catalogue records are included.")
    evidence = []
    for row in records[:MAX_RECORDS]:
        fields = {key: row[key] for key in FIELDS if key in row}
        for key, value in list(fields.items()):
            if isinstance(value, str) and len(value) > MAX_TEXT:
                fields[key] = value[:MAX_TEXT]
                limitations.append(f"Subject {row['subject_id']} field {key} was truncated.")
        tags = row.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, dict) or not isinstance(tag.get("name"), str) for tag in tags):
            raise ValueError("Invalid Subjects tags response")
        fields["tags"] = [tag["name"][:200] for tag in tags[:50]]
        if len(tags) > 50 or any(len(tag["name"]) > 200 for tag in tags):
            limitations.append(f"Subject {row['subject_id']} tags were truncated.")
        evidence.append({"source": f"subjects:/subjects/{row['subject_id']}", "fields": fields})
    if not evidence:
        limitations.append("No subject records were found.")
    return {"evidence": evidence, "evidence_count": len(evidence), "limitations": limitations}
