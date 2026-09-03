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


@quizzes_bp.get("/quizzes")
@handle_errors
def all_quizzes():
    return quiz_list(list_quizzes())


@quizzes_bp.get("/subjects/options")
@handle_errors
def subject_dropdown_options():
    return subject_options(list_subjects())


@quizzes_bp.post("/quizzes")
@handle_errors
def add_quiz():
    quiz = create_quiz(request.form.to_dict())
    return quizzes_changed(
        message(f'"{quiz["title"]}" was created.'),
        201,
        f"{FRONTEND_BASE}/quiz.html?id={quiz['quiz_id']}",
    )


@quizzes_bp.get("/quizzes/<int:quiz_id>")
@handle_errors
def quiz_by_id(quiz_id):
    return quiz_detail(get_quiz(quiz_id))


@quizzes_bp.get("/quizzes/<int:quiz_id>/edit")
@handle_errors
def quiz_edit(quiz_id):
    return quiz_edit_form(get_quiz(quiz_id))


@quizzes_bp.post("/quizzes/update")
@handle_errors
def edit_quiz():
    data = request.form.to_dict()
    quiz_id = data.pop("quiz_id", None)
    if not str(quiz_id or "").isdigit():
        raise ServiceError("A valid quiz ID is required")
    quiz = update_quiz(int(quiz_id), data)
    return quizzes_changed(message(f'"{quiz["title"]}" was updated.'))


@quizzes_bp.post("/quizzes/delete")
@handle_errors
def remove_quiz():
    quiz_id = request.form.get("quiz_id", "")
    if not quiz_id.isdigit():
        raise ServiceError("A valid quiz ID is required")
    delete_quiz(int(quiz_id))
    return quizzes_changed("", redirect=f"{FRONTEND_BASE}/?message=Quiz%20deleted.")


@quizzes_bp.post("/quizzes/<int:quiz_id>/questions")
@handle_errors
def add_quiz_question(quiz_id):
    data = request.form
    answer_texts = [data.get(f"answer_{i}", "") for i in range(1, 5)]
    correct_index = int(data.get("correct_index", 0))
    add_question(quiz_id, data.get("question_text"), data.get("explanation"), answer_texts, correct_index)
    return questions_changed(message("Question added."))


@quizzes_bp.get("/quizzes/<int:quiz_id>/questions/manage")
@handle_errors
def manage_questions(quiz_id):
    quiz = get_quiz(quiz_id)
    return questions_panel(quiz_id, quiz["questions"])


@quizzes_bp.get("/quizzes/<int:quiz_id>/questions/<int:question_id>")
@handle_errors
def question_by_id(quiz_id, question_id):
    _, question = get_question(quiz_id, question_id)
    return question_display(quiz_id, question)


@quizzes_bp.get("/quizzes/<int:quiz_id>/questions/<int:question_id>/edit")
@handle_errors
def question_edit(quiz_id, question_id):
    _, question = get_question(quiz_id, question_id)
    return question_edit_form(quiz_id, question)


@quizzes_bp.put("/quizzes/<int:quiz_id>/questions/<int:question_id>")
@handle_errors
def edit_question(quiz_id, question_id):
    data = request.form
    answer_texts = [data.get(f"answer_{i}", "") for i in range(1, 5)]
    correct_index = int(data.get("correct_index", 0))
    updated = update_question(
        quiz_id, question_id, data.get("question_text"), data.get("explanation"), answer_texts, correct_index
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
    form = request.form
    question_ids = [key[2:] for key in form.keys() if key.startswith("q_")]
    answer_ids = [form.get(key) for key in form.keys() if key.startswith("q_")]
    attempt = submit_attempt(quiz_id, form.get("student_name"), question_ids, answer_ids)
    return attempt_result(attempt)


@quizzes_bp.get("/quizzes/<int:quiz_id>/attempts")
@handle_errors
def attempt_history(quiz_id):
    quiz = get_quiz(quiz_id)
    attempts = list_attempts(quiz_id, request.args.get("student_name"))
    return attempts_list(quiz, attempts)


@quizzes_bp.post("/attempts/<int:attempt_id>/feedback")
@handle_errors
def attempt_feedback(attempt_id):
    attempt = get_or_create_feedback(attempt_id)
    return feedback_result(attempt)


def _generate(subject_id):
    form = request.form
    quiz = generate_ai_quiz(
        subject_id,
        form.get("difficulty"),
        form.get("question_count"),
        form.get("topic_hint"),
    )
    return quizzes_changed(generated_quiz_message(quiz), 201)


@quizzes_bp.post("/quizzes/generate")
@handle_errors
def generate_quiz_from_form():
    subject_id_raw = request.form.get("subject_id", "")
    if not subject_id_raw.isdigit():
        raise ServiceError("A valid subject ID is required")
    return _generate(int(subject_id_raw))


@quizzes_bp.post("/subjects/<int:subject_id>/quizzes/generate")
@handle_errors
def generate_quiz_for_subject(subject_id):
    return _generate(subject_id)
