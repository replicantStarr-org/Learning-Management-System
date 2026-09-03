from flask import Flask, jsonify, request
import sqlite3

app = Flask(__name__)

DATABASE_NAME = "data/quizzes.db"

QUIZ_FIELDS = ("subject_id", "subject_name", "title", "description", "difficulty")


def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    return body, None


def get_quiz(quiz_id, conn=None):
    owns_connection = conn is None
    conn = conn or get_db_connection()
    row = conn.execute(
        """
        SELECT quiz_id, subject_id, subject_name, title, description, difficulty,
               question_count, source, created_at, last_update
        FROM quizzes
        WHERE quiz_id = ?
        """,
        (quiz_id,),
    ).fetchone()
    if owns_connection:
        conn.close()
    return row


def get_questions_with_answers(quiz_id, conn):
    questions = conn.execute(
        """
        SELECT question_id, question_text, explanation, question_order
        FROM quiz_questions
        WHERE quiz_id = ?
        ORDER BY question_order, question_id
        """,
        (quiz_id,),
    ).fetchall()

    result = []
    for question in questions:
        answers = conn.execute(
            """
            SELECT answer_id, answer_text, is_correct, answer_order
            FROM quiz_answers
            WHERE question_id = ?
            ORDER BY answer_order, answer_id
            """,
            (question["question_id"],),
        ).fetchall()
        entry = dict(question)
        entry["answers"] = [dict(answer) for answer in answers]
        result.append(entry)
    return result


def get_attempt(attempt_id, conn):
    return conn.execute(
        """
        SELECT attempt_id, quiz_id, student_name, score, total_questions,
               ai_feedback, started_at, completed_at
        FROM quiz_attempts
        WHERE attempt_id = ?
        """,
        (attempt_id,),
    ).fetchone()


def get_responses_with_detail(attempt_id, conn):
    rows = conn.execute(
        """
        SELECT r.response_id, r.question_id, r.selected_answer_id, r.is_correct,
               q.question_text, q.explanation,
               sel.answer_text AS selected_answer_text
        FROM quiz_responses r
        JOIN quiz_questions q ON q.question_id = r.question_id
        LEFT JOIN quiz_answers sel ON sel.answer_id = r.selected_answer_id
        WHERE r.attempt_id = ?
        ORDER BY q.question_order, r.response_id
        """,
        (attempt_id,),
    ).fetchall()

    result = []
    for row in rows:
        entry = dict(row)
        correct = conn.execute(
            "SELECT answer_id, answer_text FROM quiz_answers WHERE question_id = ? AND is_correct = 1",
            (row["question_id"],),
        ).fetchone()
        entry["correct_answer_id"] = correct["answer_id"] if correct else None
        entry["correct_answer_text"] = correct["answer_text"] if correct else None
        result.append(entry)
    return result


@app.get("/")
def health():
    return jsonify({"service": "quiz-database-service", "status": "running"})


@app.get("/quizzes")
def list_quizzes():
    conn = get_db_connection()
    try:
        quizzes = conn.execute(
            """
            SELECT quiz_id, subject_id, subject_name, title, description, difficulty,
                   question_count, source, created_at, last_update
            FROM quizzes
            ORDER BY quiz_id
            """
        ).fetchall()
        return jsonify([dict(row) for row in quizzes])
    finally:
        conn.close()


@app.get("/quizzes/<int:quiz_id>")
def get_quiz_details(quiz_id):
    conn = get_db_connection()
    try:
        quiz = get_quiz(quiz_id, conn)
        if quiz is None:
            return jsonify({"error": "Quiz not found"}), 404
        body = dict(quiz)
        body["questions"] = get_questions_with_answers(quiz_id, conn)
        return jsonify(body)
    finally:
        conn.close()


@app.post("/quizzes")
def create_quiz():
    body, error = get_json_body()
    if error:
        return error

    missing = [field for field in QUIZ_FIELDS if field not in body or str(body[field]).strip() == ""]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400

    source = body.get("source", "manual")
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO quizzes (subject_id, subject_name, title, description, difficulty, question_count, source)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (
                body["subject_id"], body["subject_name"], body["title"],
                body["description"], body["difficulty"], source,
            ),
        )
        conn.commit()
        return jsonify(dict(get_quiz(cursor.lastrowid, conn))), 201
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.put("/quizzes/<int:quiz_id>")
def update_quiz(quiz_id):
    body, error = get_json_body()
    if error:
        return error

    fields = [field for field in QUIZ_FIELDS if field in body]
    if not fields:
        return jsonify({"error": "At least one quiz field is required"}), 400

    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404

        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [body[field] for field in fields] + [quiz_id]
        conn.execute(f"UPDATE quizzes SET {assignments} WHERE quiz_id = ?", values)
        conn.commit()
        return jsonify(dict(get_quiz(quiz_id, conn)))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.delete("/quizzes/<int:quiz_id>")
