import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("cloud_render", ROOT / "scripts/cloud/render.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


@pytest.fixture
def state(tmp_path, monkeypatch):
    inventory = json.loads((ROOT / "cloud/services.json").read_text())
    images = {f'{f["name"]}-{kind}': f'registry.azurecr.io/{f["name"]}-{kind}@sha256:abc'
              for f in inventory for kind in ("frontend", "backend", "database")}
    images.update({k: f'registry.azurecr.io/{k}@sha256:abc' for k in ("edge", "mcp", "rag-server", "multi-agent-server")})
    for filename, body in {
        "images.json": images, "release.json": {"release": "test", "profile": "default"},
        "environment.json": {"id": "/subscriptions/test/env", "domain": "test.azurecontainerapps.io"},
        "auth.json": {"username": "demo", "password": "unit-password", "htpasswd": "demo:$apr1$unit-salt$unit-hash", "jwt": "unit-jwt"},  # pragma: allowlist secret - dummy test credentials
        "models.json": {"key": "unit-provider-key", "endpoint": "https://example.openai.azure.com/openai/v1/"},
    }.items():
        (tmp_path / filename).write_text(json.dumps(body))
    (tmp_path / "runtime-identity").write_text("/subscriptions/test/identity")
    return tmp_path


def manifests(state, profile):
    renderer.render(state, profile)
    return {path.stem: yaml.safe_load(path.read_text()) for path in (state / "manifests").glob("*.yaml")}


def test_default_is_private_and_scales_to_zero(state):
    apps = manifests(state, "default")
    assert len(apps) == 6
    for app in apps.values():
        properties = app["properties"]
        assert properties["configuration"]["ingress"]["targetPort"] == 8080
        assert properties["configuration"]["ingress"]["allowInsecure"] is False
        assert properties["configuration"]["activeRevisionsMode"] == "Single"
        assert properties["template"]["scale"]["minReplicas"] == 1
        assert properties["template"]["scale"]["maxReplicas"] == 1
        assert [c["name"] for c in properties["template"]["containers"]] == ["edge", "frontend", "backend", "database"]
        assert all("@sha256:" in c["image"] for c in properties["template"]["containers"])
        assert "unit-provider-key" not in json.dumps(app)
    assert (state / "manifests/subjects.yaml").stat().st_mode & 0o777 == 0o600


def test_bonus_uses_nonconflicting_ports_and_secret_references(state):
    apps = manifests(state, "bonus")
    containers = apps["subjects"]["properties"]["template"]["containers"]
    assert len(containers) == 7
    ports = [c["probes"][0]["tcpSocket"]["port"] for c in containers]
    assert len(set(ports)) == len(ports)
    assert 15004 in ports
    assert sum(c["resources"]["cpu"] for c in containers) == 2
    assert sum(float(c["resources"]["memory"].removesuffix("Gi")) for c in containers) == 4
    for c in containers:
        for env in c["env"]:
            if env["name"] == "OPENAI_API_KEY":
                assert env == {"name": "OPENAI_API_KEY", "secretRef": "inference-key"}  # pragma: allowlist secret - secret reference name

    # all deployments have seven containers
    # edge, frontend, backend, database
    # then 3 for the bonus profile
    # MCP, RAG and multi-agent server
    for name in set(apps):
        assert len(apps[name]["properties"]["template"]["containers"]) == 7


def test_resources_shares_only_temporary_content(state):
    app = manifests(state, "default")["resources"]
    assert app["properties"]["template"]["volumes"] == [{"name": "content", "storageType": "EmptyDir"}]
    mounts = [c["name"] for c in app["properties"]["template"]["containers"] if c.get("volumeMounts")]
    assert mounts == ["frontend", "backend"]


def test_unknown_profile_rejected(state):
    with pytest.raises(ValueError):
        renderer.render(state, "invalid")


@pytest.fixture
def querying(monkeypatch):
    # Protocol tests do not need a live vector index or heavy Chroma dependencies.
    monkeypatch.syspath_prepend(str(ROOT / "rag-server"))
    monkeypatch.setitem(sys.modules, "chromadb", Mock())
    from pipeline import querying
    monkeypatch.setattr(querying, "settings", lambda: {"openai": {"base_url": "http://localhost:11434/v1", "model": "local", "timeout_seconds": 120}})
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.example/openai/v1/")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-key")
    monkeypatch.setenv("OPENAI_MODEL", "primary")
    return querying


def test_rag_uses_openai_protocol(querying, monkeypatch):
    response = Mock()
    response.json.return_value = {"choices": [{"message": {"content": "Grounded answer"}}]}
    post = Mock(return_value=response)
    monkeypatch.setattr(querying.requests, "post", post)
    assert querying.generate_with_openai("question", "evidence") == "Grounded answer"
    args, kwargs = post.call_args
    assert args[0] == "https://provider.example/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer unit-key"
    assert kwargs["json"]["model"] == "primary"
    assert kwargs["json"]["temperature"] == 0
    assert "options" not in kwargs["json"]
    assert kwargs["json"]["messages"][0]["role"] == "system"


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {"content": None}}]}])
def test_rag_rejects_malformed_inference(querying, monkeypatch, body):
    response = Mock()
    response.json.return_value = body
    monkeypatch.setattr(querying.requests, "post", Mock(return_value=response))
    with pytest.raises(requests.RequestException):
        querying.generate_with_openai("question", "evidence")


def test_workflow_reuses_actual_ci():
    workflow = yaml.safe_load((ROOT / ".github/workflows/cloud-deployment.yml").read_text())
    jobs = workflow["jobs"]
    for job in ("access-ci", "subjects-ci", "resources-ci", "assignments-ci", "quizzes-ci", "timetable-ci", "rag-ci"):
        assert job in jobs["deploy"]["needs"]
        path = ROOT / jobs[job]["uses"].removeprefix("./")
        called = yaml.safe_load(path.read_text())
        # PyYAML's YAML 1.1 parser treats the unquoted GitHub key `on` as True.
        assert "workflow_call" in called.get("on", called.get(True))
    assert jobs["deploy"]["environment"] == "cloud"
    assert jobs["deploy"]["permissions"]["id-token"] == "write"
