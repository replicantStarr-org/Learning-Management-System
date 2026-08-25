from flask import Flask, jsonify, request
import sqlite3

app = Flask(__name__)

DATABASE_NAME = "data/subjects.db"

SUBJECT_FIELDS = (
    "code",
    "name",
    "description",
    "semester",
    "coordinator",
    "status",
)


def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row

    # foreign keys are disabled by default
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_json_body():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    return body, None


def subject_response(row):
    return jsonify(dict(row))


def get_subject(subject_id, conn=None):
    owns_connection = conn is None
    conn = conn or get_db_connection()
    row = conn.execute(
        """
        SELECT subject_id, code, name, description, semester,
               coordinator, status, last_update
        FROM subjects
        WHERE subject_id = ?
        """,
        (subject_id,),
    ).fetchone()
    if owns_connection:
        conn.close()
    return row


def create_summary(subject_id, body):
    if "ai_response" not in body or body["ai_response"] in (None, ""):
        return jsonify({"error": "ai_response is required"}), 400

    conn = get_db_connection()
    try:
        if not get_subject(subject_id, conn):
            return jsonify({"error": "Subject not found"}), 404

        cursor = conn.execute(
            "INSERT INTO subject_ai_summaries (ai_response, subject_id) VALUES (?, ?)",
            (body["ai_response"], subject_id),
        )
        conn.commit()
        summary = conn.execute(
            """
            SELECT summary_id, ai_response, subject_id, timestamp
            FROM subject_ai_summaries
            WHERE summary_id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify(dict(summary)), 201
    finally:
        conn.close()


@app.get("/")
def health():
    return jsonify({"service": "database-service", "status": "running"})


@app.get("/subjects")
def get_subjects():
    conn = get_db_connection()
    try:
        subjects = conn.execute(
            "SELECT subject_id, code, name FROM subjects ORDER BY subject_id"
        ).fetchall()
        return jsonify([dict(row) for row in subjects])
    finally:
        conn.close()


@app.get("/subjects/<int:subject_id>")
def get_subject_details(subject_id):
    row = get_subject(subject_id)
    if row is None:
        return jsonify({"error": "Subject not found"}), 404
    return subject_response(row)


@app.post("/subjects")
def create_subject():
    body, error = get_json_body()
    if error:
        return error

    missing = [field for field in SUBJECT_FIELDS if field not in body]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO subjects (code, name, description, semester, coordinator, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            tuple(body[field] for field in SUBJECT_FIELDS),
        )
        conn.commit()
        subject = get_subject(cursor.lastrowid, conn)
        return subject_response(subject), 201
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.put("/subjects/<int:subject_id>")
def update_subject(subject_id):
    body, error = get_json_body()
    if error:
        return error

    fields = [field for field in SUBJECT_FIELDS if field in body]
    if not fields:
        return jsonify({"error": "At least one subject field is required"}), 400

    conn = get_db_connection()
    try:
        if not get_subject(subject_id, conn):
            return jsonify({"error": "Subject not found"}), 404

        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [body[field] for field in fields] + [subject_id]
        conn.execute(
            f"UPDATE subjects SET {assignments} WHERE subject_id = ?", values
        )
        conn.commit()
        return subject_response(get_subject(subject_id, conn))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.delete("/subjects/<int:subject_id>")
def delete_subject(subject_id):
    conn = get_db_connection()
    try:
        if not get_subject(subject_id, conn):
            return jsonify({"error": "Subject not found"}), 404

        # remove any related summaries first
        conn.execute(
            "DELETE FROM subject_ai_summaries WHERE subject_id = ?", (subject_id,)
        )
        conn.execute("DELETE FROM subjects WHERE subject_id = ?", (subject_id,))
        conn.commit()
        return "", 204
    finally:
        conn.close()


# nested route since they are related to a certain subject
@app.post("/subjects/<int:subject_id>/summaries")
@app.post("/subjects/<int:subject_id>/ai-summaries")
@app.post("/subjects/<int:subject_id>/ai-summary")
def create_subject_summary(subject_id):
    body, error = get_json_body()
    if error:
        return error
    return create_summary(subject_id, body)


@app.post("/summaries")
@app.post("/ai-summaries")
def create_summary_for_subject():
    body, error = get_json_body()
    if error:
        return error
    if "subject_id" not in body:
        return jsonify({"error": "subject_id is required"}), 400
    return create_summary(body["subject_id"], body)


@app.get("/subjects/<int:subject_id>/summaries")
@app.get("/subjects/<int:subject_id>/ai-summaries")
def list_subject_summaries(subject_id):
    conn = get_db_connection()
    try:
        if not get_subject(subject_id, conn):
            return jsonify({"error": "Subject not found"}), 404

        summaries = conn.execute(
            """
            SELECT summary_id, timestamp
            FROM subject_ai_summaries
            WHERE subject_id = ?
            ORDER BY timestamp DESC, summary_id DESC
            """,
            (subject_id,),
        ).fetchall()
        return jsonify([dict(row) for row in summaries])
    finally:
        conn.close()


@app.get("/summaries/<int:summary_id>")
@app.get("/ai-summaries/<int:summary_id>")
def get_summary(summary_id):
    conn = get_db_connection()
    try:
        summary = conn.execute(
            """
            SELECT summary_id, ai_response, subject_id, timestamp
            FROM subject_ai_summaries
            WHERE summary_id = ?
            """,
            (summary_id,),
        ).fetchone()
        if summary is None:
            return jsonify({"error": "AI summary not found"}), 404
        return jsonify(dict(summary))
    finally:
        conn.close()


@app.delete("/summaries/<int:summary_id>")
@app.delete("/ai-summaries/<int:summary_id>")
def delete_summary(summary_id):
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM subject_ai_summaries WHERE summary_id = ?", (summary_id,)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "AI summary not found"}), 404
        conn.commit()
        return "", 204
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6001, debug=True)
