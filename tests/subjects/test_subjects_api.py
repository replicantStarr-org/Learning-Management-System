"""Post-commit checks for two Subjects backend endpoint functions."""

from uuid import uuid4

import requests


def test_get_subjects_returns_200_and_json_list(api):
    """GET /api/v1/subjects -> api_list_subjects."""
    response = requests.get(api + "/subjects", timeout=5)

    assert response.status_code == 200, response.text
    subjects = response.json()
    assert isinstance(subjects, list)
    assert subjects, "Expected the disposable database's seeded subjects"
    assert all("subject_id" in subject and "code" in subject and "name" in subject for subject in subjects)


def test_post_subjects_returns_201_and_created_subject(api):
    """POST /api/v1/subjects -> api_create_subject."""
    payload = {
        "code": "TEST" + uuid4().hex[:12].upper(),
        "name": "Post-commit endpoint test",
        "description": "Disposable subject created by the CI/CD test.",
        "semester": "Spring",
        "coordinator": "CI test",
        "status": "Open",
    }
    response = requests.post(api + "/subjects", json=payload, timeout=5)
    created = response.json()
    subject_id = created.get("subject_id") if isinstance(created, dict) else None
    try:
        assert response.status_code == 201, response.text
        assert isinstance(subject_id, int) and subject_id > 0
        for field, value in payload.items():
            assert created[field] == value
    finally:
        if subject_id is not None:
            cleanup = requests.delete(f"{api}/subjects/{subject_id}", timeout=5)
            assert cleanup.status_code == 204, cleanup.text
