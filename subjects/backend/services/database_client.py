import os

import requests


DATABASE_URL = os.getenv("DATABASE_SERVICE_URL", "http://subject-database:6001").rstrip("/")
TIMEOUT = float(os.getenv("DATABASE_TIMEOUT_SECONDS", "5"))


class DatabaseClient:
    def _request(self, method, path, **kwargs):
        return requests.request(method, f"{DATABASE_URL}{path}", timeout=TIMEOUT, **kwargs)

    def list_subjects(self):
        return self._request("GET", "/subjects")

    def get_subject(self, subject_id):
        return self._request("GET", f"/subjects/{subject_id}")

    def create_subject(self, subject):
        return self._request("POST", "/subjects", json=subject)

    def update_subject(self, subject_id, subject):
        return self._request("PUT", f"/subjects/{subject_id}", json=subject)

    def delete_subject(self, subject_id):
        return self._request("DELETE", f"/subjects/{subject_id}")

    def list_summaries(self, subject_id):
        return self._request("GET", f"/subjects/{subject_id}/summaries")

    def get_summary(self, summary_id):
        return self._request("GET", f"/summaries/{summary_id}")

    def create_summary(self, subject_id, response):
        return self._request(
            "POST", f"/subjects/{subject_id}/summaries", json={"ai_response": response}
        )


database = DatabaseClient()
