from html import escape

from views.responses import BACKEND_BASE


STATUSES = ("Not Started", "In Progress", "Submitted", "Graded")
PRIORITIES = ("Low", "Medium", "High")

STATUS_CLASSES = {
    "Not Started": "bg-secondary-subtle text-secondary-emphasis border border-secondary-subtle",
    "In Progress": "bg-primary-subtle text-primary-emphasis border border-primary-subtle",
    "Submitted": "bg-success-subtle text-success-emphasis border border-success-subtle",
    "Graded": "bg-info-subtle text-info-emphasis border border-info-subtle",
}
PRIORITY_CLASSES = {
    "Low": "bg-light text-secondary border",
    "Medium": "bg-warning-subtle text-warning-emphasis border border-warning-subtle",
    "High": "bg-danger-subtle text-danger-emphasis border border-danger-subtle",
}


def escaped(value):
    return escape(str(value), quote=True)


def message(text):
    return f'<div class="alert alert-success mt-3" role="status">{escaped(text)}</div>'


def error(text):
    return f'<div class="alert alert-danger mt-3" role="alert">{escaped(text)}</div>'


def _status_badge(assignment):
    classes = STATUS_CLASSES.get(assignment.get("status"), "text-bg-secondary")
    return f'<span class="badge {classes}">{escaped(assignment.get("status", ""))}</span>'


def _priority_badge(assignment):
    classes = PRIORITY_CLASSES.get(assignment.get("priority"), "text-bg-secondary")
    return f'<span class="badge {classes}">{escaped(assignment.get("priority", ""))} priority</span>'


def _due_badge(assignment):
    days = assignment.get("days_until")
    label = escaped(assignment.get("due_label", assignment.get("due_at", "")))
    if assignment.get("is_overdue"):
        return f'<span class="badge text-bg-danger"><i class="bi bi-exclamation-triangle me-1"></i>Overdue &mdash; {label}</span>'
    if assignment.get("is_due_soon"):
        when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
        return f'<span class="badge text-bg-warning"><i class="bi bi-alarm me-1"></i>Due {when} &mdash; {label}</span>'
    return f'<span class="badge text-bg-light text-secondary border"><i class="bi bi-calendar-event me-1"></i>Due {label}</span>'


def subject_options(subjects):
    """Options only - each page supplies its own first option ("All subjects", "Choose a subject")."""
    if not subjects:
        return '<option value="" disabled>No subjects available - check the Subject Management service</option>'

    return "".join(
        f'<option value="{escaped(subject["subject_id"])}">'
        f'{escaped(subject["code"])} - {escaped(subject["name"])}</option>'
        for subject in subjects
    )


def _empty_state(title, body, action=""):
    return (
        f'<div class="text-center py-5"><h2 class="h4">{escaped(title)}</h2>'
        f'<p class="text-secondary">{escaped(body)}</p>{action}</div>'
    )


def assignment_list(assignments):
    if not assignments:
        return _empty_state(
            "No assignments match",
            "Try clearing the filters, or add an assignment to get started.",
            '<a class="btn btn-primary" href="/create.html">Add an assignment</a>',
        )

    cards = "".join(
        f"""
        <div class="col-md-6 col-lg-4">
            <a class="card feature-card subject-card shadow-sm text-decoration-none text-reset h-100"
               href="/assignment.html?id={escaped(assignment['assignment_id'])}">
                <div class="card-body d-flex flex-column">
                    <div class="d-flex flex-wrap gap-2 mb-2">
                        {_status_badge(assignment)}
                        {_priority_badge(assignment)}
                    </div>
                    <h2 class="h5">{escaped(assignment['title'])}</h2>
                    <p class="text-secondary small mb-2">{escaped(assignment['subject_name'])}</p>
                    <p class="small flex-grow-1">{escaped(assignment['description'][:140])}{'…' if len(assignment['description']) > 140 else ''}</p>
                    <div class="mt-2">{_due_badge(assignment)}</div>
                </div>
            </a>
        </div>
        """
        for assignment in assignments
    )
    count = len(assignments)
    return (
        f'<p class="text-secondary small mb-3">{count} assignment{"" if count == 1 else "s"}</p>'
        f'<div class="row g-4">{cards}</div>'
    )


