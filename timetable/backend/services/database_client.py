import os

import requests


DATABASE_URL = os.getenv("DATABASE_SERVICE_URL", "http://timetable-database:6005").rstrip("/")
TIMEOUT = float(os.getenv("DATABASE_TIMEOUT_SECONDS", "5"))


class DatabaseClient:
    def _request(self, method, path, **kwargs):
        return requests.request(method, f"{DATABASE_URL}{path}", timeout=TIMEOUT, **kwargs)

    def list_entries(self, username, week_start=None, week_end=None):
        params = {"username": username}
        if week_start and week_end:
            params["week_start"] = week_start
            params["week_end"] = week_end
        return self._request("GET", "/timetable", params=params)

    def get_entry(self, timetable_id):
        return self._request("GET", f"/timetable/{timetable_id}")

    def create_entry(self, entry):
        return self._request("POST", "/timetable", json=entry)

    def update_entry(self, timetable_id, entry):
        return self._request("PUT", f"/timetable/{timetable_id}", json=entry)

    def delete_entry(self, timetable_id):
        return self._request("DELETE", f"/timetable/{timetable_id}")

    def latest_plan(self, username):
        return self._request("GET", "/timetable/plans/latest", params={"username": username})

    def create_plan(self, username, plan_text, suggested_entries=None):
        return self._request(
            "POST",
            "/timetable/plans",
            json={"username": username, "plan_text": plan_text, "suggested_entries": suggested_entries},
        )

    def update_plan(self, plan_id, plan_text, suggested_entries=None):
        return self._request(
            "PUT",
            f"/timetable/plans/{plan_id}",
            json={"plan_text": plan_text, "suggested_entries": suggested_entries},
        )

    def list_advice(self, username):
        return self._request("GET", "/timetable/advice", params={"username": username})

    def create_advice(self, username, question, advice_text):
        return self._request(
            "POST",
            "/timetable/advice",
            json={"username": username, "question": question, "advice_text": advice_text},
        )


database = DatabaseClient()
