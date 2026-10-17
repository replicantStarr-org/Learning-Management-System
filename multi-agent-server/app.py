import os

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env")

from flask import Flask, jsonify, request

from connectors import CONNECTORS
from coordinator import DECISIONS, WorkflowError, get_workflow, record_decision, run_workflow, workflow_status


def create_app():
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024

    @app.errorhandler(WorkflowError)
    def workflow_error(exc):
        return jsonify(status="error", error=str(exc)), exc.status

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise WorkflowError("Request body must be a JSON object")
        return data

    def service_name(value):
        if not isinstance(value, str) or value not in CONNECTORS:
            raise WorkflowError("service must be one of: " + ", ".join(CONNECTORS))
        return value

    def text(data, key, limit):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise WorkflowError(f"{key} must be a non-empty string of at most {limit} characters")
        return value.strip()

    @app.get("/")
    @app.get("/health")
    def health():
        return jsonify(service="multi-agent-server", status="running", services=list(CONNECTORS))

    @app.post("/workflow")
    def workflow():
        data = body()
        service = service_name(data.get("service"))
        user_request = text(data, "user_request", 4000)
        record_id = data.get("record_id")
        if record_id is not None and (type(record_id) is not int or record_id < 1):
            raise WorkflowError("record_id must be a positive integer")
        result = run_workflow(service, user_request, record_id)
        return jsonify(result), 200 if result["status"] == "success" else 502

    @app.get("/workflow/status")
    def status():
        return jsonify(workflow_status(service_name(request.args.get("service"))))

    @app.get("/workflow/<uuid:workflow_id>")
    def workflow_detail(workflow_id):
        return jsonify(get_workflow(service_name(request.args.get("service")), str(workflow_id)))

    @app.post("/workflow/<uuid:workflow_id>/decision")
    def decision(workflow_id):
        data = body()
        service = service_name(data.get("service"))
        value = text(data, "decision", 30)
        if value not in DECISIONS:
            raise WorkflowError("decision must be one of: " + ", ".join(DECISIONS))
        return jsonify(record_decision(
            service, str(workflow_id), value,
            text(data, "reviewer", 200), text(data, "reason", 4000), text(data, "evidence_used", 4000),
        ))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "15004")))
