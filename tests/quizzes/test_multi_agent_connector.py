"""Tests for the Quizzes evidence connector of the multi-agent server.

The connector is called with a fake HTTP layer, so no service has to run. The tests check
what the agents are allowed to see: quiz content only, never attempts, scores or student names.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "multi-agent-server"))

from connectors import CONNECTORS
from connectors import quizzes


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


QUIZ = {
    "quiz_id": 7, "subject_id": 1, "subject_name": "Databases", "title": "SQL basics",
    "description": "Joins and keys", "difficulty": "Easy", "question_count": 1, "source": "manual",
    "keywords": [{"keyword": "sql", "weight": 2}, {"keyword": "join", "weight": 1}],
}
QUIZ_WITH_QUESTIONS = {
    **QUIZ,
    "questions": [{
        "question_id": 11, "question_text": "What is a primary key?", "explanation": "It identifies a row.",
        "answers": [
            {"answer_id": 1, "answer_text": "A unique row identifier", "is_correct": 1},
            {"answer_id": 2, "answer_text": "A backup", "is_correct": 0},
        ],
    }],
}


@pytest.fixture
def fake_get(monkeypatch):
    calls = []

    def install(payload):
        def get(url, timeout):
            calls.append(url)
            return FakeResponse(payload)
        monkeypatch.setattr(quizzes.requests, "get", get)
        return calls

    return install


def test_connector_is_registered_for_the_quizzes_service():
    assert CONNECTORS["quizzes"] is quizzes.collect_evidence


def test_catalogue_evidence_has_keywords_but_no_questions(fake_get):
    calls = fake_get([QUIZ])
    result = quizzes.collect_evidence()
    assert calls == ["http://localhost:6004/quizzes"]
    assert result["evidence_count"] == 1
    entry = result["evidence"][0]
    assert entry["source"] == "quizzes:/quizzes/7"
    assert entry["fields"]["keywords"] == ["sql", "join"]
    assert "questions" not in entry["fields"]
    assert any("questions and answers are not included" in text for text in result["limitations"])


def test_single_quiz_evidence_includes_questions_and_correct_answers(fake_get):
    calls = fake_get(QUIZ_WITH_QUESTIONS)
    result = quizzes.collect_evidence(7)
    assert calls == ["http://localhost:6004/quizzes/7"]
    question = result["evidence"][0]["fields"]["questions"][0]
    assert question["question_text"] == "What is a primary key?"
    assert question["answers"][0] == {"answer_text": "A unique row identifier", "is_correct": True}


def test_connector_never_asks_for_attempts_or_student_data(fake_get):
    urls = fake_get(QUIZ_WITH_QUESTIONS)  # the fixture records every URL in one shared list
    quizzes.collect_evidence(7)
    fake_get([QUIZ])
    quizzes.collect_evidence()
    assert len(urls) == 2 and not any("attempt" in url for url in urls)


def test_connector_rejects_a_malformed_response(fake_get):
    fake_get([{"title": "No ID"}])
    with pytest.raises(ValueError):
        quizzes.collect_evidence()
