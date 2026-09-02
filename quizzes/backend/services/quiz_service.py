import re

from services.database_client import database
from services.ollama_client import BLOCKED_OUTPUT, generate_feedback, generate_quiz_questions
from services.subjects_client import fetch_subject


QUIZ_FIELDS = ("subject_id", "subject_name", "title", "description", "difficulty")
DIFFICULTIES = ("Easy", "Medium", "Hard")
MIN_QUESTIONS = 3
MAX_QUESTIONS = 10
INJECTION_PATTERN = re.compile(
    r"(ignore (all |any )?(previous|prior|system) instructions|system prompt|"
    r"reveal .{0,20}(secret|password|token)|<\|im_(start|end)\|>|jailbreak)",
    re.IGNORECASE,
)


class ServiceError(RuntimeError):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.status = status
        self.details = details


def _json(response, fallback="Quiz database service request failed"):
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not response.ok:
        raise ServiceError(body.get("error", fallback), response.status_code, body)
    return body


def list_quizzes():
    return _json(database.list_quizzes())


def get_quiz(quiz_id):
    return _json(database.get_quiz(quiz_id), "Quiz not found")


def validate_difficulty(value):
    value = str(value or "").strip().title()
    if value not in DIFFICULTIES:
        raise ServiceError(f"Difficulty must be one of: {', '.join(DIFFICULTIES)}")
    return value


def validate_quiz(payload, partial=False):
    if not isinstance(payload, dict):
        raise ServiceError("Request body must be an object")
    missing = [] if partial else [
        field for field in QUIZ_FIELDS if not str(payload.get(field, "")).strip()
    ]
    if missing:
        raise ServiceError("All quiz fields are required", details={"fields": missing})

    limits = {"subject_name": 120, "title": 150, "description": 2000, "difficulty": 20}
    cleaned = {}
    for field in QUIZ_FIELDS:
        if field not in payload:
            continue
        if field == "subject_id":
            raw = str(payload[field]).strip()
            if not raw.isdigit():
                raise ServiceError("Subject ID must be a positive number")
            cleaned[field] = int(raw)
            continue
        if field == "difficulty":
            cleaned[field] = validate_difficulty(payload[field])
            continue
        value = str(payload[field]).strip()
        if not value:
            raise ServiceError(f"{field.replace('_', ' ').title()} cannot be empty")
        if len(value) > limits[field]:
            raise ServiceError(f"{field.replace('_', ' ').title()} is too long")
        cleaned[field] = value

    if not cleaned:
        raise ServiceError("At least one quiz field is required")
    return cleaned


def create_quiz(payload):
    return _json(database.create_quiz(validate_quiz(payload)), "Could not create quiz")


def update_quiz(quiz_id, payload):
    return _json(
        database.update_quiz(quiz_id, validate_quiz(payload, partial=True)), "Could not update quiz"
    )


def delete_quiz(quiz_id):
    response = database.delete_quiz(quiz_id)
    if not response.ok:
        _json(response, "Could not delete quiz")


def add_question(quiz_id, question_text, explanation, answer_texts, correct_index):
    question_text = str(question_text or "").strip()
    explanation = str(explanation or "").strip()
    answers = [str(text or "").strip() for text in answer_texts]

    if not question_text or not explanation:
        raise ServiceError("Question text and explanation are required")
    if sum(1 for a in answers if a) < 2:
        raise ServiceError("At least two answer options are required")
    if not (0 <= correct_index < len(answers)) or not answers[correct_index]:
        raise ServiceError("A valid correct answer must be selected")

    payload = {
        "question_text": question_text,
        "explanation": explanation,
        "answers": [
            {"text": text, "is_correct": index == correct_index}
            for index, text in enumerate(answers)
            if text
        ],
    }
    return _json(database.add_question(quiz_id, payload), "Could not add question")


def submit_attempt(quiz_id, student_name, question_ids, answer_ids):
    student_name = str(student_name or "").strip()
    if not student_name:
        raise ServiceError("Your name is required")
    if len(student_name) > 80:
        raise ServiceError("Name is too long")

    responses = []
    for question_id, answer_id in zip(question_ids, answer_ids):
        if not str(answer_id or "").isdigit():
            raise ServiceError("Every question must have an answer selected")
        responses.append({"question_id": int(question_id), "selected_answer_id": int(answer_id)})
    if not responses:
        raise ServiceError("No responses were submitted")

    return _json(
        database.submit_attempt(quiz_id, {"student_name": student_name, "responses": responses}),
        "Could not submit attempt",
    )


def list_attempts(quiz_id, student_name=None):
    return _json(database.list_attempts(quiz_id, student_name))


def get_attempt(attempt_id):
    return _json(database.get_attempt(attempt_id), "Attempt not found")


