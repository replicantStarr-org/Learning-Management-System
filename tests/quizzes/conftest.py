"""Shared fixtures for the quiz backend endpoint tests.

The tests call the running quiz backend over HTTP, the same way the frontend does,
so they need the quiz services up (docker compose up in quizzes/). Point them at a
different backend with QUIZ_BACKEND_URL.
"""

import os
import re

import pytest
import requests


BASE_URL = os.getenv("QUIZ_BACKEND_URL", "http://localhost:5004").rstrip("/")
TIMEOUT = 10


class QuizApi:
    """Thin helper around the quiz backend used by the endpoint tests."""

    def __init__(self, base_url):
        self.base_url = base_url
        self.created_quiz_ids = []

    def post(self, path, payload):
        return requests.post(f"{self.base_url}{path}", json=payload, timeout=TIMEOUT)

    def get(self, path):
        return requests.get(f"{self.base_url}{path}", timeout=TIMEOUT)

    def create_quiz(self, **overrides):
        payload = {
            "subject_id": 1,
            "subject_name": "Endpoint Tests",
            "title": "Endpoint test quiz",
            "description": "Created by the automated endpoint tests.",
            "difficulty": "Easy",
        }
        payload.update(overrides)
        response = self.post("/quizzes", payload)
        quiz_id = self.quiz_id_from(response)
        if quiz_id is not None:
            self.created_quiz_ids.append(quiz_id)
        return response

    @staticmethod
    def quiz_id_from(response):
        redirect = response.headers.get("HX-Redirect", "")
        match = re.search(r"quiz\.html\?id=(\d+)", redirect)
        return int(match.group(1)) if match else None

    def add_question(self, quiz_id, text, answers, correct_index):
        return self.post(
            f"/quizzes/{quiz_id}/questions",
            {
                "question_text": text,
                "explanation": f"Because {answers[correct_index]} is right.",
                "answers": [
                    {"text": answer, "is_correct": index == correct_index}
                    for index, answer in enumerate(answers)
                ],
            },
        )

    def answer_ids(self, quiz_id):
        """Map answer text to (question_id, answer_id) from the quiz-taking page."""
        page = self.get(f"/quizzes/{quiz_id}").text
        pattern = re.compile(
            r'name="q_(\d+)"\s+id="a_(\d+)" value="\d+" required>\s*'
            r'<label[^>]*>(.*?)</label>',
            re.S,
        )
        return {text: (int(q), int(a)) for q, a, text in pattern.findall(page)}

    def cleanup(self):
        for quiz_id in self.created_quiz_ids:
            requests.delete(f"{self.base_url}/quizzes/{quiz_id}", timeout=TIMEOUT)


@pytest.fixture
def api():
    helper = QuizApi(BASE_URL)
    try:
        requests.get(f"{BASE_URL}/", timeout=TIMEOUT).raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - environment problem
        pytest.fail(f"Quiz backend is not reachable at {BASE_URL}: {exc}")
    yield helper
    helper.cleanup()