def delete_quiz(quiz_id):
    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404

        conn.execute(
            """
            DELETE FROM quiz_responses WHERE attempt_id IN (
                SELECT attempt_id FROM quiz_attempts WHERE quiz_id = ?
            )
            """,
            (quiz_id,),
        )
        conn.execute("DELETE FROM quiz_attempts WHERE quiz_id = ?", (quiz_id,))
        conn.execute(
            """
            DELETE FROM quiz_answers WHERE question_id IN (
                SELECT question_id FROM quiz_questions WHERE quiz_id = ?
            )
            """,
            (quiz_id,),
        )
        conn.execute("DELETE FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
        conn.execute("DELETE FROM quizzes WHERE quiz_id = ?", (quiz_id,))
        conn.commit()
        return "", 204
    finally:
        conn.close()


@app.get("/quizzes/<int:quiz_id>/questions")
def list_questions(quiz_id):
    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404
        return jsonify(get_questions_with_answers(quiz_id, conn))
    finally:
        conn.close()


@app.post("/quizzes/<int:quiz_id>/questions")
def add_question(quiz_id):
    body, error = get_json_body()
    if error:
        return error

    question_text = str(body.get("question_text", "")).strip()
    explanation = str(body.get("explanation", "")).strip()
    answers = body.get("answers")
    if not question_text or not explanation:
        return jsonify({"error": "question_text and explanation are required"}), 400
    if not isinstance(answers, list) or len(answers) < 2:
        return jsonify({"error": "At least two answers are required"}), 400
    if not any(answer.get("is_correct") for answer in answers):
        return jsonify({"error": "At least one answer must be marked correct"}), 400

    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404

        order = conn.execute(
            "SELECT COALESCE(MAX(question_order), 0) + 1 FROM quiz_questions WHERE quiz_id = ?",
            (quiz_id,),
        ).fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO quiz_questions (quiz_id, question_text, explanation, question_order) VALUES (?, ?, ?, ?)",
            (quiz_id, question_text, explanation, order),
        )
        question_id = cursor.lastrowid
        for answer_order, answer in enumerate(answers, start=1):
            conn.execute(
                "INSERT INTO quiz_answers (question_id, answer_text, is_correct, answer_order) VALUES (?, ?, ?, ?)",
                (question_id, str(answer.get("text", "")).strip(), int(bool(answer.get("is_correct"))), answer_order),
            )
        conn.execute(
            "UPDATE quizzes SET question_count = question_count + 1 WHERE quiz_id = ?", (quiz_id,)
        )
        conn.commit()
        return jsonify(get_questions_with_answers(quiz_id, conn)[-1]), 201
    finally:
        conn.close()


