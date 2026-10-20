"""Fetch authoritative Learning Resources evidence through its backend HTTP API.

The Learning Resources database only accepts raw SQL, so evidence comes from the
backend's read-only catalogue instead. The catalogue carries every resource with
its tags, so a single record is found by filtering it rather than by a route.
"""

import os

import requests

FIELDS = ("l_resource_id", "title", "author", "medium", "description")
MAX_RECORDS = 50
MAX_TEXT = 2000
MAX_TAGS = 50
MAX_TAG_TEXT = 200


def _valid(row) -> bool:
    return (
        isinstance(row, dict)
        and type(row.get("l_resource_id")) is int
        and isinstance(row.get("title"), str)
        and isinstance(row.get("tags", []), list)
        and all(isinstance(tag, str) for tag in row.get("tags", []))
    )


def collect_evidence(record_id=None) -> dict:
    base = os.getenv("LEARNING_RESOURCES_API_URL", "http://localhost:5002/api/resources").rstrip("/")
    response = requests.get(
        base + "/catalogue", timeout=float(os.getenv("EVIDENCE_TIMEOUT_SECONDS", "10")),
    )
    response.raise_for_status()
    records = response.json()
    if not isinstance(records, list) or not all(_valid(row) for row in records):
        raise ValueError("Invalid Learning Resources evidence response")

    limitations = []
    if record_id is not None:
        records = [row for row in records if row["l_resource_id"] == record_id]
        if not records:
            limitations.append(f"Learning resource {record_id} was not found.")
    elif len(records) > MAX_RECORDS:
        limitations.append(f"Only the first {MAX_RECORDS} catalogue records are included.")
    limitations.append("Evidence covers catalogue metadata only; resource contents and highlights are not included.")

    evidence = []
    for row in records[:MAX_RECORDS]:
        resource_id = row["l_resource_id"]
        fields = {key: row[key] for key in FIELDS if key in row}
        for key, value in list(fields.items()):
            if isinstance(value, str) and len(value) > MAX_TEXT:
                fields[key] = value[:MAX_TEXT]
                limitations.append(f"Learning resource {resource_id} field {key} was truncated.")
        tags = row.get("tags", [])
        fields["tags"] = [tag[:MAX_TAG_TEXT] for tag in tags[:MAX_TAGS]]
        if len(tags) > MAX_TAGS or any(len(tag) > MAX_TAG_TEXT for tag in tags):
            limitations.append(f"Learning resource {resource_id} tags were truncated.")
        evidence.append({"source": f"resources:/api/resources/catalogue#{resource_id}", "fields": fields})
    if not evidence and record_id is None:
        limitations.append("No learning resource records were found.")
    return {"evidence": evidence, "evidence_count": len(evidence), "limitations": limitations}
