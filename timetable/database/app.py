from flask import Flask, jsonify, request
import sqlite3

app = Flask(__name__)

DATABASE_NAME = "data/timetable.db"

ENTRY_FIELDS = (
    "username",
    "date",
    "day_of_week",
    "start_time",
    "end_time",
    "activity_name",
    "category",
    "notes",
    "ai_generated",
    "all_day",
)
ENTRY_REQUIRED_FIELDS = (
    "username",
    "date",
    "day_of_week",
    "start_time",
    "end_time",
    "activity_name",
    "category",
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


def entry_response(row):
    return jsonify(dict(row))


def get_entry(timetable_id, conn=None):
    owns_connection = conn is None
    conn = conn or get_db_connection()
    row = conn.execute(
        """
        SELECT timetable_id, username, date, day_of_week, start_time, end_time,
               activity_name, category, notes, ai_generated, all_day, last_updated
        FROM timetable_entries
        WHERE timetable_id = ?
        """,
        (timetable_id,),
    ).fetchone()
    if owns_connection:
        conn.close()
    return row


@app.get("/")
def health():
    return jsonify({"service": "timetable-database", "status": "running"})


@app.get("/timetable")
def list_entries():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"error": "username is required"}), 400

    week_start = request.args.get("week_start")
    week_end = request.args.get("week_end")

    query = (
        "SELECT timetable_id, username, date, day_of_week, start_time, end_time, "
        "activity_name, category, notes, ai_generated, all_day, last_updated "
        "FROM timetable_entries WHERE username = ?"
    )
    params = [username]
    if week_start and week_end:
        query += " AND date BETWEEN ? AND ?"
        params += [week_start, week_end]
    query += " ORDER BY date, start_time"

    conn = get_db_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


@app.get("/timetable/<int:timetable_id>")
def get_entry_details(timetable_id):
    row = get_entry(timetable_id)
    if row is None:
        return jsonify({"error": "Timetable entry not found"}), 404
    return entry_response(row)


@app.post("/timetable")
def create_entry():
    body, error = get_json_body()
    if error:
        return error

    missing = [field for field in ENTRY_REQUIRED_FIELDS if field not in body]
    if missing:
        return jsonify({"error": "Missing required fields", "fields": missing}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO timetable_entries (
                username, date, day_of_week, start_time, end_time,
                activity_name, category, notes, ai_generated, all_day
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body["username"],
                body["date"],
                body["day_of_week"],
                body["start_time"],
                body["end_time"],
                body["activity_name"],
                body["category"],
                body.get("notes"),
                bool(body.get("ai_generated", False)),
                bool(body.get("all_day", False)),
            ),
        )
        conn.commit()
        entry = get_entry(cursor.lastrowid, conn)
        return entry_response(entry), 201
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.put("/timetable/<int:timetable_id>")
def update_entry(timetable_id):
    body, error = get_json_body()
    if error:
        return error

    fields = [field for field in ENTRY_FIELDS if field in body]
    if not fields:
        return jsonify({"error": "At least one timetable field is required"}), 400

    conn = get_db_connection()
    try:
        if not get_entry(timetable_id, conn):
            return jsonify({"error": "Timetable entry not found"}), 404

        assignments = ", ".join(f"{field} = ?" for field in fields)
        values = [body[field] for field in fields] + [timetable_id]
        conn.execute(
            f"UPDATE timetable_entries SET {assignments} WHERE timetable_id = ?", values
        )
        conn.commit()
        return entry_response(get_entry(timetable_id, conn))
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()


@app.delete("/timetable/<int:timetable_id>")
def delete_entry(timetable_id):
    conn = get_db_connection()
    try:
        if not get_entry(timetable_id, conn):
            return jsonify({"error": "Timetable entry not found"}), 404
        conn.execute("DELETE FROM timetable_entries WHERE timetable_id = ?", (timetable_id,))
        conn.commit()
        return "", 204
    finally:
        conn.close()


@app.get("/timetable/plans/latest")
def latest_plan():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"error": "username is required"}), 400

    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT plan_id, username, plan_text, suggested_entries, created_at, regenerated_at
            FROM ai_timetable_plans
            WHERE username = ?
            ORDER BY COALESCE(regenerated_at, created_at) DESC, plan_id DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
        if row is None:
            return jsonify({"error": "No plan found"}), 404
        return jsonify(dict(row))
    finally:
        conn.close()


@app.post("/timetable/plans")
def create_plan():
    body, error = get_json_body()
    if error:
        return error

    username = str(body.get("username", "")).strip()
    plan_text = str(body.get("plan_text", "")).strip()
    if not username or not plan_text:
        return jsonify({"error": "username and plan_text are required"}), 400
    suggested_entries = body.get("suggested_entries")

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO ai_timetable_plans (username, plan_text, suggested_entries) VALUES (?, ?, ?)",
            (username, plan_text, suggested_entries),
        )
        conn.commit()
        plan = conn.execute(
            "SELECT plan_id, username, plan_text, suggested_entries, created_at, regenerated_at "
            "FROM ai_timetable_plans WHERE plan_id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify(dict(plan)), 201
    finally:
        conn.close()


@app.put("/timetable/plans/<int:plan_id>")
def update_plan(plan_id):
    body, error = get_json_body()
    if error:
        return error

    plan_text = str(body.get("plan_text", "")).strip()
    if not plan_text:
        return jsonify({"error": "plan_text is required"}), 400
    suggested_entries = body.get("suggested_entries")

    conn = get_db_connection()
    try:
        existing = conn.execute(
            "SELECT plan_id FROM ai_timetable_plans WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        if existing is None:
            return jsonify({"error": "Plan not found"}), 404

        conn.execute(
            "UPDATE ai_timetable_plans SET plan_text = ?, suggested_entries = ?, "
            "regenerated_at = CURRENT_TIMESTAMP WHERE plan_id = ?",
            (plan_text, suggested_entries, plan_id),
        )
        conn.commit()
        plan = conn.execute(
            "SELECT plan_id, username, plan_text, suggested_entries, created_at, regenerated_at "
            "FROM ai_timetable_plans WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        return jsonify(dict(plan))
    finally:
        conn.close()


@app.get("/timetable/advice")
def list_advice():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"error": "username is required"}), 400

    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT advice_id, username, question, advice_text, created_at
            FROM ai_advice_logs
            WHERE username = ?
            ORDER BY created_at DESC, advice_id DESC
            """,
            (username,),
        ).fetchall()
        return jsonify([dict(row) for row in rows])
    finally:
        conn.close()


@app.post("/timetable/advice")
def create_advice():
    body, error = get_json_body()
    if error:
        return error

    username = str(body.get("username", "")).strip()
    advice_text = str(body.get("advice_text", "")).strip()
    if not username or not advice_text:
        return jsonify({"error": "username and advice_text are required"}), 400

    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "INSERT INTO ai_advice_logs (username, question, advice_text) VALUES (?, ?, ?)",
            (username, body.get("question"), advice_text),
        )
        conn.commit()
        advice = conn.execute(
            "SELECT advice_id, username, question, advice_text, created_at "
            "FROM ai_advice_logs WHERE advice_id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return jsonify(dict(advice)), 201
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6005, debug=True)
