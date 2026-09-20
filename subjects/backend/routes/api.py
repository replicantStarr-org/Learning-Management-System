from functools import wraps

import requests
from flask import Blueprint, jsonify, make_response, request

from services.subject_service import (
    ServiceError,
    create_subject,
    create_tag,
    delete_subject,
    delete_tag,
    delete_subject_tag,
    get_subject,
    get_subject_tags,
    get_tag,
    list_subjects,
    list_tags,
    update_subject,
    update_subject_tags,
    update_tag,
)


api_bp = Blueprint("subjects_api", __name__, url_prefix="/api/v1")


def _error(message, status=400, details=None):
    body = {"error": message}
    if details:
        body["details"] = details
    return jsonify(body), status


def _json_body():
    return request.get_json(silent=True)


def handle_api_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ServiceError as exc:
            return _error(str(exc), exc.status, exc.details)
        except requests.RequestException:
            return _error("The database service is unavailable.", 503)

    return wrapped


@api_bp.get("/subjects")
@handle_api_errors
def api_list_subjects():
    return jsonify(list_subjects())


@api_bp.get("/subjects/<int:subject_id>")
@handle_api_errors
def api_get_subject(subject_id):
    return jsonify(get_subject(subject_id))


@api_bp.post("/subjects")
@handle_api_errors
def api_create_subject():
    return jsonify(create_subject(_json_body())), 201


@api_bp.route("/subjects/<int:subject_id>", methods=["PATCH", "PUT"])
@handle_api_errors
def api_update_subject(subject_id):
    return jsonify(update_subject(subject_id, _json_body()))


@api_bp.delete("/subjects/<int:subject_id>")
@handle_api_errors
def api_delete_subject(subject_id):
    delete_subject(subject_id)
    return "", 204


@api_bp.get("/tags")
@handle_api_errors
def api_list_tags():
    return jsonify(list_tags())


@api_bp.get("/tags/<int:tag_id>")
@handle_api_errors
def api_get_tag(tag_id):
    return jsonify(get_tag(tag_id))


@api_bp.post("/tags")
@handle_api_errors
def api_create_tag():
    body = _json_body()
    name = body.get("name") if isinstance(body, dict) else None
    return jsonify(create_tag(name)), 201


@api_bp.put("/tags/<int:tag_id>")
@handle_api_errors
def api_update_tag(tag_id):
    body = _json_body()
    name = body.get("name") if isinstance(body, dict) else None
    return jsonify(update_tag(tag_id, name))


@api_bp.delete("/tags/<int:tag_id>")
@handle_api_errors
def api_delete_tag(tag_id):
    delete_tag(tag_id)
    return "", 204


@api_bp.get("/subjects/<int:subject_id>/tags")
@handle_api_errors
def api_get_subject_tags(subject_id):
    return jsonify(get_subject_tags(subject_id))


@api_bp.put("/subjects/<int:subject_id>/tags")
@handle_api_errors
def api_update_subject_tags(subject_id):
    body = _json_body()
    tag_ids = body.get("tag_ids") if isinstance(body, dict) else None
    return jsonify(update_subject_tags(subject_id, tag_ids))


@api_bp.delete("/subjects/<int:subject_id>/tags/<int:tag_id>")
@handle_api_errors
def api_delete_subject_tag(subject_id, tag_id):
    delete_subject_tag(subject_id, tag_id)
    return "", 204
