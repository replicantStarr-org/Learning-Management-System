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
import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Literal

import requests
from mcp.server.mcpserver.exceptions import ToolError


MAX_TEXT_LENGTH = 100
MAX_SEARCH_RESULTS = 25
# A question's search relevance is its text score (up to 1.0), plus these shares of
# its quiz's keyword match and of how many of the quiz's keywords it mentions (each
# up to 1.0). The keywords the search matched also stand in for it, like "did you
# mean": a question naming one scores as if it named the search, at ALIAS_SHARE.
KEYWORD_SCORE_SHARE = 0.5
CONTEXT_SCORE_SHARE = 0.2
ALIAS_SHARE = 0.9
MIN_RELEVANCE = 0.2
# How alike two words must be to count as a misspelling of each other ("kubernets").
TYPO_SIMILARITY = 0.85

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


STOPWORDS = {
    "a", "an", "and", "are", "do", "does", "for", "how", "in", "is", "of", "on", "or",
    "the", "to", "what", "which", "why", "with",
}


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


@lru_cache(maxsize=4096)
def _tokens(text: str) -> tuple[str, ...]:
    """Lowercased, stemmed words. Cached, as every search tokenises the same
    question text and keywords again; the key is the text itself, so an edited
    question is simply a new entry."""
    return tuple(_stem(word) for word in re.findall(r"[a-z0-9]+", text.lower()))


def _phrase_in(phrase: tuple[str, ...], tokens: tuple[str, ...]) -> bool:
    """Whether the token sequence phrase appears, whole words, in tokens."""
    return f" {' '.join(phrase)} " in f" {' '.join(tokens)} "


def _word_match(a: str, b: str, typos: bool = False) -> float:
    """1 for the same word after stemming; 0.5 when one is a prefix of the
    other ("sort" and "sorting"), which is looser, as "contain" and "container"
    show; with typos, 0.8 for a near spelling of a word of 5+ letters, checked
    first as a misspelling can also be a prefix ("kubernet"); else 0."""
    if a == b:
        return 1.0
    if typos and min(len(a), len(b)) >= 5 and _similar(a, b):
        return 0.8
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return 0.5
    return 0.0


@lru_cache(maxsize=16384)
def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= TYPO_SIMILARITY


def _best_match(word: str, words: tuple[str, ...], typos: bool = False) -> float:
    return max((_word_match(word, other, typos) for other in words), default=0.0)


def _keyword_score(query, terms, keyword, weight: float) -> float:
    """How strongly one quiz keyword matches the search: its full weight when
    either phrase contains the other, else a share of it for the words in
    common, misspellings included. Typos are only forgiven here, against the
    hundred or so keywords, not against every word of every question, which
    keeps the search as fast as before."""
    if _phrase_in(query, keyword):
        return weight
    if _phrase_in(keyword, query):
        # A keyword covering part of the search ("sql" in "sql injection")
        # counts for that part only.
        return weight * min(1.0, len(keyword) / len(terms))
    matched = sum(_best_match(word, terms, typos=True) for word in keyword)
    share = matched / len(keyword)
    # A whole keyword misspelt ("kubernets") counts nearly in full; part of one, half.
    return weight * (share if share >= 0.8 else share / 2)


def _context_score(keywords, text: tuple[str, ...]) -> float:
    """The heaviest of a quiz's keywords that this question mentions, to order
    the questions of a quiz the search found through its keywords."""
    return max((weight for tokens, weight in keywords if _phrase_in(tokens, text)), default=0.0)


def _text_score(query, terms, question: tuple[str, ...], rest: tuple[str, ...]) -> float:
    """1.0 when the question names the search, 0.7 when its answers or
    explanation do, else up to 0.5 for the search words it shares."""
    if _phrase_in(query, question):
        return 1.0
    if _phrase_in(query, rest):
        return 0.7
    words = question + rest
    if not terms:
        return 0.0
    found = sum(_best_match(term, words) for term in terms)
    return 0.5 * found / len(terms)


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
        """Find questions on a topic across every quiz, to revise it, best
        matches first.

        Each question is scored on its text, answers and explanation, and on
        its quiz's weighted keywords, which add related terms and forgive small
        typos: "containers" finds the Docker questions and "kubernets" still
        finds the Kubernetes one. Each match has its relevance. Returns at most
        25 matches. MCP-only: the quiz pages have no question search.
        """
        query = _tokens(_required_text(keyword, "keyword"))
        terms = [t for t in query if t not in STOPWORDS] or query
        matches = []
        for summary in client.request("/quizzes"):
            # The list already carries each quiz's keywords, so scoring them costs
            # no extra request; only the question fetch below does, as before.
            keywords = [(_tokens(k["keyword"]), k["weight"]) for k in summary.get("keywords", [])]
            scored = [
                (tokens, weight, _keyword_score(query, terms, tokens, weight))
                for tokens, weight in keywords
            ]
            keyword_score = max((score for _, _, score in scored), default=0.0)
            # The matched keywords, with how closely each matched (1 for an exact
            # match, less for part of one or a typo), to try as the search itself.
            aliases = [(tokens, score / weight) for tokens, weight, score in scored if score]
            if not summary["question_count"]:
                continue

            quiz = client.request(f"/quizzes/{summary['quiz_id']}")
            for number, question in enumerate(quiz["questions"], start=1):
                answers = [answer["answer_text"] for answer in question["answers"]]
                question_tokens = _tokens(question["question_text"])
                rest = _tokens(" ".join([question["explanation"], *answers]))
                text_score = max(
                    [_text_score(query, terms, question_tokens, rest)]
                    + [
                        ALIAS_SHARE * closeness * _text_score(tokens, tokens, question_tokens, rest)
                        for tokens, closeness in aliases
                    ]
                )
                context = (
                    keyword_score * _context_score(keywords, question_tokens + rest)
                    if keyword_score else 0.0
                )
                relevance = round(
                    text_score
                    + KEYWORD_SCORE_SHARE * keyword_score
                    + CONTEXT_SCORE_SHARE * context,
                    2,
                )
                if relevance >= MIN_RELEVANCE:
                    matches.append(
                        {
                            "quiz_id": quiz["quiz_id"],
                            "quiz_title": quiz["title"],
                            "subject_name": quiz["subject_name"],
                            "question_id": question["question_id"],
                            "number": number,
                            "question_text": question["question_text"],
                            "relevance": relevance,
                        }
                    )
        matches.sort(key=lambda m: (-m["relevance"], m["quiz_id"], m["number"]))
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
