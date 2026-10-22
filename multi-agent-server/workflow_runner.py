"""Run the same persisted workflow as the HTTP API, without a browser.

Run a workflow:     python workflow_runner.py "Summarise the quizzes." --service quizzes
Record a decision:  python workflow_runner.py --service quizzes --workflow-id ID \
                        --decision "Partially Accept" --reviewer NAME --reason TEXT --evidence-used TEXT
"""

import argparse
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from app import app
from coordinator import DECISIONS


def _post_to_running_server(path, payload):
    """Record decisions through the live server so its lock serialises every writer."""
    base = os.getenv("MULTI_AGENT_SERVER_URL", f"http://127.0.0.1:{os.getenv('PORT', '15004')}")
    if urlsplit(base).scheme not in {"http", "https"}:
        return 503, {"status": "error", "error": "MULTI_AGENT_SERVER_URL must be an http(s) URL"}
    request = urllib.request.Request(  # noqa: S310 - scheme checked above
        base.rstrip("/") + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - scheme checked above
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")
    except OSError as exc:
        return 503, {"status": "error", "error": f"multi-agent server not reachable at {base}: {exc}"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("user_request", nargs="?")
    parser.add_argument("--service", default="subjects")
    parser.add_argument("--record-id", type=int)
    parser.add_argument("--workflow-id", help="record a human decision for this workflow instead of running one")
    parser.add_argument("--decision", choices=DECISIONS)
    parser.add_argument("--reviewer")
    parser.add_argument("--reason")
    parser.add_argument("--evidence-used")
    args = parser.parse_args()
    if args.workflow_id:
        fields = ("decision", "reviewer", "reason", "evidence_used")
        missing = [name for name in fields if not getattr(args, name)]
        if missing:
            parser.error("recording a decision needs: " + ", ".join("--" + name.replace("_", "-") for name in missing))
        status, body = _post_to_running_server(f"/workflow/{args.workflow_id}/decision", {
            "service": args.service, **{name: getattr(args, name) for name in fields},
        })
    else:
        if not args.user_request:
            parser.error("user_request is required to run a workflow")
        with app.test_client() as client:
            response = client.post("/workflow", json={
                "service": args.service, "user_request": args.user_request, "record_id": args.record_id,
            })
        status, body = response.status_code, response.get_json()
    print(json.dumps(body, indent=2))
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
