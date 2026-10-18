import os

import requests

# Cross-feature reads go through Subjects' read-only public frontend proxy.
SUBJECTS_PUBLIC_URL = os.getenv("SUBJECTS_PUBLIC_SERVICE_URL", "http://localhost:3001/public").rstrip("/")
TIMEOUT = float(os.getenv("SUBJECTS_DATABASE_TIMEOUT_SECONDS", "3"))


def _get(path):
    try:
        response = requests.get(f"{SUBJECTS_PUBLIC_URL}{path}", timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def list_subjects():
    """Best-effort listing of subjects from the Subject Management feature.

    Returns an empty list rather than raising when that service is offline, so the
    assignment create/edit forms still render with a free-text subject fallback.
    """
    subjects = _get("/subjects")
    return subjects if isinstance(subjects, list) else []


def fetch_subject(subject_id):
    """Best-effort lookup of one subject; None when unavailable or not found."""
    subject = _get(f"/subjects/{subject_id}")
    return subject if isinstance(subject, dict) else None
