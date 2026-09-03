from functools import wraps

import requests
from flask import Blueprint, make_response, request

from services.ollama_client import OllamaError
from services.timetable_service import (
    ServiceError,
    create_advice,
    create_entry,
    delete_entry,
    get_entry,
    get_or_create_plan,
    import_ical_schedule,
    list_entries,
    update_entry,
)
from views.html import (
    advice_result,
    entry_detail,
    entry_form,
    error,
    import_result,
    message,
    plan_result,
    weekly_grid,
)


timetable_bp = Blueprint("timetable", __name__)


def handle_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ServiceError as exc:
            response = make_response(error(str(exc)), 200)
            response.headers["HX-Error"] = "true"
            return response
        except OllamaError as exc:
            response = make_response(error(str(exc)), 200)
            response.headers["HX-Error"] = "true"
            return response
        except requests.RequestException:
            response = make_response(error("The timetable database service is unavailable."), 200)
            response.headers["HX-Error"] = "true"
            return response

    return wrapped


def timetable_changed(body, status=200, redirect=None):
    response = make_response(body, status)
    response.headers["HX-Trigger"] = "timetableChanged"
    if redirect:
        response.headers["HX-Redirect"] = redirect
    return response


@timetable_bp.get("/timetable")
@handle_errors
def weekly_timetable():
    username = request.args.get("username", "")
    entries, week_start, week_end = list_entries(username, request.args.get("week_start"))
    return weekly_grid(entries, week_start, week_end, username)


@timetable_bp.get("/timetable/<int:timetable_id>")
@handle_errors
def timetable_entry(timetable_id):
    return entry_detail(get_entry(timetable_id))


@timetable_bp.get("/timetable/<int:timetable_id>/edit")
@handle_errors
def timetable_entry_edit(timetable_id):
    return entry_form(get_entry(timetable_id))


@timetable_bp.post("/timetable")
@handle_errors
def add_entry():
    data = request.form.to_dict()
    username = data.pop("username", "")
    ai_generated = data.pop("ai_generated", "") in ("1", "true", "True")
    entry = create_entry(username, data, ai_generated=ai_generated)
    return timetable_changed(message(f"{entry['activity_name']} was added to your timetable."), 201)


@timetable_bp.post("/timetable/update")
@handle_errors
def edit_entry():
    data = request.form.to_dict()
    timetable_id = data.pop("timetable_id", None)
    if not str(timetable_id or "").isdigit():
        raise ServiceError("A valid timetable entry ID is required")
    update_entry(int(timetable_id), data)
    return timetable_changed(
        "", redirect="http://localhost:3005/?message=Timetable%20entry%20updated."
    )


@timetable_bp.post("/timetable/delete")
@handle_errors
def remove_entry():
    timetable_id = request.form.get("timetable_id", "")
    if not timetable_id.isdigit():
        raise ServiceError("A valid timetable entry ID is required")
    delete_entry(int(timetable_id))
    return timetable_changed(message("Timetable entry deleted."))


@timetable_bp.post("/timetable/ai-plan")
@handle_errors
def ai_plan():
    username = request.form.get("username", "")
    force = request.form.get("force") in ("1", "true", "True")
    plan = get_or_create_plan(username, force=force)
    return plan_result(plan, username)


@timetable_bp.post("/timetable/import-ical")
@handle_errors
def import_ical():
    username = request.form.get("username", "")
    ical_url = request.form.get("ical_url", "")
    category = request.form.get("category", "Class")
    result = import_ical_schedule(username, ical_url, category)
    return timetable_changed(import_result(result))


@timetable_bp.post("/timetable/ai-advice")
@handle_errors
def ai_advice():
    username = request.form.get("username", "")
    advice = create_advice(username, request.form.get("question"))
    return advice_result(advice)
