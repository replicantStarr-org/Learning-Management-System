from flask import Blueprint, jsonify, request
from markupsafe import escape

from services.resource_service import (
    ResourceError,
    create_resource,
    delete_resource,
    list_resource_cards,
    list_resources,
    list_tags,
)

resources_bp = Blueprint('resources', __name__)

@resources_bp.route('/all')
def get_all():
    return [tuple(row) for row in list_resources()]

@resources_bp.route('/all_html')
def get_all_html():
    rows = list_resource_cards()
    if not rows:
        return '<p class="text-secondary">No learning resources yet.</p>'

    return "".join(render_card(row) for row in rows)

@resources_bp.route('/tags_html')
def get_tags_html():
    return "".join(render_tag_choice(row) for row in list_tags())

@resources_bp.route('/upload', methods=['POST'])
def upload():
    known_tags = {str(row["tag_id"]) for row in list_tags()}
    tag_ids = [int(tag) for tag in request.form.getlist("tags") if tag in known_tags]

    try:
        resource_id = create_resource(
            request.files.get("file"),
            request.form.get("title"),
            request.form.get("author"),
            request.form.get("description"),
            tag_ids,
        )
    except ResourceError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"l_resource_id": resource_id}), 201

@resources_bp.route('/<int:resource_id>', methods=['DELETE'])
def remove(resource_id):
    try:
        delete_resource(resource_id)
    except ResourceError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify({"l_resource_id": resource_id})

def render_tag_choice(row):
    tag_id = escape(row["tag_id"])
    name = escape(row["name"])

    return f"""
        <label class="tag-choice">
            <input type="checkbox" name="tags" value="{tag_id}" class="form-check-input">
            <span>{name}</span>
        </label>
    """

def render_card(row):
    resource_id = escape(row["l_resource_id"])
    title = escape(row["title"])
    author = escape(row["author"] or "Unknown author")
    description = escape(row["description"] or "No description available.")
    location = escape(row["location"])

    return f"""
        <div class="col">
            <article class="card feature-card resource-card h-100" role="button" tabindex="0"
                     data-id="{resource_id}" data-title="{title}" data-author="{author}"
                     data-description="{description}" data-location="{location}">
                <div class="resource-thumb">
                    <canvas class="resource-thumb-canvas" data-location="{location}"></canvas>
                    <div class="resource-thumb-fallback small">Preview unavailable</div>
                </div>
                <div class="card-body d-flex flex-column">
                    <h2 class="card-title h6 mb-1">{title}</h2>
                    <p class="resource-author small mb-3">{author}</p>
                    <p class="resource-description small mb-0">{description}</p>
                </div>
            </article>
        </div>
    """
