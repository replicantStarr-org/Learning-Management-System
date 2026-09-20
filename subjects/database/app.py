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


def tags_for_subject(subject_id, conn):
    rows = conn.execute(
        """
        SELECT t.tag_id, t.name
        FROM tags AS t
        JOIN subject_tags AS st ON st.tag_id = t.tag_id
        WHERE st.subject_id = ?
        ORDER BY t.tag_id
        """,
        (subject_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def subject_dict(row, conn):
    result = dict(row)
    result["tags"] = tags_for_subject(row["subject_id"], conn)
    return result


def subject_response(row, conn=None):
    owns_connection = conn is None
    conn = conn or get_db_connection()
    result = jsonify(subject_dict(row, conn))
    if owns_connection:
        conn.close()
    return result


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
        return jsonify([subject_dict(row, conn) for row in subjects])
    finally:
        conn.close()


@app.get("/subjects/<int:subject_id>")
def get_subject_details(subject_id):
    row = get_subject(subject_id)
    if row is None:
        return jsonify({"error": "Subject not found"}), 404
    return subject_response(row)


@app.get("/tags")
def get_tags():
    conn = get_db_connection()
    try:
        tags = conn.execute(
            """
            SELECT t.tag_id, t.name, COUNT(st.subject_id) AS subject_count
            FROM tags AS t
            LEFT JOIN subject_tags AS st ON st.tag_id = t.tag_id
            GROUP BY t.tag_id
            ORDER BY t.tag_id
            """
        ).fetchall()
        return jsonify([dict(row) for row in tags])
    finally:
        conn.close()


@app.get("/tags/<int:tag_id>")
def get_tag(tag_id):
    conn = get_db_connection()
    try:
        tag = conn.execute(
            """
            SELECT t.tag_id, t.name, COUNT(st.subject_id) AS subject_count
            FROM tags AS t
            LEFT JOIN subject_tags AS st ON st.tag_id = t.tag_id
            WHERE t.tag_id = ?
            GROUP BY t.tag_id
            """,
            (tag_id,),
        ).fetchone()
        if tag is None:
            return jsonify({"error": "Tag not found"}), 404
        return jsonify(dict(tag))
    finally:
        conn.close()


def get_tag_name(body):
    if "name" not in body:
        return None, jsonify({"error": "name is required"}), 400
    if not isinstance(body["name"], str):
        return None, jsonify({"error": "name must be a string"}), 400
    return body["name"], None, None


@app.post("/tags")
def create_tag():
    body, error = get_json_body()
    if error:
        return error
    name, error_response, status = get_tag_name(body)
    if error_response:
        return error_response, status
    conn = get_db_connection()
    try:
        cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        conn.commit()
        tag = conn.execute(
            "SELECT tag_id, name, 0 AS subject_count FROM tags WHERE tag_id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify(dict(tag)), 201
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"error": "A tag with that name already exists"}), 409
    finally:
        conn.close()


@app.put("/tags/<int:tag_id>")
def update_tag(tag_id):
    body, error = get_json_body()
    if error:
        return error
    name, error_response, status = get_tag_name(body)
    if error_response:
        return error_response, status
    conn = get_db_connection()
    try:
        if conn.execute("SELECT 1 FROM tags WHERE tag_id = ?", (tag_id,)).fetchone() is None:
            return jsonify({"error": "Tag not found"}), 404
        conn.execute("UPDATE tags SET name = ? WHERE tag_id = ?", (name, tag_id))
        conn.commit()
        tag = conn.execute(
            """
            SELECT t.tag_id, t.name, COUNT(st.subject_id) AS subject_count
            FROM tags AS t LEFT JOIN subject_tags AS st ON st.tag_id = t.tag_id
            WHERE t.tag_id = ? GROUP BY t.tag_id
            """,
            (tag_id,),
        ).fetchone()
        return jsonify(dict(tag))
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"error": "A tag with that name already exists"}), 409
    finally:
        conn.close()


@app.delete("/tags/<int:tag_id>")
def delete_tag(tag_id):
    conn = get_db_connection()
    try:
        cursor = conn.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "Tag not found"}), 404
        conn.commit()
        return "", 204
    finally:
        conn.close()


@app.get("/subjects/<int:subject_id>/tags")
def get_subject_tags(subject_id):
    conn = get_db_connection()
    try:
        if not get_subject(subject_id, conn):
            return jsonify({"error": "Subject not found"}), 404
        return jsonify(tags_for_subject(subject_id, conn))
    finally:
        conn.close()


@app.put("/subjects/<int:subject_id>/tags")
@app.post("/subjects/<int:subject_id>/tags")
def replace_subject_tags(subject_id):
    body, error = get_json_body()
    if error:
        return error
    tag_ids = body.get("tag_ids")
    if not isinstance(tag_ids, list) or any(not isinstance(tag_id, int) for tag_id in tag_ids):
        return jsonify({"error": "tag_ids must be a list of integers"}), 400
    if len(tag_ids) != len(set(tag_ids)):
        return jsonify({"error": "tag_ids must not contain duplicates"}), 400
    conn = get_db_connection()
    try:
        if not get_subject(subject_id, conn):
            return jsonify({"error": "Subject not found"}), 404
        if tag_ids:
            placeholders = ",".join("?" for _ in tag_ids)
            found = conn.execute(
                f"SELECT tag_id FROM tags WHERE tag_id IN ({placeholders})", tag_ids
            ).fetchall()
            if len(found) != len(tag_ids):
                return jsonify({"error": "One or more tags were not found"}), 400
        conn.execute("DELETE FROM subject_tags WHERE subject_id = ?", (subject_id,))
        conn.executemany(
            "INSERT INTO subject_tags (subject_id, tag_id) VALUES (?, ?)",
            [(subject_id, tag_id) for tag_id in tag_ids],
        )
        conn.execute(
            "UPDATE subjects SET last_update = CURRENT_TIMESTAMP WHERE subject_id = ?",
            (subject_id,),
        )
        conn.commit()
        return jsonify(tags_for_subject(subject_id, conn))
    finally:
        conn.close()


@app.delete("/subjects/<int:subject_id>/tags/<int:tag_id>")
def remove_subject_tag(subject_id, tag_id):
    conn = get_db_connection()
    try:
        if not get_subject(subject_id, conn):
            return jsonify({"error": "Subject not found"}), 404
        cursor = conn.execute(
            "DELETE FROM subject_tags WHERE subject_id = ? AND tag_id = ?",
            (subject_id, tag_id),
        )
        if cursor.rowcount:
            conn.execute(
                "UPDATE subjects SET last_update = CURRENT_TIMESTAMP WHERE subject_id = ?",
                (subject_id,),
            )
            conn.commit()
        return "", 204
    finally:
        conn.close()


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
