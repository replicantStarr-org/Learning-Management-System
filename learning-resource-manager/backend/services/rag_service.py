import os

import requests

# The RAG server runs on the host rather than in Docker, so from inside this
# container it is reached through host.docker.internal (see compose.yml).
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://localhost:5010")
TIMEOUT_SECONDS = 10

class RagError(RuntimeError):
    pass

def _request(method, path, payload=None):
    """The RAG server's status code and JSON body, passed back as they came.

    Its error responses are already JSON explaining what went wrong, so they are
    handed to the page unchanged. Only failing to get an answer at all is an
    error here.
    """
    try:
        response = requests.request(
            method, f"{RAG_SERVER_URL}{path}", json=payload, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise RagError("The RAG server is unavailable.") from exc

    try:
        return response.status_code, response.json()
    except ValueError as exc:
        raise RagError("The RAG server returned a malformed response.") from exc

def health():
    return _request("GET", "/health")
