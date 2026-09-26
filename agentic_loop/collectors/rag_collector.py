import ast
from pathlib import Path

from config.review_config import ServiceConfig


RAG_SERVER_DIR = "rag-server"

REQUIRED_PYTHON_FILES = [
    "eval.py",
    "pipeline/__init__.py",
    "pipeline/common.py",
    "pipeline/connector.py",
    "pipeline/vectors.py",
    "pipeline/audit.py",
    "pipeline/ingestion.py",
    "pipeline/querying.py",
    "pipeline/connectors/__init__.py",
    "pipeline/connectors/assignments.py",
    "pipeline/connectors/learning_resources.py",
    "pipeline/connectors/quizzes.py",
    "pipeline/connectors/subjects.py",
    "pipeline/connectors/timetable.py",
    "server/__init__.py",
    "server/http_server.py",
    "server/endpoints.py",
    "server/mcp_server.py",
]

REQUIRED_RAG_ROUTES = [
    ("GET", "/health"),
    ("GET", "/services"),
    ("POST", "/ingest"),
    ("POST", "/retrieve"),
    ("POST", "/answer"),
]


def _routes(http_server: Path) -> dict[tuple[str, str], str]:
    """The ROUTES table in http_server.py: (method, path) -> endpoints function name.

    Read from the syntax tree rather than with a regex, so formatting changes
    do not break the check.
    """
    tree = ast.parse(http_server.read_text(encoding="utf-8"), filename=f"{RAG_SERVER_DIR}/server/{http_server.name}")
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "ROUTES" for target in node.targets):
            continue

        routes: dict[tuple[str, str], str] = {}
        for key, value in zip(node.value.keys, node.value.values):
            if not (isinstance(key, ast.Tuple) and len(key.elts) == 2):
                continue
            method, path = (element.value if isinstance(element, ast.Constant) else None for element in key.elts)
            handler = value.attr if isinstance(value, ast.Attribute) else getattr(value, "id", "?")
            routes[(method, path)] = handler
        return routes
    return {}


def _functions(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=f"{RAG_SERVER_DIR}/server/{source.name}")
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def collect(repo_root: Path, service: ServiceConfig | None) -> tuple[bool, str]:
    rag_server_dir = repo_root / RAG_SERVER_DIR
    if not rag_server_dir.is_dir():
        return False, f"RAG server directory is missing: {RAG_SERVER_DIR}/"

    missing_files = [path for path in REQUIRED_PYTHON_FILES if not (rag_server_dir / path).is_file()]
    if missing_files:
        return False, "RAG server is missing Python files: " + ", ".join(
            f"{RAG_SERVER_DIR}/{path}" for path in missing_files
        )

    try:
        routes = _routes(rag_server_dir / "server/http_server.py")
        endpoint_functions = _functions(rag_server_dir / "server/endpoints.py")
    except SyntaxError as exc:
        return False, f"RAG server source does not parse: {exc.filename}:{exc.lineno}: {exc.msg}"

    if not routes:
        return False, f"No ROUTES table found in {RAG_SERVER_DIR}/server/http_server.py"

    missing_routes = [f"{method} {path}" for method, path in REQUIRED_RAG_ROUTES if (method, path) not in routes]
    if missing_routes:
        return False, "http_server.py ROUTES is missing: " + ", ".join(missing_routes)

    # A route whose handler was renamed or removed would only fail at request time.
    unbound = [
        f"{method} {path} -> endpoints.{routes[(method, path)]}"
        for method, path in REQUIRED_RAG_ROUTES
        if routes[(method, path)] not in endpoint_functions
    ]
    if unbound:
        return False, "Routes point at functions not defined in endpoints.py: " + ", ".join(unbound)

    route_lines = "\n".join(
        f"- {method} {path} -> endpoints.{routes[(method, path)]}" for method, path in REQUIRED_RAG_ROUTES
    )
    return True, (
        f"RAG server: {RAG_SERVER_DIR}/\n"
        f"All {len(REQUIRED_PYTHON_FILES)} required Python files present.\n"
        f"All {len(REQUIRED_RAG_ROUTES)} required routes are in ROUTES and bound to endpoints.py functions:\n"
        f"{route_lines}"
    )