@app.put("/quizzes/<int:quiz_id>/questions/<int:question_id>")
def update_question(quiz_id, question_id):
    body, error = get_json_body()
    if error:
        return error

    question_text = str(body.get("question_text", "")).strip()
    explanation = str(body.get("explanation", "")).strip()
    answers = body.get("answers")
    if not question_text or not explanation:
        return jsonify({"error": "question_text and explanation are required"}), 400
    if not isinstance(answers, list) or len(answers) < 2:
        return jsonify({"error": "At least two answers are required"}), 400
    if not any(answer.get("is_correct") for answer in answers):
        return jsonify({"error": "At least one answer must be marked correct"}), 400

    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404
        existing = conn.execute(
            "SELECT question_id FROM quiz_questions WHERE question_id = ? AND quiz_id = ?",
            (question_id, quiz_id),
        ).fetchone()
        if not existing:
            return jsonify({"error": "Question not found"}), 404

        try:
            conn.execute(
                "UPDATE quiz_questions SET question_text = ?, explanation = ? WHERE question_id = ?",
                (question_text, explanation, question_id),
            )

            existing_answers = conn.execute(
                "SELECT answer_id FROM quiz_answers WHERE question_id = ? ORDER BY answer_order",
                (question_id,),
            ).fetchall()

            for answer_order, answer in enumerate(answers, start=1):
                answer_text = str(answer.get("text", "")).strip()
                is_correct = int(bool(answer.get("is_correct")))
                if answer_order <= len(existing_answers):
                    conn.execute(
                        "UPDATE quiz_answers SET answer_text = ?, is_correct = ?, answer_order = ? WHERE answer_id = ?",
                        (answer_text, is_correct, answer_order, existing_answers[answer_order - 1]["answer_id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO quiz_answers (question_id, answer_text, is_correct, answer_order) VALUES (?, ?, ?, ?)",
                        (question_id, answer_text, is_correct, answer_order),
                    )

            if len(answers) < len(existing_answers):
                for row in existing_answers[len(answers):]:
                    conn.execute("DELETE FROM quiz_answers WHERE answer_id = ?", (row["answer_id"],))

            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return jsonify({"error": "Cannot remove an answer option that a student has already selected"}), 409

        updated = next(
            question for question in get_questions_with_answers(quiz_id, conn)
            if question["question_id"] == question_id
        )
        return jsonify(updated)
    finally:
        conn.close()


@app.delete("/quizzes/<int:quiz_id>/questions/<int:question_id>")
def delete_question(quiz_id, question_id):
    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404

        try:
            conn.execute("DELETE FROM quiz_answers WHERE question_id = ?", (question_id,))
            cursor = conn.execute(
                "DELETE FROM quiz_questions WHERE question_id = ? AND quiz_id = ?", (question_id, quiz_id)
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({"error": "Question not found"}), 404
            conn.execute(
                "UPDATE quizzes SET question_count = question_count - 1 WHERE quiz_id = ?", (quiz_id,)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return jsonify({"error": "Cannot delete a question that a student has already attempted"}), 409
        return "", 204
    finally:
        conn.close()


@app.post("/quizzes/<int:quiz_id>/attempts")
def submit_attempt(quiz_id):
    body, error = get_json_body()
    if error:
        return error

    student_name = str(body.get("student_name", "")).strip()
    responses = body.get("responses")
    if not student_name:
        return jsonify({"error": "student_name is required"}), 400
    if not isinstance(responses, list) or not responses:
        return jsonify({"error": "responses is required"}), 400

    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404

        questions = conn.execute(
            "SELECT question_id FROM quiz_questions WHERE quiz_id = ?", (quiz_id,)
        ).fetchall()
        valid_question_ids = {row["question_id"] for row in questions}

        graded = []
        score = 0
        for response in responses:
            question_id = response.get("question_id")
            selected_answer_id = response.get("selected_answer_id")
            if question_id not in valid_question_ids:
                return jsonify({"error": f"Question {question_id} does not belong to this quiz"}), 400

            correct = conn.execute(
                "SELECT is_correct FROM quiz_answers WHERE answer_id = ? AND question_id = ?",
                (selected_answer_id, question_id),
            ).fetchone()
            is_correct = bool(correct and correct["is_correct"])
            if is_correct:
                score += 1
            graded.append((question_id, selected_answer_id, int(is_correct)))

        cursor = conn.execute(
            """
            INSERT INTO quiz_attempts (quiz_id, student_name, score, total_questions, completed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (quiz_id, student_name, score, len(questions)),
        )
        attempt_id = cursor.lastrowid

        for question_id, selected_answer_id, is_correct in graded:
            conn.execute(
                """
                INSERT INTO quiz_responses (attempt_id, question_id, selected_answer_id, is_correct)
                VALUES (?, ?, ?, ?)
                """,
                (attempt_id, question_id, selected_answer_id, is_correct),
            )
        conn.commit()

        attempt = dict(get_attempt(attempt_id, conn))
        attempt["responses"] = get_responses_with_detail(attempt_id, conn)
        return jsonify(attempt), 201
    finally:
        conn.close()


@app.get("/quizzes/<int:quiz_id>/attempts")
def list_attempts(quiz_id):
    conn = get_db_connection()
    try:
        if not get_quiz(quiz_id, conn):
            return jsonify({"error": "Quiz not found"}), 404

        student_name = request.args.get("student_name")
        query = """
            SELECT attempt_id, quiz_id, student_name, score, total_questions,
                   ai_feedback, started_at, completed_at
            FROM quiz_attempts
            WHERE quiz_id = ?
        """
        params = [quiz_id]
        if student_name:
            query += " AND student_name = ?"
            params.append(student_name)
        query += " ORDER BY COALESCE(completed_at, started_at) DESC, attempt_id DESC"

        attempts = conn.execute(query, params).fetchall()
        return jsonify([dict(row) for row in attempts])
    finally:
        conn.close()


@app.get("/attempts/<int:attempt_id>")
def get_attempt_details(attempt_id):
    conn = get_db_connection()
    try:
        attempt = get_attempt(attempt_id, conn)
        if attempt is None:
            return jsonify({"error": "Attempt not found"}), 404
        body = dict(attempt)
        body["responses"] = get_responses_with_detail(attempt_id, conn)
        return jsonify(body)
    finally:
        conn.close()


@app.post("/attempts/<int:attempt_id>/feedback")
def store_attempt_feedback(attempt_id):
    body, error = get_json_body()
    if error:
        return error

    ai_feedback = body.get("ai_feedback")
    if not ai_feedback:
        return jsonify({"error": "ai_feedback is required"}), 400

    conn = get_db_connection()
    try:
        if not get_attempt(attempt_id, conn):
            return jsonify({"error": "Attempt not found"}), 404
        conn.execute(
            "UPDATE quiz_attempts SET ai_feedback = ? WHERE attempt_id = ?", (ai_feedback, attempt_id)
        )
        conn.commit()
        return jsonify(dict(get_attempt(attempt_id, conn)))
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6004)
