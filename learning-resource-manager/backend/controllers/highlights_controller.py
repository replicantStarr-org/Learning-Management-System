from flask import Blueprint, jsonify, request

from services.highlight_service import (
    COLOURS,
    HighlightError,
    create_highlight,
    delete_highlight,
    list_for_resource,
    list_summary_for_resource,
)

highlights_bp = Blueprint('highlights', __name__)

@highlights_bp.route('/colours')
def colours():
    return jsonify({"colours": sorted(COLOURS)})

@highlights_bp.route('/resource/<int:resource_id>')
def for_resource(resource_id):
    return jsonify({"highlights": list_for_resource(resource_id)})

@highlights_bp.route('/resource/<int:resource_id>/summary')
def summary_for_resource(resource_id):
    return jsonify({"highlights": list_summary_for_resource(resource_id)})

@highlights_bp.route('', methods=['POST'])
def create():
    payload = request.get_json(silent=True) or {}

    try:
        resource_id = int(payload.get("l_resource_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "A resource is required."}), 400

    try:
        highlight_id = create_highlight(
            resource_id,
            payload.get("name"),
            payload.get("colour"),
            payload.get("quote"),
            payload.get("rects"),
        )
    except HighlightError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"l_resource_highlight_id": highlight_id}), 201

@highlights_bp.route('/<int:highlight_id>', methods=['DELETE'])
def remove(highlight_id):
    try:
        delete_highlight(highlight_id)
    except HighlightError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify({"l_resource_highlight_id": highlight_id})
