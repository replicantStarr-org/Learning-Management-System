import sqlite3
from typing import Any

from flask import Flask, jsonify, request

from database_init import database_file

# Stands in, inside a transaction, for the id of the row the first statement
# inserted. The rows that hang off a new row (a resource's tags, a highlight's
# rectangles) can then be written in the same transaction as the row itself.
NEW_ROW_ID = "$new_row_id"

app = Flask(__name__)
# Rows go back in the order the statement selected the columns in, rather than
# alphabetically, so a caller reading them positionally still sees the table.
app.json.sort_keys = False

def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(database_file())
    connection.row_factory = sqlite3.Row

    return connection

class RequestError(ValueError):
    pass

def read_statement(payload: Any) -> tuple[str, list[Any]]:
    """One statement and its parameters, as sent by the backend."""
    if not isinstance(payload, dict):
        raise RequestError("Each statement must be a JSON object.")

    sql = payload.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        raise RequestError("Each statement needs a 'sql' string.")

    params = payload.get("params", [])
    if not isinstance(params, list):
        raise RequestError("'params' must be a JSON array.")

    return sql, params

@app.get("/health")
def health() -> Any:
    return jsonify({"service": "learning-resource-database", "status": "running"})

@app.post("/query")
def run_query() -> Any:
    """Run one statement and return the rows it produced."""
    try:
        sql, params = read_statement(request.get_json(silent=True))
    except RequestError as exc:
        return jsonify({"error": str(exc)}), 400

    connection = connect()
    try:
        rows = connection.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        connection.close()

    return jsonify({"rows": [dict(row) for row in rows]})

@app.post("/execute")
def run_statements() -> Any:
    """Run every statement in one transaction, or none of them.

    Nothing is committed unless all of them succeed, so a resource and its tags
    cannot end up half written even though the backend is a network hop away.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("statements"), list):
        return jsonify({"error": "Request body needs a 'statements' array."}), 400

    statements = body["statements"]
    if not statements:
        return jsonify({"error": "'statements' must not be empty."}), 400

    try:
        parsed = [read_statement(statement) for statement in statements]
    except RequestError as exc:
        return jsonify({"error": str(exc)}), 400

    connection = connect()
    try:
        # Commits on the way out, and rolls back if a statement raises.
        with connection:
            results = execute_all(connection, parsed)
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        connection.close()

    return jsonify({"results": results})

def execute_all(
    connection: sqlite3.Connection, statements: list[tuple[str, list[Any]]]
) -> list[dict[str, Any]]:
    new_row_id: int | None = None
    results = []

    for index, (sql, params) in enumerate(statements):
        cursor = connection.execute(sql, substitute(params, new_row_id))
        if index == 0:
            new_row_id = cursor.lastrowid

        results.append({"last_row_id": cursor.lastrowid, "row_count": cursor.rowcount})

    return results

def substitute(params: list[Any], new_row_id: int | None) -> list[Any]:
    if new_row_id is None:
        return params

    return [new_row_id if param == NEW_ROW_ID else param for param in params]

def main() -> None:
    app.run(host="0.0.0.0", port=6002)

if __name__ == "__main__":
    main()
