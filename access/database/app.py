import os
import sqlite3

from flask import Flask, jsonify, request

app = Flask(__name__)
DATABASE_NAME = os.getenv("DATABASE_NAME", "data/users.db")


def get_connection():
    connection = sqlite3.connect(DATABASE_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def serialize_user(row):
    return dict(row) if row else None


@app.get("/")
def health():
    return jsonify({"service": "access-database", "status": "running"})


@app.get("/users/<string:username>")
def get_user(username):
    with get_connection() as connection:
        user = connection.execute(
            "SELECT username, hashed_password, created_time FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if user is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify(serialize_user(user))


@app.post("/users")
def create_user():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    username = str(body.get("username", "")).strip()
    hashed_password = str(body.get("hashed_password", ""))
    if not username or not hashed_password:
        return jsonify({"error": "username and hashed_password are required"}), 400

    try:
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
                (username, hashed_password),
            )
            user = connection.execute(
                "SELECT username, created_time FROM users WHERE username = ?",
                (username,),
            ).fetchone()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 409

    return jsonify(serialize_user(user)), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000)
