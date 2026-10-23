"""Fetch authoritative Timetable evidence through its database HTTP API.

The Timetable database lists entries per user, so catalogue evidence is built by
listing the users first and then each user's entries.
"""

import os

import requests

FIELDS = (
    "timetable_id", "username", "date", "day_of_week", "start_time", "end_time",
    "activity_name", "category", "notes", "ai_generated", "all_day",
)
MAX_RECORDS = 50
MAX_USERS = 20
MAX_TEXT = 2000


def _valid(row) -> bool:
    return (
        isinstance(row, dict)
        and type(row.get("timetable_id")) is int
        and isinstance(row.get("username"), str)
        and isinstance(row.get("date"), str)
        and isinstance(row.get("activity_name"), str)
    )


def collect_evidence(record_id=None) -> dict:
    base = os.getenv("TIMETABLE_DATABASE_URL", "http://localhost:6005").rstrip("/")
    timeout = float(os.getenv("EVIDENCE_TIMEOUT_SECONDS", "10"))
    limitations = []

    if record_id is not None:
        response = requests.get(f"{base}/timetable/{record_id}", timeout=timeout)
        if response.status_code == 404:
            return {
                "evidence": [], "evidence_count": 0,
                "limitations": [f"Timetable entry {record_id} was not found."],
            }
        response.raise_for_status()
        records = [response.json()]
    else:
        response = requests.get(base + "/timetable/users", timeout=timeout)
        response.raise_for_status()
        users = response.json()
        if not isinstance(users, list) or not all(isinstance(user, str) for user in users):
            raise ValueError("Invalid Timetable users response")
        if len(users) > MAX_USERS:
            limitations.append(f"Only the first {MAX_USERS} users' timetables are included.")
        records = []
        for username in users[:MAX_USERS]:
            response = requests.get(base + "/timetable", params={"username": username}, timeout=timeout)
            response.raise_for_status()
            entries = response.json()
            if not isinstance(entries, list):
                raise ValueError("Invalid Timetable entries response")
            records.extend(entries)

    if not all(_valid(row) for row in records):
        raise ValueError("Invalid Timetable evidence response")
    if len(records) > MAX_RECORDS:
        limitations.append(f"Only the first {MAX_RECORDS} timetable entries are included.")
    limitations.append("Evidence covers timetable entries only; saved AI plans and advice are not included.")

    evidence = []
    for row in records[:MAX_RECORDS]:
        fields = {key: row[key] for key in FIELDS if key in row}
        for key, value in list(fields.items()):
            if isinstance(value, str) and len(value) > MAX_TEXT:
                fields[key] = value[:MAX_TEXT]
                limitations.append(f"Timetable entry {row['timetable_id']} field {key} was truncated.")
        evidence.append({"source": f"timetable:/timetable/{row['timetable_id']}", "fields": fields})
    if not evidence:
        limitations.append("No timetable entries were found.")
    return {"evidence": evidence, "evidence_count": len(evidence), "limitations": limitations}
