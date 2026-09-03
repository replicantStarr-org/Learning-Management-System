from flask import Flask, jsonify, request
import sqlite3

app = Flask(__name__)

DATABASE_NAME = "data/assignments.db"

ASSIGNMENT_FIELDS = (
    "subject_id",
    "subject_name",
    "title",
    "description",
    "requirements",
    "due_at",
    "status",
    "priority",
    "weighting",
)
REQUIRED_FIELDS = ASSIGNMENT_FIELDS[:6]

ASSIGNMENT_COLUMNS = """
    assignment_id, subject_id, subject_name, title, description, requirements,
    due_at, status, priority, weighting, created_at, last_update
"""


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


def get_assignment(assignment_id, conn=None):
    owns_connection = conn is None
    conn = conn or get_db_connection()
    row = conn.execute(
        f"SELECT {ASSIGNMENT_COLUMNS} FROM assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
    if owns_connection:
        conn.close()
    return row


def get_latest_summary(assignment_id, conn):
    return conn.execute(
        """
        SELECT summary_id, assignment_id, ai_response, model, created_at
        FROM assignment_summaries
        WHERE assignment_id = ?
        ORDER BY summary_id DESC
        LIMIT 1
        """,
        (assignment_id,),
    ).fetchone()


def get_reminders(assignment_id, conn):
    return conn.execute(
        """
        SELECT reminder_id, assignment_id, remind_at, message, acknowledged, created_at
        FROM assignment_reminders
        WHERE assignment_id = ?
        ORDER BY remind_at
        """,
        (assignment_id,),
    ).fetchall()


@app.get("/")
def health():
    return jsonify({"service": "assignment-database-service", "status": "running"})


@app.get("/assignments")
def list_assignments():
    """List assignments, optionally filtered. All filters are combined with AND."""
    query = f"SELECT {ASSIGNMENT_COLUMNS} FROM assignments WHERE 1 = 1"
    params = []

    if request.args.get("subject_id"):
        query += " AND subject_id = ?"
        params.append(request.args["subject_id"])
    if request.args.get("status"):
        query += " AND status = ?"
        params.append(request.args["status"])
    if request.args.get("priority"):
        query += " AND priority = ?"
        params.append(request.args["priority"])
    if request.args.get("q"):
        query += " AND (title LIKE ? OR description LIKE ? OR subject_name LIKE ?)"
        pattern = f"%{request.args['q']}%"
        params.extend([pattern, pattern, pattern])

    query += " ORDER BY due_at, assignment_id"

    conn = get_db_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


@app.get("/assignments/upcoming")
def list_upcoming():
    """Assignments due between now and `days` days from now that are not finished yet."""
    days = request.args.get("days", "7")
    if not str(days).isdigit():
        return jsonify({"error": "days must be a positive number"}), 400

    conn = get_db_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT {ASSIGNMENT_COLUMNS}
            FROM assignments
            WHERE due_at >= datetime('now', 'localtime')
              AND due_at <= datetime('now', 'localtime', ?)
              AND status NOT IN ('Submitted', 'Graded')
            ORDER BY due_at, assignment_id
            """,
            (f"+{int(days)} days",),
        ).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


@app.get("/assignments/<int:assignment_id>")
def get_assignment_details(assignment_id):
    conn = get_db_connection()
    try:
        assignment = get_assignment(assignment_id, conn)
        if assignment is None:
            return jsonify({"error": "Assignment not found"}), 404

        body = dict(assignment)
        summary = get_latest_summary(assignment_id, conn)
        body["summary"] = dict(summary) if summary else None
        body["reminders"] = [dict(row) for row in get_reminders(assignment_id, conn)]
        return jsonify(body)
    finally:
        conn.close()


@app.post("/assignments")
def create_assignment():
    body, error = get_json_body()
    if error:
        return error

    required = [field for field in REQUIRED_FIELDS if str(body.get(field, "")).strip() == ""]
    if required:
        return jsonify({"error": "Missing required fields", "fields": required}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO assignments
                (subject_id, subject_name, title, description, requirements,
                 due_at, status, priority, weighting)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body["subject_id"], body["subject_name"], body["title"], body["description"],
                body["requirements"], body["due_at"], body.get("status", "Not Started"),
                body.get("priority", "Medium"), body.get("weighting", 0),
            ),
        )
        conn.commit()
        return jsonify(dict(get_assignment(cursor.lastrowid, conn))), 201
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.put("/assignments/<int:assignment_id>")
def update_assignment(assignment_id):
    body, error = get_json_body()
    if error:
        return error

    fields = [field for field in ASSIGNMENT_FIELDS if field in body]
    if not fields:
        return jsonify({"error": "At least one assignment field is required"}), 400

    conn = get_db_connection()
    try:
        if not get_assignment(assignment_id, conn):
            return jsonify({"error": "Assignment not found"}), 404

        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [body[field] for field in fields] + [assignment_id]
        conn.execute(f"UPDATE assignments SET {assignments} WHERE assignment_id = ?", values)
        conn.commit()
        return jsonify(dict(get_assignment(assignment_id, conn)))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.delete("/assignments/<int:assignment_id>")
def delete_assignment(assignment_id):
    conn = get_db_connection()
    try:
        if not get_assignment(assignment_id, conn):
            return jsonify({"error": "Assignment not found"}), 404

        conn.execute("DELETE FROM assignment_reminders WHERE assignment_id = ?", (assignment_id,))
        conn.execute("DELETE FROM assignment_summaries WHERE assignment_id = ?", (assignment_id,))
        conn.execute("DELETE FROM assignments WHERE assignment_id = ?", (assignment_id,))
        conn.commit()
        return "", 204
    finally:
        conn.close()


@app.post("/assignments/<int:assignment_id>/summary")
def store_summary(assignment_id):
    body, error = get_json_body()
    if error:
        return error

    ai_response = str(body.get("ai_response", "")).strip()
    if not ai_response:
        return jsonify({"error": "ai_response is required"}), 400

    conn = get_db_connection()
    try:
        if not get_assignment(assignment_id, conn):
            return jsonify({"error": "Assignment not found"}), 404

        cursor = conn.execute(
            "INSERT INTO assignment_summaries (assignment_id, ai_response, model) VALUES (?, ?, ?)",
            (assignment_id, ai_response, str(body.get("model", "unknown"))),
        )
        conn.commit()
        summary = conn.execute(
            """
            SELECT summary_id, assignment_id, ai_response, model, created_at
            FROM assignment_summaries
            WHERE summary_id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify(dict(summary)), 201
    finally:
        conn.close()


@app.get("/reminders")
def list_reminders():
    """Unacknowledged reminders that have already fired, for assignments still due.

    `within_days` bounds how far into the future the linked due date may be, so the
    frontend can poll for deadline notifications without pulling historic reminders.
    """
    within_days = request.args.get("within_days", "14")
    if not str(within_days).isdigit():
        return jsonify({"error": "within_days must be a positive number"}), 400

    query = """
        SELECT r.reminder_id, r.assignment_id, r.remind_at, r.message, r.acknowledged,
               a.title, a.subject_name, a.due_at, a.status, a.priority
        FROM assignment_reminders r
        JOIN assignments a ON a.assignment_id = r.assignment_id
        WHERE r.remind_at <= datetime('now', 'localtime')
          AND a.due_at <= datetime('now', 'localtime', ?)
          AND r.acknowledged = 0
          AND a.status NOT IN ('Submitted', 'Graded')
        ORDER BY a.due_at, r.reminder_id
    """

    conn = get_db_connection()
    try:
        rows = conn.execute(query, (f"+{int(within_days)} days",)).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


@app.post("/assignments/<int:assignment_id>/reminders")
def create_reminder(assignment_id):
    body, error = get_json_body()
    if error:
        return error

    remind_at = str(body.get("remind_at", "")).strip()
    message = str(body.get("message", "")).strip()
    if not remind_at or not message:
        return jsonify({"error": "remind_at and message are required"}), 400

    conn = get_db_connection()
    try:
        if not get_assignment(assignment_id, conn):
            return jsonify({"error": "Assignment not found"}), 404

        cursor = conn.execute(
            "INSERT INTO assignment_reminders (assignment_id, remind_at, message) VALUES (?, ?, ?)",
            (assignment_id, remind_at, message),
        )
        conn.commit()
        reminder = conn.execute(
            """
            SELECT reminder_id, assignment_id, remind_at, message, acknowledged, created_at
            FROM assignment_reminders
            WHERE reminder_id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify(dict(reminder)), 201
    finally:
        conn.close()


@app.post("/reminders/<int:reminder_id>/acknowledge")
def acknowledge_reminder(reminder_id):
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "UPDATE assignment_reminders SET acknowledged = 1 WHERE reminder_id = ?", (reminder_id,)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Reminder not found"}), 404
        conn.commit()
        return "", 204
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6003)
