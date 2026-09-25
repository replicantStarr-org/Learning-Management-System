import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pipeline.common import services, settings
from pipeline.ingestion import ingest_services
from pipeline.querying import answer_question, retrieve_context


class RAGHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _read_json(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "rag-server"})
            return
        if self.path == "/services":
            self._send_json(200, {"status": "ok", "services": sorted(services())})
            return
        self._send_json(404, {"status": "error", "error": "not_found"})

    def do_POST(self):
        try:
            payload = self._read_json()
        except Exception as exc:
            self._send_json(400, {"status": "error", "error": f"invalid_json: {exc}"})
            return

        try:
            service = (payload.get("service") or "").strip() or None
            if service and service not in services():
                self._send_json(
                    404,
                    {"status": "error", "error": f"unknown service {service!r}", "available": sorted(services())},
                )
                return

            if self.path == "/ingest":
                result = ingest_services(service)
                # 502: the RAG server is fine, the service it read from was not.
                self._send_json({"success": 200, "partial": 207}.get(result["status"], 502), result)
                return

            if self.path in ("/retrieve", "/answer"):
                query = (payload.get("query") or "").strip()
                if not query:
                    self._send_json(400, {"status": "error", "error": "query is required"})
                    return
                k = int(payload["k"]) if payload.get("k") else None
                handler = retrieve_context if self.path == "/retrieve" else answer_question
                result = handler(query=query, k=k, service=service)
                self._send_json(200 if result["status"] == "success" else 500, result)
                return

            self._send_json(404, {"status": "error", "error": "not_found"})
        except Exception as exc:
            self._send_json(500, {"status": "error", "error": str(exc)})


def main():
    server_settings = settings()["server"]
    host, port = server_settings["host"], server_settings["port"]
    server = ThreadingHTTPServer((host, port), RAGHandler)
    print(f"RAG HTTP server running on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
