from flask import Blueprint, request

from services.assignment_service import (
    create_assignment,
    delete_assignment,
    get_assignment,
    list_assignments,
    list_upcoming,
    update_assignment,
)
from services.subjects_client import list_subjects
from views.html import (
    assignment_detail,
    assignment_edit_form,
    assignment_list,
    created_message,
    deleted_redirect,
    subject_options,
    upcoming_list,
    updated_message,
)
from views.responses import FRONTEND_BASE, respond


assignments_bp = Blueprint("assignments", __name__)

CHANGED = "assignmentsChanged"


def payload():
    """Accept HTMX form posts and JSON API calls through the same handlers."""
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict()


@assignments_bp.get("/assignments")
def all_assignments():
    return respond(list_assignments(request.args.to_dict()), assignment_list)


@assignments_bp.get("/assignments/upcoming")
def upcoming_assignments():
    return respond(list_upcoming(request.args.get("days", "7")), upcoming_list)


@assignments_bp.get("/assignments/<int:assignment_id>")
def assignment_by_id(assignment_id):
    return respond(get_assignment(assignment_id), assignment_detail)


@assignments_bp.get("/assignments/<int:assignment_id>/edit")
def assignment_edit(assignment_id):
    return respond(get_assignment(assignment_id), assignment_edit_form)


@assignments_bp.post("/assignments")
def add_assignment():
    assignment = create_assignment(payload())
    return respond(
        assignment,
        created_message,
        status=201,
        trigger=CHANGED,
        redirect=f"{FRONTEND_BASE}/assignment.html?id={assignment['assignment_id']}",
    )


@assignments_bp.put("/assignments/<int:assignment_id>")
def edit_assignment(assignment_id):
    assignment = update_assignment(assignment_id, payload())
    return respond(assignment, updated_message, trigger=CHANGED)


@assignments_bp.delete("/assignments/<int:assignment_id>")
def remove_assignment(assignment_id):
    delete_assignment(assignment_id)
    return respond(
        {"assignment_id": assignment_id, "deleted": True},
        deleted_redirect,
        trigger=CHANGED,
        redirect=f"{FRONTEND_BASE}/?message=Assignment%20deleted.",
    )


@assignments_bp.get("/subjects/options")
def subject_dropdown_options():
    return respond(list_subjects(), subject_options)
