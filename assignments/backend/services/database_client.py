import os

import requests

from services.errors import ServiceError, UpstreamError


DATABASE_URL = os.getenv("DATABASE_SERVICE_URL", "http://localhost:6003").rstrip("/")
TIMEOUT = float(os.getenv("DATABASE_TIMEOUT_SECONDS", "5"))


class DatabaseClient:
    """Thin HTTP wrapper over the assignment database microservice.

    Every method returns the decoded body and raises on failure, so the service layer
    never has to inspect status codes itself.
    """

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(method, f"{DATABASE_URL}{path}", timeout=TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise UpstreamError("The assignment database service is unavailable.") from exc

        if response.status_code == 204 or not response.content:
            return None

        try:
            body = response.json()
        except ValueError:
            body = {}

        if not response.ok:
            message = body.get("error") if isinstance(body, dict) else None
            raise ServiceError(
                message or "The assignment database service rejected the request",
                response.status_code,
                body if isinstance(body, dict) else None,
            )
        return body

    def list_assignments(self, filters=None):
        return self._request("GET", "/assignments", params=filters or None)

    def list_upcoming(self, days):
        return self._request("GET", "/assignments/upcoming", params={"days": days})

    def get_assignment(self, assignment_id):
        return self._request("GET", f"/assignments/{assignment_id}")

    def create_assignment(self, assignment):
        return self._request("POST", "/assignments", json=assignment)

    def update_assignment(self, assignment_id, assignment):
        return self._request("PUT", f"/assignments/{assignment_id}", json=assignment)

    def delete_assignment(self, assignment_id):
        return self._request("DELETE", f"/assignments/{assignment_id}")

    def store_summary(self, assignment_id, ai_response, model):
        return self._request(
            "POST",
            f"/assignments/{assignment_id}/summary",
            json={"ai_response": ai_response, "model": model},
        )

    def list_reminders(self, within_days=14):
        return self._request("GET", "/reminders", params={"within_days": within_days})

    def create_reminder(self, assignment_id, remind_at, message):
        return self._request(
            "POST",
            f"/assignments/{assignment_id}/reminders",
            json={"remind_at": remind_at, "message": message},
        )

    def acknowledge_reminder(self, reminder_id):
        return self._request("POST", f"/reminders/{reminder_id}/acknowledge")


database = DatabaseClient()
