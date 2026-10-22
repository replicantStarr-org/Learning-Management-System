"""Relay this service's workflow requests to the shared Multi-Agent Server."""

import os

import requests

SERVICE = "assignments"
MULTI_AGENT_SERVICE_URL = os.getenv("MULTI_AGENT_SERVICE_URL", "http://localhost:15004").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("MULTI_AGENT_REQUEST_TIMEOUT_SECONDS", "10"))
WORKFLOW_TIMEOUT = float(os.getenv("MULTI_AGENT_WORKFLOW_TIMEOUT_SECONDS", "180"))


class MultiAgentError(RuntimeError):
    pass


def _request(method, path, payload=None, timeout=REQUEST_TIMEOUT):
    try:
        response = requests.request(
            method,
            MULTI_AGENT_SERVICE_URL + path,
            json=payload,
            params={"service": SERVICE} if method == "GET" else None,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise MultiAgentError("The multi-agent server timed out. Check workflow status before retrying.") from exc
    except requests.RequestException as exc:
        raise MultiAgentError("The multi-agent server is unavailable.") from exc
    try:
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Expected object")
    except ValueError as exc:
        raise MultiAgentError("The multi-agent server returned a malformed response.") from exc
    return response.status_code, body


def run_workflow(payload):
    request_body = {"service": SERVICE, "user_request": payload.get("user_request")}
    if payload.get("record_id") is not None:
        request_body["record_id"] = payload["record_id"]
    return _request("POST", "/workflow", request_body, timeout=WORKFLOW_TIMEOUT)


def workflow_status():
    return _request("GET", "/workflow/status")


def get_workflow(workflow_id):
    return _request("GET", f"/workflow/{workflow_id}")


def record_decision(workflow_id, payload):
    decision = {key: payload.get(key) for key in ("decision", "reviewer", "reason", "evidence_used")}
    return _request("POST", f"/workflow/{workflow_id}/decision", {**decision, "service": SERVICE})