import os

import requests

# The backend never opens the database file. Statements are sent to the database
# service, which owns the file, runs them and sends the rows back.
DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://localhost:6002")
TIMEOUT_SECONDS = 15

# Stands in, inside a transaction, for the id of the row the first statement
# inserted. Understood by the database service, so the rows that hang off a new
# row go in without a second round trip to read its id back.
NEW_ROW_ID = "$new_row_id"

class DatabaseError(RuntimeError):
    pass

def _post(path, payload):
    try:
        response = requests.post(
            f"{DATABASE_SERVICE_URL}{path}", json=payload, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise DatabaseError("The database service is unavailable.") from exc

    if not response.ok:
        raise DatabaseError(_error_message(response))

    try:
        return response.json()
    except ValueError as exc:
        raise DatabaseError("The database service returned a malformed response.") from exc

def _error_message(response):
    fallback = f"The database service returned {response.status_code}."
    try:
        return response.json().get("error") or fallback
    except ValueError:
        return fallback

def fetch(sql, params=()):
    """The rows one statement produced, as dictionaries."""
    return _post("/query", {"sql": sql, "params": list(params)}).get("rows", [])

# Query shapes live in database/construct_db.sql as views, so the only SQL here
# is the name of the view to read.
def query(view):
    return fetch(f"SELECT * FROM {view}")

def execute(sql, params=()):
    """Run one write, returning its 'last_row_id' and 'row_count'."""
    return transaction([(sql, params)])[0]

def transaction(statements):
    """Run '(sql, params)' pairs in one transaction, or none of them at all."""
    payload = {
        "statements": [{"sql": sql, "params": list(params)} for sql, params in statements]
    }

    return _post("/execute", payload).get("results", [])
