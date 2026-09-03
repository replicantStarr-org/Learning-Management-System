import re
from datetime import datetime, timedelta

from services.database_client import database
from services.errors import ServiceError


REQUIRED_FIELDS = ("subject_id", "subject_name", "title", "description", "requirements", "due_at")
OPTIONAL_FIELDS = ("status", "priority", "weighting")
STATUSES = ("Not Started", "In Progress", "Submitted", "Graded")
PRIORITIES = ("Low", "Medium", "High")
LENGTH_LIMITS = {"subject_name": 120, "title": 150, "description": 2000, "requirements": 4000}
MAX_WINDOW_DAYS = 90
DEFAULT_REMINDER_LEAD_DAYS = 3

DATE_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
STORED_FORMAT = "%Y-%m-%d %H:%M:%S"

# Reused for any free text that later reaches the model, so an injected brief is rejected at
# the boundary rather than at generation time.
INJECTION_PATTERN = re.compile(
    r"(ignore (all |any )?(previous|prior|system) instructions|system prompt|"
    r"reveal .{0,20}(secret|password|token)|<\|im_(start|end)\|>|jailbreak)",
    re.IGNORECASE,
)


def parse_due_at(value):
    raw = str(value or "").strip()
    for date_format in DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, date_format)
        except ValueError:
            continue
        if date_format == "%Y-%m-%d":
            parsed = parsed.replace(hour=23, minute=59)
        return parsed
    raise ServiceError("Due date must be a valid date and time")


def _text(field, value):
    value = str(value).strip()
    if not value:
        raise ServiceError(f"{field.replace('_', ' ').title()} cannot be empty")
    if len(value) > LENGTH_LIMITS[field]:
        raise ServiceError(f"{field.replace('_', ' ').title()} is too long")
    return value


def validate_assignment(payload, partial=False):
    if not isinstance(payload, dict):
        raise ServiceError("Request body must be an object")

    if not partial:
        missing = [field for field in REQUIRED_FIELDS if not str(payload.get(field, "")).strip()]
        if missing:
            raise ServiceError("All assignment fields are required", details={"fields": missing})

    cleaned = {}
    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        if field not in payload or str(payload[field]).strip() == "":
            continue

        if field == "subject_id":
            raw = str(payload[field]).strip()
            if not raw.isdigit():
                raise ServiceError("Subject ID must be a positive number")
            cleaned[field] = int(raw)
        elif field == "due_at":
            cleaned[field] = parse_due_at(payload[field]).strftime(STORED_FORMAT)
        elif field == "status":
            cleaned[field] = _one_of(payload[field], STATUSES, "Status")
        elif field == "priority":
            cleaned[field] = _one_of(payload[field], PRIORITIES, "Priority")
        elif field == "weighting":
            raw = str(payload[field]).strip()
            if not raw.isdigit() or int(raw) > 100:
                raise ServiceError("Weighting must be a whole number between 0 and 100")
            cleaned[field] = int(raw)
        else:
            cleaned[field] = _text(field, payload[field])

    if not cleaned:
        raise ServiceError("At least one assignment field is required")
    return cleaned


def _one_of(value, allowed, label):
    value = str(value or "").strip().title()
    if value not in allowed:
        raise ServiceError(f"{label} must be one of: {', '.join(allowed)}")
    return value


def annotate(assignment):
    """Add the derived deadline fields the list, detail and reminder views all need."""
    try:
        due = datetime.strptime(assignment["due_at"], STORED_FORMAT)
    except (KeyError, TypeError, ValueError):
        return assignment

    remaining = due - datetime.now()
    days = remaining.days if remaining.total_seconds() >= 0 else -((-remaining).days + 1)
    finished = assignment.get("status") in ("Submitted", "Graded")

    assignment["due_label"] = due.strftime("%a %d %b %Y, %H:%M")
    assignment["days_until"] = days
    assignment["is_overdue"] = remaining.total_seconds() < 0 and not finished
    assignment["is_due_soon"] = 0 <= remaining.total_seconds() and days <= 3 and not finished
    return assignment


def list_assignments(filters=None):
    allowed = ("subject_id", "status", "priority", "q")
    query = {
        key: str(value).strip()
        for key, value in (filters or {}).items()
        if key in allowed and str(value).strip()
    }
    if "q" in query and len(query["q"]) > 100:
        raise ServiceError("Search text is too long")
    if "status" in query:
        query["status"] = _one_of(query["status"], STATUSES, "Status")
    if "priority" in query:
        query["priority"] = _one_of(query["priority"], PRIORITIES, "Priority")

    return [annotate(assignment) for assignment in database.list_assignments(query)]


def _days(value, default):
    raw = str(value or default).strip()
    if not raw.isdigit() or not (1 <= int(raw) <= MAX_WINDOW_DAYS):
        raise ServiceError(f"Days must be a whole number between 1 and {MAX_WINDOW_DAYS}")
    return int(raw)


def list_upcoming(days=7):
    return [annotate(assignment) for assignment in database.list_upcoming(_days(days, 7))]


def get_assignment(assignment_id):
    return annotate(database.get_assignment(assignment_id))


def create_assignment(payload):
    assignment = database.create_assignment(validate_assignment(payload))
    _schedule_default_reminder(assignment)
    return annotate(assignment)


def update_assignment(assignment_id, payload):
    return annotate(database.update_assignment(assignment_id, validate_assignment(payload, partial=True)))


def delete_assignment(assignment_id):
    database.delete_assignment(assignment_id)


def _schedule_default_reminder(assignment):
    """Every new assignment gets one reminder, three days before it is due.

    A reminder for an assignment that is already due sooner than that fires immediately, so
    short-notice work still shows up in the notifications panel.
    """
    due = datetime.strptime(assignment["due_at"], STORED_FORMAT)
    remind_at = max(due - timedelta(days=DEFAULT_REMINDER_LEAD_DAYS), datetime.now())
    database.create_reminder(
        assignment["assignment_id"],
        remind_at.strftime(STORED_FORMAT),
        f"\"{assignment['title']}\" is due on {due.strftime('%d %b %Y')}.",
    )


def list_reminders(within_days=14):
    return [annotate(reminder) for reminder in database.list_reminders(_days(within_days, 14))]


def acknowledge_reminder(reminder_id):
    database.acknowledge_reminder(reminder_id)
