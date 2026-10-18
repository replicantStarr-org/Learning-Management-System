"""Run the same persisted workflow as the HTTP API, without a browser."""

import argparse
import json

from app import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("user_request")
    parser.add_argument("--service", default="subjects")
    parser.add_argument("--record-id", type=int)
    args = parser.parse_args()
    with app.test_client() as client:
        response = client.post("/workflow", json={
            "service": args.service, "user_request": args.user_request, "record_id": args.record_id,
        })
        print(json.dumps(response.get_json(), indent=2))
        return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
