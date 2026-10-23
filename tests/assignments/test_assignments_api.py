"""Post-commit checks for two Assignments backend endpoint functions."""

import os
from uuid import uuid4

import requests

BACKEND = os.getenv("ASSIGNMENTS_BACKEND_URL", "http://127.0.0.1:5003").rstrip("/")


def test_get_assignments_lists_seeded_records():
    """GET /assignments -> all_assignments."""
    response = requests.get(f"{BACKEND}/assignments", timeout=5)

    assert response.status_code == 200, response.text
    assignments = response.json()
    assert isinstance(assignments, list)
    assert assignments
    assert all("assignment_id" in row and "title" in row for row in assignments)


def test_post_assignments_creates_record():
    """POST /assignments -> add_assignment."""
    payload = {
        "subject_id": 1,
        "subject_name": "ASD101 - Advanced Software Development",
        "title": f"CI endpoint test {uuid4().hex[:10]}",
        "description": "Disposable record created by endpoint testing.",
        "requirements": "Created and deleted by this test.",
        "due_at": "2099-01-01 09:00:00",
        "priority": "Low",
        "weighting": 5,
    }
    response = requests.post(f"{BACKEND}/assignments", json=payload, timeout=5)
    created = response.json()
    assignment_id = created.get("assignment_id") if isinstance(created, dict) else None
    try:
        assert response.status_code == 201, response.text
        assert isinstance(assignment_id, int) and assignment_id > 0
        for field, value in payload.items():
            assert created[field] == value
    finally:
        if assignment_id is not None:
            cleanup = requests.delete(f"{BACKEND}/assignments/{assignment_id}", timeout=5)
            assert cleanup.status_code == 200, cleanup.text