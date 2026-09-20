from functools import wraps

import requests
from flask import Blueprint, make_response, request

from services.ollama_client import OllamaError
from services.subject_service import (
    ServiceError,
    ask_question,
    create_subject,
    create_tag,
    delete_subject,
    delete_tag,
    get_or_create_summary,
    get_tag,
    list_subjects,
    list_tags,
    subject_page_data,
    update_subject,
    update_subject_tags,
    update_tag,
)
from views.html import (
    assigned_tags,
    error,
    message,
    question_result,
    subject_detail,
    subject_form,
    subject_list,
    tag_manager,
    tag_options,
    summary_result,
)


subjects_bp = Blueprint("subjects", __name__)


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
            response = make_response(error("The database service is unavailable."), 200)
            response.headers["HX-Error"] = "true"
            return response

    return wrapped


def subjects_changed(body, status=200, redirect=None):
    response = make_response(body, status)
    response.headers["HX-Trigger"] = "subjectsChanged"
    if redirect:
        response.headers["HX-Redirect"] = redirect
    return response


@subjects_bp.get("/subjects")
@handle_errors
def all_subjects():
    return subject_list(list_subjects())


@subjects_bp.get("/subjects/detail")
@handle_errors
def subject_detail_by_form():
    subject_id = request.args.get("subject_id", "")
    if not subject_id.isdigit():
        raise ServiceError("A valid subject ID is required")
    subject, tags = subject_page_data(int(subject_id))
    return subject_detail(subject, tags)


@subjects_bp.get("/subjects/<int:subject_id>")
@handle_errors
def subject_by_id(subject_id):
    subject, tags = subject_page_data(subject_id)
    return subject_detail(subject, tags)


@subjects_bp.get("/subjects/<int:subject_id>/edit")
@handle_errors
def subject_edit_form(subject_id):
    subject, tags = subject_page_data(subject_id)
    return subject_form(subject, tags)


@subjects_bp.post("/subjects")
@handle_errors
def add_subject():
    subject = create_subject(request.form.to_dict())
    return subjects_changed(
        message(f"{subject['code']} was created."),
        201,
        f"http://localhost:3001/subject.html?id={subject['subject_id']}",
    )


@subjects_bp.post("/subjects/update")
@handle_errors
def edit_subject():
    data = request.form.to_dict()
    subject_id = data.pop("subject_id", None)
    if not str(subject_id or "").isdigit():
        raise ServiceError("A valid subject ID is required")
    subject = update_subject(int(subject_id), data)
    return subjects_changed(
        message(f"{subject['code']} was updated."),
        redirect=f"http://localhost:3001/subject.html?id={subject['subject_id']}",
    )


@subjects_bp.post("/subjects/delete")
@handle_errors
def remove_subject():
    subject_id = request.form.get("subject_id", "")
    if not subject_id.isdigit():
        raise ServiceError("A valid subject ID is required")
    delete_subject(int(subject_id))
    return subjects_changed(
        "", redirect="http://localhost:3001/?message=Subject%20deleted."
    )


@subjects_bp.get("/tags")
@handle_errors
def all_tags():
    return tag_manager(None, list_tags())


@subjects_bp.get("/tags/<int:tag_id>")
@handle_errors
def tag_by_id(tag_id):
    return tag_manager(None, [get_tag(tag_id)])


@subjects_bp.post("/tags")
@handle_errors
def add_tag():
    tag = create_tag(request.form.get("name"))
    subject_id = request.form.get("subject_id", "")
    if subject_id.isdigit():
        subject, tags = subject_page_data(int(subject_id))
        update_subject_tags(
            int(subject_id),
            [item["tag_id"] for item in subject["tags"]] + [tag["tag_id"]],
        )
        subject, tags = subject_page_data(int(subject_id))
        return tag_options(subject, tags) + assigned_tags(subject, out_of_band=True)
    return message(f"{tag['name']} was created.")


@subjects_bp.post("/tags/update")
@handle_errors
def edit_tag():
    tag_id = request.form.get("tag_id", "")
    if not tag_id.isdigit():
        raise ServiceError("A valid tag ID is required")
    update_tag(int(tag_id), request.form.get("name"))
    subject_id = request.form.get("subject_id", "")
    if subject_id.isdigit():
        subject, tags = subject_page_data(int(subject_id))
        return tag_manager(subject, tags)
    return message("Tag was updated.")


@subjects_bp.post("/tags/delete")
@handle_errors
def remove_tag():
    tag_id = request.form.get("tag_id", "")
    if not tag_id.isdigit():
        raise ServiceError("A valid tag ID is required")
    delete_tag(int(tag_id))
    subject_id = request.form.get("subject_id", "")
    if subject_id.isdigit():
        subject, tags = subject_page_data(int(subject_id))
        return tag_manager(subject, tags)
    return message("Tag was deleted.")


@subjects_bp.post("/subjects/<int:subject_id>/tags")
@handle_errors
def edit_subject_tags(subject_id):
    update_subject_tags(subject_id, request.form.getlist("tag_ids"))
    subject, tags = subject_page_data(subject_id)
    return assigned_tags(subject)


@subjects_bp.post("/subjects/<int:subject_id>/summary")
@handle_errors
def subject_summary(subject_id):
    return summary_result(get_or_create_summary(subject_id))


@subjects_bp.post("/subjects/questions")
@handle_errors
def subject_question():
    subject_id = request.form.get("subject_id", "")
    if not subject_id.isdigit():
        raise ServiceError("A valid subject ID is required")
    return question_result(ask_question(int(subject_id), request.form.get("question")))
