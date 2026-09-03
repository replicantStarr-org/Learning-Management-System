from flask import Blueprint, request

from services.assignment_service import acknowledge_reminder, list_reminders
from views.html import reminders_list
from views.responses import respond


reminders_bp = Blueprint("reminders", __name__)


@reminders_bp.get("/reminders")
def due_reminders():
    return respond(list_reminders(request.args.get("within_days", "14")), reminders_list)


@reminders_bp.post("/reminders/<int:reminder_id>/acknowledge")
def acknowledge(reminder_id):
    acknowledge_reminder(reminder_id)
    # Answer with the refreshed panel so dismissing one reminder repaints the rest.
    return respond(list_reminders(), reminders_list)
