"""
MCP tools for the quiz manager.

The tools call the quiz database API. The quiz backend's routes return HTML
fragments for its pages, so the database API is the JSON view of the same
quizzes (the RAG connector reads it for the same reason).

Every tool is read-only. An MCP client can browse quizzes, questions and
attempt results, but cannot create, edit or delete a quiz, submit an attempt,
or run AI generation. Writes stay behind the backend's validation, and the
quiz pages remain the only way to change quiz data.

quizzes_student_results and quizzes_search_questions are MCP-only: no backend
route or page offers a cross-quiz view of one student or a question search.
"""

import json
import os
from typing import Any, Literal

import requests
from mcp.server.mcpserver.exceptions import ToolError


MAX_KEYWORD_LENGTH = 100
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
    if len(text) > MAX_KEYWORD_LENGTH:
        raise ToolError(f"{name} must be {MAX_KEYWORD_LENGTH} characters or fewer.")
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


def _percent(score: int, total: int) -> float:
    return round(100 * score / total, 1) if total else 0.0


def _attempt(attempt: dict) -> dict:
    # ai_feedback is model-written text, not a result, so it is left out.
    return {
        "attempt_id": attempt["attempt_id"],
        "quiz_id": attempt["quiz_id"],
        "student_name": attempt["student_name"],
        "score": attempt["score"],
        "total_questions": attempt["total_questions"],
        "percent": _percent(attempt["score"], attempt["total_questions"]),
        "completed_at": attempt["completed_at"],
    }


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
        quizzes = client.request("/quizzes")
        if subject and subject.strip():
            needle = subject.strip().lower()
            quizzes = [q for q in quizzes if needle in q["subject_name"].lower()]
        if difficulty:
            quizzes = [q for q in quizzes if q["difficulty"] == difficulty]
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
                    {
                        "question_id": question["question_id"],
                        "number": number,
                        "question_text": question["question_text"],
                        "answers": [answer["answer_text"] for answer in question["answers"]],
                        "correct_answer": next(
                            (a["answer_text"] for a in question["answers"] if a["is_correct"]),
                            None,
                        ),
                        "explanation": question["explanation"],
                    }
                    for number, question in enumerate(quiz["questions"], start=1)
                ],
            },
            ensure_ascii=False,
        )

    @mcp.tool(name="quizzes_attempts_list")
    def quizzes_attempts_list(quiz_id: int, student_name: str | None = None) -> str:
        """List the attempts made at one quiz, newest first, optionally for one
        student only (exact name, e.g. "Alice Nguyen")."""
        quiz_id = _positive_id(quiz_id, "quiz_id")
        params = {"student_name": student_name.strip()} if student_name and student_name.strip() else {}
        attempts = client.request(f"/quizzes/{quiz_id}/attempts", **params)
        return json.dumps([_attempt(a) for a in attempts], ensure_ascii=False)

    @mcp.tool(name="quizzes_student_results")
    def quizzes_student_results(student_name: str) -> str:
        """Summarise one student's results across every quiz: each attempt,
        their best score per quiz, and their average percentage.

        student_name matches ignoring case and surrounding spaces. MCP-only:
        the quiz pages show attempts one quiz at a time.
        """
        name = _required_text(student_name, "student_name").lower()
        attempts = []
        titles = {}
        for quiz in client.request("/quizzes"):
            titles[quiz["quiz_id"]] = quiz["title"]
            attempts.extend(
                a for a in client.request(f"/quizzes/{quiz['quiz_id']}/attempts")
                if a["student_name"].strip().lower() == name
            )
        if not attempts:
            raise ToolError(f"No quiz attempts exist for {student_name.strip()!r}.")

        attempts.sort(key=lambda a: (a["completed_at"] or "", a["attempt_id"]))
        best = {}
        for attempt in attempts:
            current = best.get(attempt["quiz_id"])
            if current is None or attempt["score"] > current["score"]:
                best[attempt["quiz_id"]] = attempt
        return json.dumps(
            {
                "student_name": attempts[0]["student_name"],
                "attempt_count": len(attempts),
                "quiz_count": len(best),
                "average_percent": round(
                    sum(_percent(a["score"], a["total_questions"]) for a in attempts) / len(attempts), 1
                ),
                "best_by_quiz": [
                    {"quiz_title": titles[quiz_id], **_attempt(attempt)}
                    for quiz_id, attempt in sorted(best.items())
                ],
                "attempts": [
                    {"quiz_title": titles[a["quiz_id"]], **_attempt(a)} for a in attempts
                ],
            },
            ensure_ascii=False,
        )

    @mcp.tool(name="quizzes_search_questions")
    def quizzes_search_questions(keyword: str) -> str:
        """Find questions across every quiz whose question text, answers or
        explanation contain keyword, ignoring case. Returns at most 25 matches.
        MCP-only: the quiz pages have no question search.
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
