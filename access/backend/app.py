import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://localhost:6000")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
SESSION_LENGTH = timedelta(hours=24)


def request_data():
    body = request.get_json(silent=True) if request.is_json else request.form
    return body if hasattr(body, "get") else {}


def database_request(method, path, **kwargs):
    try:
        return requests.request(
            method, f"{DATABASE_SERVICE_URL}{path}", timeout=5, **kwargs
        )
    except requests.RequestException:
        return None


def valid_session():
    username = request.cookies.get("username")
    created_time = request.cookies.get("created_time")
    if not username or not created_time:
        return None

    try:
        created = datetime.fromisoformat(created_time)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    age = datetime.now(timezone.utc) - created
    return username if timedelta(0) <= age < SESSION_LENGTH else None


app = Flask(__name__)
CORS(app, supports_credentials=True)

@app.get("/")
def health():
    return jsonify({"service": "access-backend", "status": "running"})


@app.get("/session")
def session():
    username = valid_session()
    if not username:
        return jsonify({"authenticated": False, "login_url": f"{FRONTEND_URL}/login"}), 401
    return jsonify({"authenticated": True, "username": username})


@app.post("/register")
def register():
    body = request_data() or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    if len(username) > 80:
        return jsonify({"error": "Username must be 80 characters or fewer"}), 400

    response = database_request(
        "POST",
        "/users",
        json={
            "username": username,
            "hashed_password": generate_password_hash(password),
        },
    )
    if response is None:
        return jsonify({"error": "User database is unavailable"}), 503
    if response.status_code == 409:
        return jsonify({"error": "That username is already registered"}), 409
    if response.status_code != 201:
        return jsonify({"error": "Unable to create account"}), 502
    return jsonify({"message": "Account created. You can now log in."}), 201

@app.post("/login")
def login():
    body = request_data() or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    response = database_request("GET", f"/users/{quote(username, safe='')}")
    if response is None:
        return jsonify({"error": "User database is unavailable"}), 503
    if response.status_code == 404:
        return jsonify({"error": "Incorrect username or password"}), 401
    if not response.ok:
        return jsonify({"error": "Unable to log in"}), 502

    user = response.json()
    if not check_password_hash(user["hashed_password"], password):
        return jsonify({"error": "Incorrect username or password"}), 401

    created_time = datetime.now(timezone.utc).isoformat()
    result = jsonify({"message": "Login successful", "username": username})
    cookie_options = {
        "max_age": int(SESSION_LENGTH.total_seconds()),
        "samesite": "Lax",
        "path": "/",
    }
    result.set_cookie("username", username, **cookie_options)
    result.set_cookie("created_time", created_time, **cookie_options)
    return result

@app.post("/logout")
def logout():
    result = jsonify({"message": "Logged out"})
    result.delete_cookie("username", path="/")
    result.delete_cookie("created_time", path="/")
    return result

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