def get_or_create_feedback(attempt_id, force=False):
    attempt = get_attempt(attempt_id)
    if attempt.get("ai_feedback") and not force:
        return attempt

    incorrect = [r for r in attempt["responses"] if not r["is_correct"]]
    if not incorrect:
        return _json(
            database.store_attempt_feedback(
                attempt_id, "Great work! Every answer in this attempt was correct."
            )
        )

    context_lines = []
    for response in incorrect:
        context_lines.append(
            f"Question: {response['question_text']}\n"
            f"Your answer: {response['selected_answer_text']}\n"
            f"Correct answer: {response['correct_answer_text']}\n"
            f"Why it's correct: {response['explanation']}"
        )
    context_text = "\n\n".join(context_lines)

    if INJECTION_PATTERN.search(context_text):
        raise ServiceError("Feedback could not be generated safely for this attempt", 422)

    feedback = generate_feedback(context_text)
    if BLOCKED_OUTPUT in feedback:
        raise ServiceError("The AI rejected this request as unsafe", 422)

    return _json(database.store_attempt_feedback(attempt_id, feedback), "Could not save feedback")


def generate_ai_quiz(subject_id, difficulty, question_count, topic_hint=""):
    difficulty = validate_difficulty(difficulty)

    count_raw = str(question_count or "").strip()
    if not count_raw.isdigit() or not (MIN_QUESTIONS <= int(count_raw) <= MAX_QUESTIONS):
        raise ServiceError(f"Number of questions must be between {MIN_QUESTIONS} and {MAX_QUESTIONS}")
    question_count = int(count_raw)

    topic_hint = str(topic_hint or "").strip()
    if len(topic_hint) > 500:
        raise ServiceError("Topic hint must be 500 characters or fewer")
    if INJECTION_PATTERN.search(topic_hint):
        raise ServiceError("That topic hint cannot be processed safely", 422)

    subject = fetch_subject(subject_id)
    if subject:
        subject_name = f"{subject['code']} - {subject['name']}"
        context_text = (
            f"Subject: {subject_name}\n"
            f"Subject description: {subject['description']}\n"
            f"Additional focus requested by the student: {topic_hint or 'None'}"
        )
    else:
        subject_name = f"Subject #{subject_id}"
        context_text = (
            f"Subject: {subject_name}\n"
            "Subject description: Not available - the Subject Management service could not be reached.\n"
            f"Additional focus requested by the student: {topic_hint or 'None'}"
        )

    if INJECTION_PATTERN.search(context_text):
        raise ServiceError("The subject content was rejected as unsafe for generation", 422)

    payload, raw = generate_quiz_questions(context_text, difficulty, question_count)
    if payload is None:
        raise ServiceError("The AI could not generate a valid quiz. Please try again.", 422)

    questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(questions, list) or not questions:
        raise ServiceError("The AI response did not contain any questions. Please try again.", 422)

    ai_title = str(payload.get("title") or "").strip()[:80]
    if len(re.sub(r"[^a-zA-Z0-9]", "", ai_title)) < 8:
        ai_title = f"AI-generated {difficulty} quiz: {subject_name}"

    quiz = _json(
        database.create_quiz(
            {
                "subject_id": subject_id,
                "subject_name": subject_name,
                "title": ai_title,
                "description": f"Automatically generated {difficulty.lower()} practice quiz"
                + (f" focused on: {topic_hint}." if topic_hint else "."),
                "difficulty": difficulty,
                "source": "ai_generated",
            }
        ),
        "Could not create AI-generated quiz",
    )

    added = 0
    for entry in questions[:question_count]:
        try:
            question_text = str(entry["question"]).strip()
            options = [str(o).strip() for o in entry["options"]]
            correct_index = int(entry["correct_index"])
            explanation = str(entry.get("explanation", "")).strip() or "This is the correct answer."
        except (KeyError, TypeError, ValueError):
            continue
        alnum_options = [o for o in options if re.search(r"[a-zA-Z0-9]{2,}", o)]
        if (
            len(re.sub(r"[^a-zA-Z0-9]", "", question_text)) < 8
            or len(alnum_options) < 2
            or not (0 <= correct_index < len(options))
            or not re.search(r"[a-zA-Z0-9]{2,}", options[correct_index])
        ):
            continue

        response = database.add_question(
            quiz["quiz_id"],
            {
                "question_text": question_text,
                "explanation": explanation,
                "answers": [
                    {"text": text, "is_correct": index == correct_index}
                    for index, text in enumerate(options)
                ],
            },
        )
        if response.ok:
            added += 1

    if added == 0:
        database.delete_quiz(quiz["quiz_id"])
        raise ServiceError("The AI response could not be turned into usable questions. Please try again.", 422)

    return get_quiz(quiz["quiz_id"])
