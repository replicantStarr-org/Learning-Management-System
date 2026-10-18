"""Post-commit endpoint tests for the quiz backend (two endpoint functions).

1. POST /quizzes                    - create a quiz, with validation of bad input
2. POST /quizzes/<id>/attempts      - grade a submitted attempt

Both are Release 0 functions that carry real logic (validation and grading), so
the tests assert behaviour and not only that the route answers. Failures reach
the browser as an HTML alert with the HX-Error header and HTTP 200, so error
cases are asserted through that header and the alert text.
"""


# --- Endpoint 1: POST /quizzes ------------------------------------------------

def test_create_quiz_returns_201_and_redirects_to_the_new_quiz(api):
    response = api.create_quiz(title="Created by endpoint test")

    assert response.status_code == 201
    assert "HX-Error" not in response.headers
    assert response.headers["HX-Trigger"] == "quizzesChanged"
    quiz_id = api.quiz_id_from(response)
    assert quiz_id is not None, "HX-Redirect should point at the new quiz"

    page = api.get(f"/quizzes/{quiz_id}")
    assert page.status_code == 200
    assert "Created by endpoint test" in page.text


def test_create_quiz_rejects_a_missing_title(api):
    response = api.create_quiz(title="")

    assert response.headers.get("HX-Error") == "true"
    assert "All quiz fields are required" in response.text
    assert api.quiz_id_from(response) is None


def test_create_quiz_rejects_an_unknown_difficulty(api):
    response = api.create_quiz(difficulty="Impossible")

    assert response.headers.get("HX-Error") == "true"
    assert "Difficulty must be one of" in response.text
    assert api.quiz_id_from(response) is None


# --- Endpoint 2: POST /quizzes/<id>/attempts ----------------------------------

def _quiz_with_two_questions(api):
    quiz_id = api.quiz_id_from(api.create_quiz(title="Grading endpoint test"))
    assert quiz_id is not None
    assert api.add_question(quiz_id, "Capital of France?", ["Paris", "Lyon", "Nice"], 0).status_code == 200
    assert api.add_question(quiz_id, "2 + 2 = ?", ["3", "4", "5"], 1).status_code == 200
    return quiz_id, api.answer_ids(quiz_id)


def _attempt(api, quiz_id, picks):
    return api.post(
        f"/quizzes/{quiz_id}/attempts",
        {
            "student_name": "Endpoint Tester",
            "responses": [
                {"question_id": question_id, "selected_answer_id": answer_id}
                for question_id, answer_id in picks
            ],
        },
    )


def test_attempt_with_all_correct_answers_scores_full_marks(api):
    quiz_id, ids = _quiz_with_two_questions(api)

    response = _attempt(api, quiz_id, [ids["Paris"], ids["4"]])

    assert response.status_code == 200
    assert "Your score: 2 / 2" in response.text


def test_attempt_with_one_wrong_answer_scores_one_of_two(api):
    quiz_id, ids = _quiz_with_two_questions(api)

    response = _attempt(api, quiz_id, [ids["Lyon"], ids["4"]])

    assert response.status_code == 200
    assert "Your score: 1 / 2" in response.text


def test_attempt_without_a_student_name_is_rejected(api):
    quiz_id, ids = _quiz_with_two_questions(api)

    response = api.post(
        f"/quizzes/{quiz_id}/attempts",
        {"student_name": " ", "responses": [{"question_id": ids["Paris"][0], "selected_answer_id": ids["Paris"][1]}]},
    )

    assert response.headers.get("HX-Error") == "true"
    assert "Your name is required" in response.text
