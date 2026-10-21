"""Run the same persisted workflow as the HTTP API, without a browser.

Run a workflow:     python workflow_runner.py "Summarise the quizzes." --service quizzes
Record a decision:  python workflow_runner.py --service quizzes --workflow-id ID \
                        --decision "Partially Accept" --reviewer NAME --reason TEXT --evidence-used TEXT
"""

import argparse
import json

from app import app
from coordinator import DECISIONS


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
    with app.test_client() as client:
        if args.workflow_id:
            fields = ("decision", "reviewer", "reason", "evidence_used")
            missing = [name for name in fields if not getattr(args, name)]
            if missing:
                parser.error("recording a decision needs: " + ", ".join("--" + name.replace("_", "-") for name in missing))
            response = client.post(f"/workflow/{args.workflow_id}/decision", json={
                "service": args.service, **{name: getattr(args, name) for name in fields},
            })
        else:
            if not args.user_request:
                parser.error("user_request is required to run a workflow")
            response = client.post("/workflow", json={
                "service": args.service, "user_request": args.user_request, "record_id": args.record_id,
            })
        print(json.dumps(response.get_json(), indent=2))
        return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
