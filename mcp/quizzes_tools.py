"""
MCP tools for the quiz manager, a self-study tool for students.

The tools call the quiz database API. The quiz backend's routes return HTML
fragments for its pages, so the database API is the JSON view of the same
quizzes (the RAG connector reads it for the same reason).

Every tool is read-only and about the study material: finding quizzes,
reading a quiz's questions, searching questions by topic and drawing a
practice question. None of them returns attempts or scores, so no student can
look up another's results, and none can create, edit or delete a quiz,
submit an attempt or run AI generation; those stay on the quiz pages, behind
the backend's validation.

quizzes_search_questions and quizzes_practice_question are MCP-only: the quiz
pages have no question search and no single-question practice.
"""

import json
import os
import random
from typing import Any, Literal

import requests
from mcp.server.mcpserver.exceptions import ToolError


MAX_TEXT_LENGTH = 100
MAX_SEARCH_RESULTS = 25

Difficulty = Literal["Easy", "Medium", "Hard"]


class QuizzesApiError(ToolError):
    """An error returned by, or while reaching, the quiz database API.

    A ToolError, so the MCP SDK passes this message on to the caller rather
    than replacing it with a generic one.
    """


class QuizzesApiClient:
    def __init__(self):
        self.base_url = os.getenv(
            "QUIZZES_DATABASE_API_URL", "http://127.0.0.1:6004"
        ).rstrip("/")
        self.timeout = float(os.getenv("QUIZZES_DATABASE_API_TIMEOUT_SECONDS", "10"))

    def request(self, path: str, **params: Any) -> Any:
        try:
            response = requests.get(
                f"{self.base_url}{path}", params=params, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise QuizzesApiError(
                "The quiz service is unavailable. "
                "Make sure the quiz containers are running."
            ) from exc

        if not response.ok:
            try:
                message = response.json().get("error")
            except ValueError:
                message = None
            if response.status_code == 404:
                # Shown to the student as-is, such as "Quiz not found."
                raise QuizzesApiError(f"{message or 'Not found'}.")
            raise QuizzesApiError(
                f"HTTP {response.status_code}: {message or 'quiz database request failed'}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise QuizzesApiError("The quiz service returned invalid JSON.") from exc


def _positive_id(value: int, name: str) -> int:
    if value < 1:
        raise ToolError(f"{name} must be a positive integer.")
    return value


def _required_text(value: str, name: str) -> str:
    text = value.strip()
    if not text:
        raise ToolError(f"{name} is required.")
    if len(text) > MAX_TEXT_LENGTH:
        raise ToolError(f"{name} must be {MAX_TEXT_LENGTH} characters or fewer.")
    return text


def _summary(quiz: dict) -> dict:
    return {
        "quiz_id": quiz["quiz_id"],
        "title": quiz["title"],
        "subject_name": quiz["subject_name"],
        "difficulty": quiz["difficulty"],
        "question_count": quiz["question_count"],
        "source": quiz["source"],
    }


def _question(number: int, question: dict) -> dict:
    return {
        "question_id": question["question_id"],
        "number": number,
        "question_text": question["question_text"],
        "answers": [answer["answer_text"] for answer in question["answers"]],
        "correct_answer": next(
            (a["answer_text"] for a in question["answers"] if a["is_correct"]), None
        ),
        "explanation": question["explanation"],
    }


def _filtered(quizzes: list[dict], subject: str | None, difficulty: str | None) -> list[dict]:
    if subject and subject.strip():
        needle = subject.strip().lower()
        quizzes = [q for q in quizzes if needle in q["subject_name"].lower()]
    if difficulty:
        quizzes = [q for q in quizzes if q["difficulty"] == difficulty]
    return quizzes


def register_quiz_tools(mcp):
    client = QuizzesApiClient()

    @mcp.tool(name="quizzes_list")
    def quizzes_list(
        subject: str | None = None, difficulty: Difficulty | None = None
    ) -> str:
        """List quizzes, optionally filtered.

        subject matches part of the subject name or code, ignoring case
        (e.g. "DBS102" or "database"). difficulty is Easy, Medium or Hard.
        """
        quizzes = _filtered(client.request("/quizzes"), subject, difficulty)
        return json.dumps([_summary(q) for q in quizzes], ensure_ascii=False)

    @mcp.tool(name="quizzes_get")
    def quizzes_get(quiz_id: int) -> str:
        """Get one quiz by its quiz_id, with every question, its answer options,
        which option is correct, and the explanation."""
        quiz = client.request(f"/quizzes/{_positive_id(quiz_id, 'quiz_id')}")
        return json.dumps(
            {
                **_summary(quiz),
                "description": quiz["description"],
                "questions": [
                    _question(number, question)
                    for number, question in enumerate(quiz["questions"], start=1)
                ],
            },
            ensure_ascii=False,
        )

    @mcp.tool(name="quizzes_search_questions")
    def quizzes_search_questions(keyword: str) -> str:
        """Find questions across every quiz whose question text, answers or
        explanation contain keyword, ignoring case, to revise one topic.
        Returns at most 25 matches. MCP-only: the quiz pages have no question
        search.
        """
        needle = _required_text(keyword, "keyword").lower()
        matches = []
        for summary in client.request("/quizzes"):
            quiz = client.request(f"/quizzes/{summary['quiz_id']}")
            for number, question in enumerate(quiz["questions"], start=1):
                answers = [answer["answer_text"] for answer in question["answers"]]
                haystack = " ".join([question["question_text"], question["explanation"], *answers]).lower()
                if needle in haystack:
                    matches.append(
                        {
                            "quiz_id": quiz["quiz_id"],
                            "quiz_title": quiz["title"],
                            "subject_name": quiz["subject_name"],
                            "question_id": question["question_id"],
                            "number": number,
                            "question_text": question["question_text"],
                        }
                    )
        return json.dumps(
            {
                "keyword": keyword.strip(),
                "match_count": len(matches),
                "truncated": len(matches) > MAX_SEARCH_RESULTS,
                "matches": matches[:MAX_SEARCH_RESULTS],
            },
            ensure_ascii=False,
        )

    @mcp.tool(name="quizzes_practice_question")
    def quizzes_practice_question(
        subject: str | None = None, difficulty: Difficulty | None = None
    ) -> str:
        """Pick one random question to practise, optionally from quizzes on a
        subject (part of its name or code) or of a difficulty.

        The result includes the correct answer and explanation; a client
        quizzing the student should hold them back until the student has
        answered. MCP-only: the quiz pages only run whole quizzes.
        """
        quizzes = [
            q for q in _filtered(client.request("/quizzes"), subject, difficulty)
            if q["question_count"]
        ]
        if not quizzes:
            raise ToolError("No quizzes with questions match that subject and difficulty.")
        quiz = client.request(f"/quizzes/{random.choice(quizzes)['quiz_id']}")
        number, question = random.choice(list(enumerate(quiz["questions"], start=1)))
        return json.dumps(
            {
                "quiz_id": quiz["quiz_id"],
                "quiz_title": quiz["title"],
                "subject_name": quiz["subject_name"],
                "difficulty": quiz["difficulty"],
                **_question(number, question),
            },
            ensure_ascii=False,
        )
