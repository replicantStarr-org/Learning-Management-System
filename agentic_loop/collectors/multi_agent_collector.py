import ast
import json
import os
from pathlib import Path

from config.review_config import ServiceConfig

REQUIRED_FUNCTIONS = {
    "agents/planner_agent.py": "plan_workflow",
    "agents/worker_agent.py": "generate_output",
    "agents/reviewer_agent.py": "review_output",
    "coordinator.py": "run_workflow",
}


def _tree(path: Path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _calls(tree):
    return {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    server = repo_root / "multi-agent-server"
    registry = server / "connectors/__init__.py"
    if not registry.is_file():
        return False, "Missing multi-agent-server/connectors/__init__.py"
    try:
        tree = _tree(registry)
        registered = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CONNECTORS" for t in node.targets):
                if isinstance(node.value, ast.Dict):
                    registered = {key.value for key in node.value.keys if isinstance(key, ast.Constant)}
        if service.key not in registered:
            return False, f"{service.label} is not integrated into multi-agent coordination yet; no adapter is registered."
        backend = repo_root / service.directory / "backend"
        frontend = repo_root / service.directory / "frontend"
        required = [
            *(server / name for name in REQUIRED_FUNCTIONS),
            server / "agents/model_client.py", server / "app.py", server / "storage.py", server / "requirements.txt",
            server / "connectors" / f"{service.key}.py",
            *(server / "prompts" / f"{role}_prompt.txt" for role in ("planner", "worker", "reviewer")),
            backend / "app.py", backend / "routes/multi_agent.py", backend / "services/multi_agent_service.py",
            frontend / "multi-agent.html", frontend / "multi-agent.js", frontend / "nginx.conf", frontend / "index.html",
            repo_root / service.directory / "docker-compose.yml",
            repo_root / "prompts/areas/multi_agent_prompt.txt",
        ]
        missing = [str(path.relative_to(repo_root)) for path in required if not path.is_file()]
        if missing:
            return False, "Multi-agent evidence incomplete. Missing: " + ", ".join(missing)
        for name, function in REQUIRED_FUNCTIONS.items():
            if not any(isinstance(n, ast.FunctionDef) and n.name == function for n in _tree(server / name).body):
                return False, f"{name} is missing function {function}"
        coordinator = _tree(server / "coordinator.py")
        missing_calls = set(REQUIRED_FUNCTIONS.values()) - {"run_workflow"} - _calls(coordinator)
        if missing_calls:
            return False, "Coordinator missing calls to: " + ", ".join(sorted(missing_calls))
        if not any(
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "register_blueprint"
            and any(isinstance(arg, ast.Name) and arg.id == "multi_agent_bp" for arg in node.args)
            for node in ast.walk(_tree(backend / "app.py"))
        ):
            return False, "Backend does not register multi_agent_bp"
        sources = [
            registry, server / "coordinator.py", server / "app.py", server / "storage.py",
            server / "agents/model_client.py",
            *(server / name for name in REQUIRED_FUNCTIONS if name.startswith("agents/")),
            server / "connectors" / f"{service.key}.py",
            *(server / "prompts" / f"{role}_prompt.txt" for role in ("planner", "worker", "reviewer")),
            backend / "routes/multi_agent.py", backend / "services/multi_agent_service.py",
        ]
        evidence = [
            f"Selected service: {service.key}. Registered adapters: {', '.join(sorted(registered))}.",
            "Static checks: required files/functions present; coordinator calls all three agents; backend registers blueprint.",
            "These checks establish wiring only, not successful model execution, citation accuracy or reviewer identity.",
        ]
        if all(os.path.exists(source) for source in sources):
            evidence.append("All required source files are present.")
        evidence.append("UI/proxy integration files present. UI content and browser behaviour require separate validation.")
    except (SyntaxError, OSError) as exc:
        return False, f"Cannot inspect multi-agent source: {exc}"

    data_dir = Path(os.getenv("MULTI_AGENT_DATA_DIR", str(server)))
    history = data_dir / "workflow_history.jsonl"
    try:
        records = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()] if history.exists() else []
        selected = [row for row in records if row.get("service") == service.key]
        if selected:
            latest = selected[-1]
            summary = {key: latest.get(key) for key in ("workflow_id", "timestamp", "status", "duration_ms")}
            summary["agent_statuses"] = {role: latest.get(f"{role}_result", {}).get("status") for role in ("planner", "worker", "reviewer")}
            summary["evidence_count"] = latest.get("evidence_result", {}).get("evidence_count", 0)
            summary["human_decision"] = latest.get("human_decision", {}).get("status")
            evidence.append("Latest persisted workflow snapshot (not independently re-executed): " + json.dumps(summary))
        else:
            evidence.append("No persisted workflow for this service. Live execution and human decision are unverified.")
        audit = data_dir / "coordination_audit.jsonl"
        audit_records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line.strip()] if audit.exists() else []
        evidence.append(f"Persisted audit events for this service: {sum(row.get('service') == service.key for row in audit_records)}.")
    except (ValueError, OSError, AttributeError, TypeError) as exc:
        evidence.append(f"Runtime evidence unreadable ({type(exc).__name__}); live execution is unverified.")
    return True, "\n\n".join(evidence)