def upcoming_list(assignments):
    if not assignments:
        return _empty_state("Nothing due", "You have no unfinished assignments in this window.")

    rows = "".join(
        f"""
        <a class="list-group-item list-group-item-action d-flex justify-content-between align-items-center flex-wrap gap-2"
           href="/assignment.html?id={escaped(assignment['assignment_id'])}">
            <span>
                <span class="fw-semibold d-block">{escaped(assignment['title'])}</span>
                <small class="text-secondary">{escaped(assignment['subject_name'])} &middot; {escaped(assignment['weighting'])}% of the unit</small>
            </span>
            <span class="d-flex gap-2 flex-wrap">{_priority_badge(assignment)}{_due_badge(assignment)}</span>
        </a>
        """
        for assignment in assignments
    )
    return f'<div class="list-group list-group-flush">{rows}</div>'


def reminders_list(reminders):
    if not reminders:
        return (
            '<div class="alert alert-light border" role="status">'
            '<i class="bi bi-bell-slash me-1"></i> No deadline notifications right now.</div>'
        )

    items = "".join(
        f"""
        <div class="alert {'alert-danger' if reminder.get('is_overdue') else 'alert-warning'} d-flex justify-content-between align-items-center flex-wrap gap-2"
             role="status">
            <span>
                <i class="bi bi-bell me-1" aria-hidden="true"></i>
                {escaped(reminder['message'])}
                <a class="alert-link ms-1" href="/assignment.html?id={escaped(reminder['assignment_id'])}">Open</a>
            </span>
            <button class="btn btn-sm btn-outline-dark" type="button"
                    hx-post="{BACKEND_BASE}/reminders/{escaped(reminder['reminder_id'])}/acknowledge"
                    hx-target="#notifications">Dismiss</button>
        </div>
        """
        for reminder in reminders
    )
    return items


def summary_result(summary):
    return f"""
    <div class="alert alert-primary mt-3">
        <p class="fw-semibold mb-1"><i class="bi bi-stars" aria-hidden="true"></i> AI summary</p>
        <p class="mb-1 preserve-lines">{escaped(summary['ai_response'])}</p>
        <small class="text-secondary">Generated by {escaped(summary['model'])} on {escaped(summary['created_at'])}</small>
    </div>
    """


def assignment_detail(assignment):
    assignment_id = escaped(assignment["assignment_id"])
    summary = assignment.get("summary")

    return f"""
    <div class="d-flex flex-column flex-md-row justify-content-between gap-3 mb-4">
        <div>
            <div class="d-flex flex-wrap gap-2 mb-2">
                {_status_badge(assignment)}{_priority_badge(assignment)}{_due_badge(assignment)}
            </div>
            <h1 class="display-6 fw-bold mb-2">{escaped(assignment['title'])}</h1>
            <p class="text-secondary mb-0">{escaped(assignment['subject_name'])} &middot; worth {escaped(assignment['weighting'])}% of the unit</p>
        </div>
        <div class="d-flex align-items-start gap-2">
            <a class="btn btn-outline-primary" href="/edit.html?id={assignment_id}">Edit</a>
            <button class="btn btn-outline-danger" type="button"
                    hx-delete="{BACKEND_BASE}/assignments/{assignment_id}"
                    hx-confirm="Delete this assignment permanently?">Delete</button>
        </div>
    </div>

    <section class="card border-0 shadow-sm mb-4">
        <div class="card-body p-4">
            <h2 class="h5">Description</h2>
            <p class="preserve-lines">{escaped(assignment['description'])}</p>
            <h2 class="h5 mt-4">Requirements</h2>
            <p class="preserve-lines mb-0">{escaped(assignment['requirements'])}</p>
        </div>
    </section>

    <section class="card border-0 shadow-sm mb-4">
        <div class="card-body p-4">
            <h2 class="h5">AI assistance</h2>
            <p class="text-secondary small">Summarise what this brief is asking for.</p>
            <div class="d-flex gap-2 flex-wrap">
                <button class="btn btn-primary" type="button"
                        hx-post="{BACKEND_BASE}/assignments/{assignment_id}/summary{'?force=true' if summary else ''}"
                        hx-target="#summary-result" hx-indicator="#summary-loading">
                    <i class="bi bi-stars me-1"></i> {'Regenerate summary' if summary else 'Summarise requirements'}
                </button>
                <span class="htmx-indicator" id="summary-loading" role="status"><span class="spinner-border spinner-border-sm"></span> Summarising…</span>
            </div>
            <div id="summary-result" aria-live="polite">{summary_result(summary) if summary else ''}</div>
        </div>
    </section>

    <a class="btn btn-outline-secondary" href="/">Back to all assignments</a>
    """


