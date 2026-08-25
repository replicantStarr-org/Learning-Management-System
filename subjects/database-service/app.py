from flask import Flask, jsonify, request
import sqlite3

app = Flask(__name__)

DATABASE_NAME = "data/subjects.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/")
def health():
    return jsonify({"service": "database-service", "status": "running"})

@app.get("/subjects")
def get_subjects():
    conn = get_db_connection()
    students = conn.execute(
        "SELECT subject_id, code, name FROM subjects"
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in students])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6001, debug=True)
