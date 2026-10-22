"""Fetch authoritative Quizzes study material through its database HTTP API.

Only quiz content is read: titles, descriptions, keywords, questions, answer options
and explanations. Attempts, scores and student names are never requested, so a
workflow cannot expose how any student performed.
"""

import os

import requests

CATALOGUE_FIELDS = (
    "quiz_id", "subject_id", "subject_name", "title", "description", "difficulty", "question_count", "source",
)
MAX_RECORDS = 50
MAX_QUESTIONS = 30
MAX_KEYWORDS = 10
MAX_TEXT = 2000


def _text(value):
    return value[:MAX_TEXT] if isinstance(value, str) else value


def _keywords(row, limitations):
    keywords = row.get("keywords", [])
    if not isinstance(keywords, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("keyword"), str) for item in keywords
    ):
        raise ValueError("Invalid Quizzes keywords response")
    if len(keywords) > MAX_KEYWORDS:
        limitations.append(f"Quiz {row['quiz_id']} keywords were truncated.")
    return [item["keyword"][:200] for item in keywords[:MAX_KEYWORDS]]


def _questions(row, limitations):
    questions = row.get("questions")
    if not isinstance(questions, list):
        raise ValueError("Invalid Quizzes questions response")
    if len(questions) > MAX_QUESTIONS:
        limitations.append(f"Quiz {row['quiz_id']} questions were truncated to the first {MAX_QUESTIONS}.")
    result = []
    for question in questions[:MAX_QUESTIONS]:
        answers = question.get("answers") if isinstance(question, dict) else None
        if not isinstance(answers, list) or not isinstance(question.get("question_text"), str) or any(
            not isinstance(answer, dict) or not isinstance(answer.get("answer_text"), str) for answer in answers
        ):
            raise ValueError("Invalid Quizzes question response")
        result.append({
            "question_id": question.get("question_id"),
            "question_text": _text(question["question_text"]),
            "explanation": _text(question.get("explanation")),
            "answers": [
                {"answer_text": _text(answer["answer_text"]), "is_correct": bool(answer.get("is_correct"))}
                for answer in answers
            ],
        })
    return result


def collect_evidence(record_id=None) -> dict:
    base = os.getenv("QUIZZES_DATABASE_URL", "http://localhost:6004").rstrip("/")
    path = f"/quizzes/{record_id}" if record_id is not None else "/quizzes"
    response = requests.get(base + path, timeout=float(os.getenv("EVIDENCE_TIMEOUT_SECONDS", "10")))
    response.raise_for_status()
    payload = response.json()
    records = [payload] if record_id is not None else payload
    if not isinstance(records, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("quiz_id"), int) or not isinstance(row.get("title"), str)
        for row in records
    ):
        raise ValueError("Invalid Quizzes evidence response")
    limitations = []
    if record_id is None:
        limitations.append(
            "Catalogue evidence contains quiz titles, descriptions, difficulty and keywords only; "
            "questions and answers are not included. Run the workflow with a quiz ID to study one quiz."
        )
    if len(records) > MAX_RECORDS:
        limitations.append(f"Only the first {MAX_RECORDS} catalogue records are included.")
    evidence = []
    for row in records[:MAX_RECORDS]:
        fields = {key: _text(row[key]) for key in CATALOGUE_FIELDS if key in row}
        fields["keywords"] = _keywords(row, limitations)
        if record_id is not None:
            fields["questions"] = _questions(row, limitations)
        evidence.append({"source": f"quizzes:/quizzes/{row['quiz_id']}", "fields": fields})
    if not evidence:
        limitations.append("No quizzes were found.")
    return {"evidence": evidence, "evidence_count": len(evidence), "limitations": limitations}
