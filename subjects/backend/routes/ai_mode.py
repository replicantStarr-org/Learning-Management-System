"""AI mode status and decorators for AI model-backed subject routes."""

from functools import wraps

from flask import Blueprint, jsonify, make_response

from services.ai_mode import DISABLED_MESSAGE, ai_mode_is_enabled
from views.html import error


ai_mode_bp = Blueprint("ai_mode", __name__)


def ai_mode_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not ai_mode_is_enabled():
            response = make_response(error(DISABLED_MESSAGE), 403)
            response.headers["HX-Error"] = "true"
            return response
        return view(*args, **kwargs)

    return wrapped


@ai_mode_bp.get("/ai-mode/status")
def ai_mode_status():
    enabled = ai_mode_is_enabled()
    return jsonify(
        enabled=enabled,
        ai_mode_enabled=enabled,
        message="AI mode is enabled." if enabled else DISABLED_MESSAGE,
    )
