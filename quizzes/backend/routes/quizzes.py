from functools import wraps

import requests
from flask import Blueprint, make_response, request

from services.ollama_client import OllamaError
from services.quiz_service import (
    ServiceError,
    add_question,
    create_quiz,
    delete_question,
    delete_quiz,
    generate_ai_quiz,
    get_or_create_feedback,
    get_attempt,
    get_question,
    get_quiz,
    list_attempts,
    list_quizzes,
    submit_attempt,
    update_question,
    update_quiz,
)
from services.subjects_client import list_subjects
from views.html import (
    FRONTEND_BASE,
    attempt_result,
    attempts_list,
    error,
    feedback_result,
    generated_quiz_message,
    message,
    question_display,
    question_edit_form,
    questions_panel,
    quiz_detail,
    quiz_edit_form,
    quiz_list,
    subject_options,
)


quizzes_bp = Blueprint("quizzes", __name__)


def handle_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except ServiceError as exc:
            response = make_response(error(str(exc)), 200)
            response.headers["HX-Error"] = "true"
            return response
        except OllamaError as exc:
            response = make_response(error(str(exc)), 200)
            response.headers["HX-Error"] = "true"
            return response
        except requests.RequestException:
            response = make_response(error("The quiz database service is unavailable."), 200)
            response.headers["HX-Error"] = "true"
            return response

    return wrapped


def quizzes_changed(body, status=200, redirect=None):
    response = make_response(body, status)
    response.headers["HX-Trigger"] = "quizzesChanged"
    if redirect:
        response.headers["HX-Redirect"] = redirect
    return response


def questions_changed(body, status=200):
    response = make_response(body, status)
    response.headers["HX-Trigger"] = "questionsChanged, quizzesChanged"
    return response


