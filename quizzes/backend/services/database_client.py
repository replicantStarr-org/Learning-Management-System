import os

import requests


DATABASE_URL = os.getenv("DATABASE_SERVICE_URL", "http://quiz-database:6004").rstrip("/")
TIMEOUT = float(os.getenv("DATABASE_TIMEOUT_SECONDS", "5"))


class DatabaseClient:
    def _request(self, method, path, **kwargs):
        return requests.request(method, f"{DATABASE_URL}{path}", timeout=TIMEOUT, **kwargs)

    def list_quizzes(self):
        return self._request("GET", "/quizzes")

    def get_quiz(self, quiz_id):
        return self._request("GET", f"/quizzes/{quiz_id}")

    def create_quiz(self, quiz):
        return self._request("POST", "/quizzes", json=quiz)

    def update_quiz(self, quiz_id, quiz):
        return self._request("PUT", f"/quizzes/{quiz_id}", json=quiz)

    def delete_quiz(self, quiz_id):
        return self._request("DELETE", f"/quizzes/{quiz_id}")

    def add_question(self, quiz_id, question):
        return self._request("POST", f"/quizzes/{quiz_id}/questions", json=question)

    def submit_attempt(self, quiz_id, attempt):
        return self._request("POST", f"/quizzes/{quiz_id}/attempts", json=attempt)

    def list_attempts(self, quiz_id, student_name=None):
        params = {"student_name": student_name} if student_name else None
        return self._request("GET", f"/quizzes/{quiz_id}/attempts", params=params)

    def get_attempt(self, attempt_id):
        return self._request("GET", f"/attempts/{attempt_id}")

    def store_attempt_feedback(self, attempt_id, ai_feedback):
        return self._request(
            "POST", f"/attempts/{attempt_id}/feedback", json={"ai_feedback": ai_feedback}
        )


database = DatabaseClient()
