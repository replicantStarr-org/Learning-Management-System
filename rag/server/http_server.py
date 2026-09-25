"""The HTTP server: routes each request to its function in server/endpoints.py.

Run from rag/ with: .venv_rag/bin/python -m server.http_server
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline.common import settings

from . import endpoints
from .endpoints import ApiError

# (method, path) -> endpoint(payload) returning (status code, JSON body).
ROUTES = {
    ("GET", "/health"): endpoints.health,
    ("GET", "/services"): endpoints.services,
    ("POST", "/ingest"): endpoints.ingest,
    ("POST", "/retrieve"): endpoints.retrieve,
    ("POST", "/answer"): endpoints.answer,
}


class RAGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        endpoint = ROUTES.get((method, self.path))
        if endpoint is None:
            self._send_json(404, {"status": "error", "error": "not_found"})
            return

        try:
            payload = self._read_json() if method == "POST" else {}
            status, body = endpoint(payload)
        except ApiError as exc:
            status, body = exc.status, exc.body
        except Exception as exc:
            status, body = 500, {"status": "error", "error": str(exc)}
        self._send_json(status, body)

    def _read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b""
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, f"invalid_json: {exc}") from exc
        if not isinstance(payload, dict):
            raise ApiError(400, "request body must be a JSON object")
        return payload

    def _send_json(self, status_code: int, payload: dict):
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    server_settings = settings()["server"]
    host, port = server_settings["host"], server_settings["port"]
    server = ThreadingHTTPServer((host, port), RAGHandler)
    print(f"RAG HTTP server running on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