def _select(name, label, options, selected):
    choices = "".join(
        f'<option{" selected" if option == selected else ""}>{escaped(option)}</option>'
        for option in options
    )
    return f"""
    <label class="form-label" for="{name}">{escaped(label)}</label>
    <select class="form-select" id="{name}" name="{name}">{choices}</select>
    """


def assignment_edit_form(assignment):
    assignment_id = escaped(assignment["assignment_id"])
    # datetime-local needs the "T" separator that SQLite does not store.
    due_value = escaped(str(assignment["due_at"]).replace(" ", "T")[:16])

    return f"""
    <form hx-put="{BACKEND_BASE}/assignments/{assignment_id}" hx-target="#form-result">
        <div class="row g-3 mb-3">
            <div class="col-md-6">
                <label class="form-label" for="title">Title</label>
                <input class="form-control" id="title" name="title" maxlength="150"
                       value="{escaped(assignment['title'])}" required>
            </div>
            <div class="col-md-6">
                <label class="form-label" for="subject_name">Subject</label>
                <input class="form-control" id="subject_name" name="subject_name" maxlength="120"
                       value="{escaped(assignment['subject_name'])}" required>
            </div>
            <div class="col-md-4">
                <label class="form-label" for="due_at">Due</label>
                <input class="form-control" id="due_at" name="due_at" type="datetime-local"
                       value="{due_value}" required>
            </div>
            <div class="col-md-4">{_select("status", "Status", STATUSES, assignment.get("status"))}</div>
            <div class="col-md-4">{_select("priority", "Priority", PRIORITIES, assignment.get("priority"))}</div>
            <div class="col-md-4">
                <label class="form-label" for="weighting">Weighting (%)</label>
                <input class="form-control" id="weighting" name="weighting" type="number" min="0" max="100"
                       value="{escaped(assignment['weighting'])}" required>
            </div>
        </div>
        <div class="mb-3">
            <label class="form-label" for="description">Description</label>
            <textarea class="form-control" id="description" name="description" rows="3" maxlength="2000" required>{escaped(assignment['description'])}</textarea>
        </div>
        <div class="mb-4">
            <label class="form-label" for="requirements">Requirements</label>
            <textarea class="form-control" id="requirements" name="requirements" rows="5" maxlength="4000" required>{escaped(assignment['requirements'])}</textarea>
        </div>
        <div class="d-flex gap-2">
            <button class="btn btn-primary" type="submit">Save changes</button>
            <a class="btn btn-outline-secondary" href="/assignment.html?id={assignment_id}">Cancel</a>
        </div>
        <div id="form-result" aria-live="polite"></div>
    </form>
    """


def deleted_redirect(_payload):
    return ""


def created_message(assignment):
    return message(f'"{assignment["title"]}" was created.')


def updated_message(assignment):
    return message(f'"{assignment["title"]}" was updated.')
