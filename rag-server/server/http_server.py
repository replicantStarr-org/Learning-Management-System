"""The HTTP server: routes each request to its function in server/endpoints.py.

Start and stop it with ./run.sh and ./run.sh stop (run.ps1 on Windows).
"""

import json
import os
import signal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from pipeline.common import BASE_DIR, settings

from . import endpoints
from .endpoints import ApiError

# How run.sh / run.ps1 find the server to stop it. Removed on a clean exit.
PID_FILE = BASE_DIR / "rag-server.pid"

# (method, path) -> endpoint(payload) returning (status code, JSON body).
ROUTES = {
    ("GET", "/health"): endpoints.health,
    ("GET", "/services"): endpoints.services,
    ("POST", "/ingest"): endpoints.ingest,
    ("POST", "/clear"): endpoints.clear,
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


class RAGServer(ThreadingHTTPServer):
    # Request threads are waited for on shutdown instead of killed, so stopping
    # during an ingest lets it finish rather than leaving the index half-updated.
    daemon_threads = False


def stop_on_sigterm(signum, frame):
    # `kill` and `./run.sh stop` send SIGTERM; treat it exactly like Ctrl+C.
    raise KeyboardInterrupt


def main():
    server_settings = settings()["server"]
    host, port = server_settings["host"], server_settings["port"]
    url = server_settings["url"]
    server = RAGServer((host, port), RAGHandler)
    PID_FILE.write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, stop_on_sigterm)
    print(f"RAG HTTP server running on {host}:{port}, reachable at {url}", flush=True)
    # `url` is what clients use, `port` is what the server binds; they are
    # set separately in config.toml, so catch them drifting apart.
    if urlparse(url).port != port:
        print(f"warning: server.url {url} does not use server.port {port}; clients will not reach this server", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # The normal way to stop it, so no traceback.
        print("RAG HTTP server stopping; finishing requests in progress (Ctrl+C again to force)", flush=True)
    finally:
        try:
            server.server_close()  # waits for the request threads
        except KeyboardInterrupt:
            # A second Ctrl+C (or stop). os._exit, because a normal exit would
            # wait for the request threads all over again.
            PID_FILE.unlink(missing_ok=True)
            print("RAG HTTP server forced to stop; requests in progress were cut off", flush=True)
            os._exit(1)
        finally:
            PID_FILE.unlink(missing_ok=True)
    print("RAG HTTP server stopped", flush=True)


if __name__ == "__main__":
    main()
