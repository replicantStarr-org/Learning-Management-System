from flask import Blueprint, request

from services.ai_service import get_or_create_summary
from views.html import summary_result
from views.responses import respond


ai_bp = Blueprint("ai", __name__)


def _forced():
    """A repeat press of the button regenerates rather than replaying the cache."""
    return request.args.get("force", "").lower() == "true"


@ai_bp.post("/assignments/<int:assignment_id>/summary")
def generate_summary(assignment_id):
    return respond(get_or_create_summary(assignment_id, _forced()), summary_result)