def request_data():
    """Return a dictionary for both browser forms and REST JSON clients."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else request.form.to_dict()


def question_form_values(data):
    """Normalise the form representation and the JSON answer representation."""
    answers = data.get("answers")
    if isinstance(answers, list):
        answer_texts = [
            answer.get("text", answer.get("answer_text", ""))
            for answer in answers[:4]
            if isinstance(answer, dict)
        ]
        correct_index = next(
            (index for index, answer in enumerate(answers[:4]) if isinstance(answer, dict) and answer.get("is_correct")),
            -1,
        )
        return data.get("question_text"), data.get("explanation"), answer_texts, correct_index

    answer_texts = [data.get(f"answer_{i}", "") for i in range(1, 5)]
    try:
        correct_index = int(data.get("correct_index", 0))
    except (TypeError, ValueError) as exc:
        raise ServiceError("A valid correct answer must be selected") from exc
    return data.get("question_text"), data.get("explanation"), answer_texts, correct_index


@quizzes_bp.get("/quizzes")
@handle_errors
def all_quizzes():
    return quiz_list(list_quizzes())


@quizzes_bp.get("/subjects")
@handle_errors
def subject_dropdown_options():
    # Subjects are owned by the Subjects service.  This endpoint is only a
    # presentation of that resource for the quiz forms; it does not proxy CRUD.
    return subject_options(list_subjects())


@quizzes_bp.post("/quizzes")
@handle_errors
def add_quiz():
    quiz = create_quiz(request_data())
    return quizzes_changed(
        message(f'"{quiz["title"]}" was created.'),
        201,
        f"{FRONTEND_BASE}/quiz.html?id={quiz['quiz_id']}",
    )


@quizzes_bp.get("/quizzes/<int:quiz_id>")
@handle_errors
def quiz_by_id(quiz_id):
    quiz = get_quiz(quiz_id)
    if request.args.get("view") == "edit":
        return quiz_edit_form(quiz)
    return quiz_detail(quiz)


@quizzes_bp.put("/quizzes/<int:quiz_id>")
@handle_errors
def edit_quiz(quiz_id):
    data = request_data()
    quiz = update_quiz(quiz_id, data)
    return quizzes_changed(message(f'"{quiz["title"]}" was updated.'))


@quizzes_bp.delete("/quizzes/<int:quiz_id>")
@handle_errors
def remove_quiz(quiz_id):
    delete_quiz(quiz_id)
    return quizzes_changed("", 204, redirect=f"{FRONTEND_BASE}/?message=Quiz%20deleted.")


@quizzes_bp.post("/quizzes/<int:quiz_id>/questions")
@handle_errors
def add_quiz_question(quiz_id):
    data = request_data()
    question_text, explanation, answer_texts, correct_index = question_form_values(data)
    add_question(quiz_id, question_text, explanation, answer_texts, correct_index)
    return questions_changed(message("Question added."))


@quizzes_bp.get("/quizzes/<int:quiz_id>/questions")
@handle_errors
def manage_questions(quiz_id):
    quiz = get_quiz(quiz_id)
    return questions_panel(quiz_id, quiz["questions"])


@quizzes_bp.get("/quizzes/<int:quiz_id>/questions/<int:question_id>")
@handle_errors
def question_by_id(quiz_id, question_id):
    _, question = get_question(quiz_id, question_id)
    if request.args.get("view") == "edit":
        return question_edit_form(quiz_id, question)
    return question_display(quiz_id, question)


@quizzes_bp.put("/quizzes/<int:quiz_id>/questions/<int:question_id>")
@handle_errors
def edit_question(quiz_id, question_id):
    data = request_data()
    question_text, explanation, answer_texts, correct_index = question_form_values(data)
    updated = update_question(
        quiz_id, question_id, question_text, explanation, answer_texts, correct_index
    )
    return questions_changed(question_display(quiz_id, updated))


@quizzes_bp.delete("/quizzes/<int:quiz_id>/questions/<int:question_id>")
@handle_errors
def remove_question(quiz_id, question_id):
    delete_question(quiz_id, question_id)
    return questions_changed("")


@quizzes_bp.post("/quizzes/<int:quiz_id>/attempts")
@handle_errors
def add_attempt(quiz_id):
    payload = request_data()
    if isinstance(payload.get("responses"), list):
        question_ids = [item.get("question_id") for item in payload["responses"] if isinstance(item, dict)]
        answer_ids = [item.get("selected_answer_id") for item in payload["responses"] if isinstance(item, dict)]
    else:
        question_ids = [key[2:] for key in payload if key.startswith("q_")]
        answer_ids = [payload.get(key) for key in payload if key.startswith("q_")]
    attempt = submit_attempt(quiz_id, payload.get("student_name"), question_ids, answer_ids)
    return attempt_result(attempt)


@quizzes_bp.get("/quizzes/<int:quiz_id>/attempts")
@handle_errors
def attempt_history(quiz_id):
    quiz = get_quiz(quiz_id)
    attempts = list_attempts(quiz_id, request.args.get("student_name"))
    return attempts_list(quiz, attempts)


@quizzes_bp.get("/attempts/<int:attempt_id>")
@handle_errors
def attempt_by_id(attempt_id):
    return attempt_result(get_attempt(attempt_id))


@quizzes_bp.get("/attempts/<int:attempt_id>/feedback")
@handle_errors
def stored_attempt_feedback(attempt_id):
    attempt = get_attempt(attempt_id)
    if not attempt.get("ai_feedback"):
        raise ServiceError("Feedback has not been generated for this attempt", 404)
    return feedback_result(attempt)


@quizzes_bp.post("/attempts/<int:attempt_id>/feedback")
@handle_errors
def attempt_feedback(attempt_id):
    # Feedback generation is a POST because it may create the cached
    # feedback sub-resource. GET above only reads an existing representation.
    attempt = get_or_create_feedback(attempt_id)
    return feedback_result(attempt)


def _generate(subject_id):
    form = request_data()
    quiz = generate_ai_quiz(
        subject_id,
        form.get("difficulty"),
        form.get("question_count"),
        form.get("topic_hint"),
    )
    return quizzes_changed(generated_quiz_message(quiz), 201)


@quizzes_bp.post("/quiz-generations")
@handle_errors
def create_quiz_generation():
    """Create a generated quiz from the quiz-generation resource."""
    subject_id_raw = request_data().get("subject_id", "")
    if not str(subject_id_raw).isdigit():
        raise ServiceError("A valid subject ID is required")
    return _generate(int(subject_id_raw))


@quizzes_bp.post("/subjects/<int:subject_id>/quiz-generations")
@handle_errors
def create_subject_quiz_generation(subject_id):
    """Nested REST form for generating a quiz for one subject."""
    return _generate(subject_id)
