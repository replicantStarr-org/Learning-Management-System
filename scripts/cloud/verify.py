"""Cloud verification checks to ensure environment is correctly configured and operational."""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

state = Path(os.environ.get("STATE_DIR", ".cloud"))
report = Path(os.environ.get("REPORT_DIR", "reports/cloud/local"))
report.mkdir(parents=True, exist_ok=True)
results = []


def check(name, condition):
    results.append({"check": name, "passed": bool(condition)})
    print(f'{"PASS" if condition else "FAIL"}: {name}', flush=True)
    if not condition:
        raise RuntimeError(name)


def wait(url, session, expected=200):
    for _ in range(40):
        try:
            response = session.get(url, timeout=30)
            if response.status_code == expected:
                return response
        except requests.RequestException:
            pass
        time.sleep(5)
    raise RuntimeError("Endpoint did not become ready: " + url)


def main():
    auth = json.loads((state / "auth.json").read_text())
    release = json.loads((state / "release.json").read_text())
    apps = json.loads((report / "apps.json").read_text())

    # setup session with the basic auth to ensure all requests are authenticated
    session = requests.Session()
    session.auth = (auth["username"], auth["password"])

    subjects_url = None
    # check each app is available and properly configured (including auth)
    for app in apps:
        url = "https://" + app["fqdn"]

        response = wait(url + "/", session)
        check(app["name"] + " browser hardening", response.headers.get("X-Content-Type-Options") == "nosniff")
        check(app["name"] + " authenticated frontend", response.status_code == 200)

        challenge = requests.get(url + "/", timeout=30)
        check(app["name"] + " authentication enforced", challenge.status_code == 401)

        # check that the access correctly redirects to the login page
        # without changing origin (e.g. changing to port 3000 like the local deployment)
        if app["name"] == "lh-access":
            redirect = session.get(url + "/", allow_redirects=False, timeout=30)
            check("Access same-origin login redirect", redirect.status_code == 302
                  and redirect.headers.get("Location") == "/login")

        if app["name"] == "lh-subjects":
            subjects_url = url


    check("all six feature sites present", len(apps) == 6 and subjects_url)

    # additional checks just for the subjects service (for now)
    # other services can have checks added as needed
    check("subject feature site present", subjects_url)

    config = wait(subjects_url + "/config", session).json()
    check("expected runtime profile", config["profile"] == release["profile"])
    ai_services_deployed = release["profile"] == "bonus"
    check("runtime feature flags", all(value is ai_services_deployed for value in config["flags"].values()))

    check("API authentication enforced", requests.get(subjects_url + "/api/v1/subjects", timeout=30).status_code == 401)

    rows = wait(subjects_url + "/api/v1/subjects", session).json()
    check("database/API reachable", isinstance(rows, list) and len(rows) > 0)

    payload = {"code": "CLOUD" + uuid.uuid4().hex[:8].upper(), "name": "Cloud acceptance fixture",
               "description": "Temporary verification record", "semester": "Spring", "coordinator": "Demo", "status": "Open"}
    subject_id = None
    try:
        created = session.post(subjects_url + "/api/v1/subjects", json=payload, timeout=30)
        check("Subjects CREATE", created.status_code == 201)

        subject_id = created.json()["subject_id"]
        path = subjects_url + f"/api/v1/subjects/{subject_id}"
        check("Subjects READ", session.get(path, timeout=30).json()["code"] == payload["code"])

        updated = session.patch(path, json={"name": "Updated cloud fixture"}, timeout=30)
        check("Subjects UPDATE", updated.status_code == 200 and updated.json()["name"] == "Updated cloud fixture")

        fragment = session.get(subjects_url + f"/subjects/{subject_id}", timeout=30)
        check("same-origin generated HTML", fragment.status_code == 200 and "localhost:5001" not in fragment.text)

        csrf = session.patch(path, json={"name": "Must not be applied"}, headers={"Origin": "https://attacker.invalid"}, timeout=30)
        check("cross-origin mutation rejected", csrf.status_code == 403)

        check("Subjects DELETE", session.delete(path, timeout=30).status_code == 204)
        check("Subjects deleted record absent", session.get(path, timeout=30).status_code == 404)
        subject_id = None
    finally:
        if subject_id:
            session.delete(subjects_url + f"/api/v1/subjects/{subject_id}", timeout=30)

    for endpoint in ("/api/v1/subjects", "/tags"):
        check(endpoint + " available", session.get(subjects_url + endpoint, timeout=30).status_code == 200)

    if ai_services_deployed:
        ai = session.post(subjects_url + "/subjects/questions", data={"subject_id": "1", "question": "What is this subject about?"}, timeout=180)
        check("AI real inference", ai.status_code == 200 and "Answer" in ai.text and ai.headers.get("HX-Error") != "true")

        mcp = session.post(subjects_url + "/mcp/query/field", json={"field": "code", "value": "ASD101"}, timeout=90)
        check("MCP real tool call", mcp.status_code == 200 and "ASD101" in mcp.text)

        ingest = session.post(subjects_url + "/rag/ingest", json={}, timeout=120)
        check("RAG ingestion", ingest.status_code == 200 and ingest.json().get("status") == "success")

        answer = session.post(subjects_url + "/rag/answer", json={"query": "What does Advanced Software Development cover?"}, timeout=180)
        body = answer.json()
        check("RAG grounded inference", answer.status_code == 200 and body.get("citations") and body.get("answer") != "Insufficient evidence.")

        workflow = session.post(subjects_url + "/multi-agent/workflow", json={"user_request": "Give a brief overview of the subjects in the catalogue, grounded only in evidence."}, timeout=180)
        body = workflow.json()
        check("multi-agent three roles", workflow.status_code == 200 and all(body.get(f"{role}_result", {}).get("status") == "success" for role in ("planner", "worker", "reviewer")))
        check("human approval remains pending", body["human_decision"]["status"] == "pending")
    else:
        for path, payload in (("/subjects/1/summary", {}), ("/subjects/questions", {}),
                              ("/mcp/query/tag", {"tag": "core"}), ("/rag/ingest", {}),
                              ("/multi-agent/workflow", {"user_request": "do not run"})):
            check(path + " disabled", session.post(subjects_url + path, json=payload, timeout=30).status_code == 403)


if __name__ == "__main__":
    success = False
    try:
        main()
        success = True
    finally:
        (report / "cloud-verification.json").write_text(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
            "passed": success, "checks": results}, indent=2) + "\n")
