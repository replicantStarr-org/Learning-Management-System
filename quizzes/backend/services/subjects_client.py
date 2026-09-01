import os

import requests

# Cross-feature read: per the top-level design.md integration rule, other features may only be
# queried through their database service's CRUD API, never through direct DB access.
SUBJECTS_DATABASE_URL = os.getenv("SUBJECTS_DATABASE_SERVICE_URL", "http://localhost:6001").rstrip("/")
TIMEOUT = float(os.getenv("SUBJECTS_DATABASE_TIMEOUT_SECONDS", "3"))


def list_subjects():
    """Best-effort listing of subjects from the Subject Management feature.

    Returns an empty list (rather than raising) when the subjects service is unreachable, so
    the quiz feature's create/generate forms still render without a working dropdown.
    """
    try:
        response = requests.get(f"{SUBJECTS_DATABASE_URL}/subjects", timeout=TIMEOUT)
    except requests.RequestException:
        return []
    if not response.ok:
        return []
    try:
        subjects = response.json()
    except ValueError:
        return []
    return subjects if isinstance(subjects, list) else []


def fetch_subject(subject_id):
    """Best-effort lookup of a subject from the Subject Management feature.

    Returns None (rather than raising) when the subjects service is unreachable or the
    subject does not exist, so quiz generation still works if that feature is offline.
    """
    try:
        response = requests.get(f"{SUBJECTS_DATABASE_URL}/subjects/{subject_id}", timeout=TIMEOUT)
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    try:
        return response.json()
    except ValueError:
        return None
