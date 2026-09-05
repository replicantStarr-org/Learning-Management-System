import os
import re
from pathlib import Path

import requests

from config.review_config import ServiceConfig, service_path


SHORTCUT_ROUTE = re.compile(r"@\w+\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
GENERIC_ROUTE = re.compile(
    r"@\w+\.route\(\s*['\"]([^'\"]*)['\"](?P<args>.*?)\)", re.IGNORECASE | re.DOTALL
)
METHODS = re.compile(r"methods\s*=\s*\[([^]]+)\]", re.IGNORECASE)
QUOTED = re.compile(r"['\"]([A-Za-z]+)['\"]")
BLUEPRINT = re.compile(
    r"register_blueprint\(\s*(\w+)\s*,\s*url_prefix\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE
)
BLUEPRINT_NAME = re.compile(r"(\w+)\s*=\s*Blueprint\(")
PARAMETER = re.compile(r"<(?:(?:int|string|float|path|uuid):)?[^>]+>")


def _runnable_path(path: str) -> str:
    return PARAMETER.sub("1", path) or "/"


def _routes(backend: Path) -> list[tuple[str, str]]:
    prefixes: dict[str, str] = {}
    for source in backend.rglob("*.py"):
        for blueprint, prefix in BLUEPRINT.findall(source.read_text(encoding="utf-8")):
            prefixes[blueprint] = prefix.rstrip("/")

    found: list[tuple[str, str]] = []
    for source in backend.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        owner_match = BLUEPRINT_NAME.search(text)
        prefix = prefixes.get(owner_match.group(1), "") if owner_match else ""
        found.extend((method.upper(), prefix + path) for method, path in SHORTCUT_ROUTE.findall(text))
        for match in GENERIC_ROUTE.finditer(text):
            method_match = METHODS.search(match.group("args"))
            methods = QUOTED.findall(method_match.group(1)) if method_match else ["GET"]
            found.extend((method.upper(), prefix + match.group(1)) for method in methods)
    return sorted(set(found))


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    backend = service_path(repo_root, service) / "backend"
    if not backend.is_dir():
        return False, f"Missing backend directory: {backend.relative_to(repo_root)}"

    routes = _routes(backend)
    if not routes:
        return False, "No Flask endpoints were found under the backend directory."

    variable = f"{service.key.upper()}_BASE_URL"
    # Feature backends use the same port offset as the rest of the
    # application.  Probing every service on port 5000 reaches only the
    # access backend and produces misleading 404s for otherwise valid routes.
    backend_ports = {
        "access": 5000,
        "subjects": 5001,
        "assignments": 5003,
        "resources": 7050,
        "quizzes": 5004,
        "timetable": 5005,
    }
    default_url = f"http://localhost:{backend_ports.get(service.key, 5000)}"
    base_url = os.getenv(variable, os.getenv("SERVICE_BASE_URL", default_url)).rstrip("/")
    evidence: list[str] = []
    failures: list[str] = []
    session = requests.Session()
    for method, declared_path in routes:
        path = _runnable_path(declared_path)
        try:
            response = session.request(method, base_url + path, timeout=2)
            elapsed = int(response.elapsed.total_seconds() * 1000)
            evidence.append(f"{method} {declared_path} -> HTTP {response.status_code} ({elapsed}ms)")
        except requests.RequestException as exc:
            result = f"{method} {declared_path} -> connection failure ({type(exc).__name__})"
            evidence.append(result)
            failures.append(result)

    result = f"Base URL: {base_url}\n" + "\n".join(evidence)
    if failures:
        return False, f"{len(failures)} endpoint(s) did not respond.\n{result}"
    return True, result
