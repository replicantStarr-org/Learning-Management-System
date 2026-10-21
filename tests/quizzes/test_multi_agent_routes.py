"""Tests for the Quizzes multi-agent routes and the relay to the multi-agent server.

The routes run in a small Flask app with the HTTP layer faked, so no service has to run.
They check the switch (403 when off, off by default in the cloud), the error mapping
(503 when the server fails) and the request bodies sent to the server.
"""

import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("flask")
BACKEND = Path(__file__).resolve().parents[2] / "quizzes" / "backend"
WORKFLOW_ID = "2c464ac0-7422-4122-ab53-151b2ce10bd6"
DECISION = {"decision": "Partially Accept", "reviewer": "Mitch", "reason": "Fix the plan", "evidence_used": "quiz 1"}


@pytest.fixture
def modules(monkeypatch):
    """Import the backend's routes/services packages without leaking them into other tests."""
    for name in ("MULTI_AGENT_ENABLED", "CLOUD_DEPLOYMENT"):
        monkeypatch.delenv(name, raising=False)
    saved = {name: sys.modules.pop(name) for name in list(sys.modules)
             if name in ("routes", "services") or name.startswith(("routes.", "services."))}
    monkeypatch.syspath_prepend(str(BACKEND))
    routes = importlib.import_module("routes.multi_agent")
    service = importlib.import_module("services.multi_agent_service")
    yield routes, service
    for name in list(sys.modules):
        if name in ("routes", "services") or name.startswith(("routes.", "services.")):
            del sys.modules[name]
    sys.modules.update(saved)


@pytest.fixture
def client(modules):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(modules[0].multi_agent_bp)
    return app.test_client()


@pytest.fixture
def server(modules, monkeypatch):
    """Replace the HTTP call to the multi-agent server and record what was sent."""
    service = modules[1]
    sent = []

    def fake_request(method, path, payload=None, timeout=None):
        sent.append((method, path, payload))
        return 200, {"status": "success", "path": path}

    monkeypatch.setattr(service, "_request", fake_request)
    return sent


PROTECTED = [
    ("post", "/multi-agent/workflow", {"user_request": "Plan"}),
    ("get", "/multi-agent/workflow/status", None),
    ("get", f"/multi-agent/workflow/{WORKFLOW_ID}", None),
    ("post", f"/multi-agent/workflow/{WORKFLOW_ID}/decision", DECISION),
]


def call(client, method, path, body, **kwargs):
    return getattr(client, method)(path, **({"json": body} if body is not None else {}), **kwargs)


def test_status_is_on_locally_by_default(client):
    assert client.get("/multi-agent/status").get_json() == {"enabled": True}


def test_status_is_off_by_default_in_the_cloud(client, monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "true")
    assert client.get("/multi-agent/status").get_json() == {"enabled": False}


def test_cloud_flag_can_turn_it_on_for_the_bonus_profile(client, monkeypatch):
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "true")
    monkeypatch.setenv("MULTI_AGENT_ENABLED", "true")
    assert client.get("/multi-agent/status").get_json() == {"enabled": True}


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_every_route_returns_403_when_switched_off(client, server, monkeypatch, method, path, body):
    monkeypatch.setenv("MULTI_AGENT_ENABLED", "false")
    response = call(client, method, path, body)
    assert response.status_code == 403
    assert server == []


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_page_switch_header_turns_the_routes_off(client, server, method, path, body):
    assert call(client, method, path, body, headers={"X-Multi-Agent-Mode": "off"}).status_code == 403
    assert server == []


def test_workflow_for_the_catalogue_sends_no_record_id(client, server):
    assert client.post("/multi-agent/workflow", json={"user_request": "Plan"}).status_code == 200
    assert server == [("POST", "/workflow", {"service": "quizzes", "user_request": "Plan"})]


def test_workflow_for_one_quiz_sends_its_id(client, server):
    client.post("/multi-agent/workflow", json={"user_request": "Plan", "quiz_id": 7})
    assert server[0][2]["record_id"] == 7


def test_decision_sends_all_fields_and_the_service(client, server):
    client.post(f"/multi-agent/workflow/{WORKFLOW_ID}/decision", json={**DECISION, "extra": "ignored"})
    method, path, payload = server[0]
    assert (method, path) == ("POST", f"/workflow/{WORKFLOW_ID}/decision")
    assert payload == {**DECISION, "service": "quizzes"}


@pytest.mark.parametrize("path", ["/multi-agent/workflow", f"/multi-agent/workflow/{WORKFLOW_ID}/decision"])
def test_a_body_that_is_not_an_object_returns_400(client, server, path):
    assert client.post(path, json=["not", "an", "object"]).status_code == 400
    assert server == []


def test_a_malformed_workflow_id_is_not_found(client, server):
    assert client.get("/multi-agent/workflow/not-a-uuid").status_code == 404
    assert server == []


def test_server_down_returns_503(client, modules, monkeypatch):
    import requests
    monkeypatch.setattr(modules[1].requests, "request",
                        lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("refused")))
    response = client.post("/multi-agent/workflow", json={"user_request": "Plan"})
    assert response.status_code == 503
    assert "unavailable" in response.get_json()["error"]


def test_server_timeout_returns_503_with_advice(client, modules, monkeypatch):
    import requests
    monkeypatch.setattr(modules[1].requests, "request",
                        lambda *a, **k: (_ for _ in ()).throw(requests.Timeout()))
    response = client.get("/multi-agent/workflow/status")
    assert response.status_code == 503
    assert "timed out" in response.get_json()["error"]


def test_malformed_server_reply_returns_503(client, modules, monkeypatch):
    class Reply:
        status_code = 200

        def json(self):
            return ["not", "an", "object"]

    monkeypatch.setattr(modules[1].requests, "request", lambda *a, **k: Reply())
    assert client.get("/multi-agent/workflow/status").status_code == 503


def test_server_error_status_and_body_pass_through(client, modules, monkeypatch):
    monkeypatch.setattr(modules[1], "_request", lambda *a, **k: (409, {"error": "already decided"}))
    response = client.post(f"/multi-agent/workflow/{WORKFLOW_ID}/decision", json=DECISION)
    assert (response.status_code, response.get_json()) == (409, {"error": "already decided"})
