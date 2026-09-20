import os
import re
from datetime import datetime, timezone

from services.database_client import database
from services.ollama_client import (
    BLOCKED_OUTPUT,
    answer_subject_question,
    summarise_subject,
)


SUBJECT_FIELDS = ("code", "name", "description", "semester", "coordinator", "status")
SUMMARY_MAX_AGE_HOURS = int(os.getenv("SUMMARY_MAX_AGE_HOURS", "168"))
INJECTION_PATTERN = re.compile(
    r"(ignore (all |any )?(previous|prior|system) instructions|system prompt|"
    r"reveal .{0,20}(secret|password|token)|<\|im_(start|end)\|>|jailbreak)",
    re.IGNORECASE,
)


class ServiceError(RuntimeError):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.status = status
        self.details = details


def _json(response, fallback="Database service request failed"):
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not response.ok:
        raise ServiceError(body.get("error", fallback), response.status_code, body)
    return body


def list_subjects():
    return _json(database.list_subjects())


def get_subject(subject_id):
    return _json(database.get_subject(subject_id))


def validate_subject(payload, partial=False):
    if not isinstance(payload, dict):
        raise ServiceError("Request body must be an object")
    missing = [] if partial else [field for field in SUBJECT_FIELDS if not str(payload.get(field, "")).strip()]
    if missing:
        raise ServiceError("All subject fields are required", details={"fields": missing})

    cleaned = {}
    limits = {"code": 20, "name": 120, "description": 5000, "semester": 60,
              "coordinator": 120, "status": 60}
    for field in SUBJECT_FIELDS:
        if field not in payload:
            continue
        value = str(payload[field]).strip()
        if not value:
            raise ServiceError(f"{field.replace('_', ' ').title()} cannot be empty")
        if len(value) > limits[field]:
            raise ServiceError(f"{field.replace('_', ' ').title()} is too long")
        cleaned[field] = value.upper() if field == "code" else value

    if not cleaned:
        raise ServiceError("At least one subject field is required")
    return cleaned


def create_subject(payload):
    return _json(database.create_subject(validate_subject(payload)), "Could not create subject")


def update_subject(subject_id, payload):
    result = _json(
        database.update_subject(subject_id, validate_subject(payload, partial=True)),
        "Could not update subject",
    )
    return result


def delete_subject(subject_id):
    response = database.delete_subject(subject_id)
    if not response.ok:
        _json(response, "Could not delete subject")


def list_tags():
    return _json(database.list_tags(), "Could not load tags")


def validate_tag_name(name):
    name = str(name or "").strip()
    if not name:
        raise ServiceError("Tag name cannot be empty")
    if len(name) > 120:
        raise ServiceError("Tag name must be 120 characters or fewer")
    return name


def get_tag(tag_id):
    return _json(database.get_tag(tag_id), "Could not load tag")


def create_tag(name):
    return _json(database.create_tag(validate_tag_name(name)), "Could not create tag")


def update_tag(tag_id, name):
    return _json(
        database.update_tag(tag_id, validate_tag_name(name)), "Could not update tag"
    )


def delete_tag(tag_id):
    response = database.delete_tag(tag_id)
    if not response.ok:
        _json(response, "Could not delete tag")


def update_subject_tags(subject_id, tag_ids):
    try:
        tag_ids = [int(tag_id) for tag_id in tag_ids]
    except (TypeError, ValueError):
        raise ServiceError("Tag IDs must be valid integers")
    return _json(
        database.replace_subject_tags(subject_id, tag_ids),
        "Could not update subject tags",
    )


def get_subject_tags(subject_id):
    return _json(database.get_subject_tags(subject_id), "Could not load subject tags")


def delete_subject_tag(subject_id, tag_id):
    response = database.delete_subject_tag(subject_id, tag_id)
    if not response.ok:
        _json(response, "Could not remove subject tag")


def subject_page_data(subject_id):
    subject = get_subject(subject_id)
    return subject, list_tags()


def _parse_timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _up_to_date_summary(subject):
    summaries = _json(database.list_summaries(subject["subject_id"]))
    if not summaries:
        return None

    subject_updated = _parse_timestamp(subject["last_update"])
    now = datetime.now(timezone.utc)
    latest_summary = summaries[0]
    created = _parse_timestamp(latest_summary["timestamp"])
    age_hours = (now - created).total_seconds() / 3600
    return latest_summary if created >= subject_updated and age_hours <= SUMMARY_MAX_AGE_HOURS else None


def get_or_create_summary(subject_id):
    subject = get_subject(subject_id)
    fresh = _up_to_date_summary(subject)
    if fresh:
        result = _json(database.get_summary(fresh["summary_id"]))
        result["reused"] = True
        return result

    subject_text = " ".join(str(subject.get(field, "")) for field in SUBJECT_FIELDS)
    if INJECTION_PATTERN.search(subject_text):
        raise ServiceError("The subject content was rejected as unsafe for summarisation", 422)
    answer = summarise_subject(subject)
    if BLOCKED_OUTPUT in answer:
        raise ServiceError("The AI rejected unsafe subject content", 422)
    result = _json(database.create_summary(subject_id, answer), "Could not store summary")
    result["reused"] = False
    return result


def ask_question(subject_id, question):
    question = str(question or "").strip()
    if not question:
        raise ServiceError("Question is required")
    if len(question) > 1000:
        raise ServiceError("Question must be 1000 characters or fewer")
    if INJECTION_PATTERN.search(question):
        raise ServiceError("That question cannot be processed safely", 422)
    answer = answer_subject_question(get_subject(subject_id), question)
    if BLOCKED_OUTPUT in answer:
        raise ServiceError("The AI rejected the question as unsafe", 422)
    return {"subject_id": subject_id, "question": question, "answer": answer}
