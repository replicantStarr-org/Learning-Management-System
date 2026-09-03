from services.assignment_service import INJECTION_PATTERN, get_assignment
from services.database_client import database
from services.errors import ServiceError
from services.ollama_client import summarise_assignment
from services.subjects_client import fetch_subject


def _subject_context(assignment):
    subject = fetch_subject(assignment.get("subject_id"))
    if not subject:
        return f"Subject: {assignment['subject_name']}"
    return (
        f"Subject: {subject['code']} - {subject['name']}\n"
        f"Subject description: {subject['description']}"
    )


def _assignment_context(assignment):
    context = (
        f"{_subject_context(assignment)}\n"
        f"Assignment title: {assignment['title']}\n"
        f"Description: {assignment['description']}\n"
        f"Requirements: {assignment['requirements']}\n"
        f"Due: {assignment['due_at']}\n"
        f"Weighting: {assignment['weighting']}% of the unit"
    )
    if INJECTION_PATTERN.search(context):
        raise ServiceError("This assignment's content was rejected as unsafe for AI processing.", 422)
    return context


def get_or_create_summary(assignment_id, force=False):
    """Return the cached summary, generating one first if there isn't one (or if forced).

    Caching matters here because the summary is read far more often than the brief changes,
    and a local model costs seconds per call.
    """
    assignment = get_assignment(assignment_id)
    if assignment.get("summary") and not force:
        return assignment["summary"]

    ai_response, model = summarise_assignment(_assignment_context(assignment))
    return database.store_summary(assignment_id, ai_response, model)
