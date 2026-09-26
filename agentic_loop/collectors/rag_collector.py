"""Evidence for reviewing the RAG connector of one service.

The RAG server indexes each service through a connector module in
rag-server/pipeline/connectors/, written to the rules in the AGENTS.md there.
This collects three kinds of evidence for the selected service's connector:

1. The RAG server's own structure (required files and routes), as a precondition.
2. A static analysis of the connector module against those rules.
3. When the service is running, the chunks the connector actually produces,
   generated twice with the RAG server's own environment to check determinism.
"""

import ast
import json
import os
import re
import subprocess
from pathlib import Path

from config.review_config import ServiceConfig


RAG_SERVER_DIR = "rag-server"
CONNECTORS_DIR = "pipeline/connectors"
PREVIEW_TIMEOUT_SECONDS = 90
SAMPLE_CHARACTERS = 500

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

# ServiceConfig.key -> connector module in rag-server/pipeline/connectors/.
CONNECTOR_MODULES = {
    "subjects": "subjects",
    "assignments": "assignments",
    "resources": "learning_resources",
    "quizzes": "quizzes",
    "timetable": "timetable",
}
NO_CONNECTOR_REASONS = {
    "access": "it only stores accounts and password hashes, which must never be indexed",
}

FORBIDDEN_IMPORTS = {"requests", "httpx", "urllib", "aiohttp", "sqlite3", "http"}
NONDETERMINISTIC_CALLS = {
    ("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"), ("date", "today"),
    ("time", "time"), ("random", "random"), ("random", "randint"), ("random", "choice"),
    ("random", "shuffle"), ("uuid", "uuid4"),
}
SECRET_KEY = re.compile(r"password|passwd|hash|token|secret|api_?key|session", re.IGNORECASE)
AI_KEY = re.compile(r"summar|advice|ai_|generated|llm|plan_text", re.IGNORECASE)
ID_KEY = re.compile(r"(^|_)id$", re.IGNORECASE)
RAW_FLAG_LINE = re.compile(r":\s*(0|1|True|False)\s*$")

# Runs inside rag-server/ with its own venv, like the preview in AGENTS.md.
PREVIEW_SCRIPT = """
import json, sys
import requests
from pipeline.common import settings
from pipeline.connector import connectors
from pipeline.ingestion import record_chunks

name = sys.argv[1]
connector = connectors()[name]

def run():
    chunks = []
    for record in connector.records():
        for chunk in record_chunks(name, record, ""):
            chunks.append({"id": chunk["id"], "entity": record.entity, "title": record.title, "text": chunk["text"]})
    return chunks

try:
    first = run()
    second = run()
except requests.RequestException as exc:
    print(json.dumps({"unreachable": str(exc)}))
except Exception as exc:
    print(json.dumps({"error": repr(exc)}))
else:
    print(json.dumps({
        "chunks": first,
        "stable": first == second,
        "max_words": settings()["chunking"]["max_words"],
    }))
"""


# ------------------------------------------------------------ RAG server structure


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


def _check_structure(rag_server_dir: Path) -> str | None:
    """None if the RAG server has its files and routes, otherwise the problem."""
    missing_files = [path for path in REQUIRED_PYTHON_FILES if not (rag_server_dir / path).is_file()]
    if missing_files:
        return "RAG server is missing Python files: " + ", ".join(
            f"{RAG_SERVER_DIR}/{path}" for path in missing_files
        )

    try:
        routes = _routes(rag_server_dir / "server/http_server.py")
        endpoint_functions = _functions(rag_server_dir / "server/endpoints.py")
    except SyntaxError as exc:
        return f"RAG server source does not parse: {exc.filename}:{exc.lineno}: {exc.msg}"

    if not routes:
        return f"No ROUTES table found in {RAG_SERVER_DIR}/server/http_server.py"

    missing_routes = [f"{method} {path}" for method, path in REQUIRED_RAG_ROUTES if (method, path) not in routes]
    if missing_routes:
        return "http_server.py ROUTES is missing: " + ", ".join(missing_routes)

    # A route whose handler was renamed or removed would only fail at request time.
    unbound = [
        f"{method} {path} -> endpoints.{routes[(method, path)]}"
        for method, path in REQUIRED_RAG_ROUTES
        if routes[(method, path)] not in endpoint_functions
    ]
    if unbound:
        return "Routes point at functions not defined in endpoints.py: " + ", ".join(unbound)
    return None


# ------------------------------------------------------------- static analysis


def _call_name(node: ast.Call) -> str | None:
    return node.func.id if isinstance(node.func, ast.Name) else None


def _constant_strings(nodes) -> list[str]:
    return [node.value for node in nodes if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def _field_keys(record_call: ast.Call) -> list[str]:
    """Keys the Record's fields are built from: pick() arguments and dict literal keys."""
    fields = next((kw.value for kw in record_call.keywords if kw.arg == "fields"), None)
    if fields is None and len(record_call.args) >= 4:
        fields = record_call.args[3]
    if fields is None:
        return []

    keys: list[str] = []
    for node in ast.walk(fields):
        if isinstance(node, ast.Call) and _call_name(node) == "pick":
            keys.extend(_constant_strings(node.args[1:]))
        elif isinstance(node, ast.Dict):
            keys.extend(_constant_strings(key for key in node.keys if key is not None))
    return list(dict.fromkeys(keys))


def _entity_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    def is_entity(decorator: ast.expr) -> bool:
        return isinstance(decorator, ast.Attribute) and decorator.attr == "entity"

    return [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and any(is_entity(d) for d in node.decorator_list)
    ]


def _describe_entity_function(function: ast.FunctionDef) -> tuple[str, list[str]]:
    """One evidence line for an entity function, and the field keys it indexes."""
    get_name = function.args.args[0].arg if function.args.args else "get"
    paths, entities, keys = [], [], []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == get_name and node.args:
            params = [kw.arg for kw in node.keywords if kw.arg]
            paths.append(ast.unparse(node.args[0]) + (f" with {', '.join(params)}" if params else ""))
        elif name == "Record":
            entity = next((kw.value for kw in node.keywords if kw.arg == "entity"), node.args[0] if node.args else None)
            entities.append(entity.value if isinstance(entity, ast.Constant) else ast.unparse(entity) if entity else "?")
            keys.extend(_field_keys(node))

    keys = list(dict.fromkeys(keys))
    line = (
        f"- {function.name}(): fetches {', '.join(paths) or 'nothing through get()'}; "
        f"yields entity {', '.join(dict.fromkeys(entities)) or '(none)'}; "
        f"fields: {', '.join(keys) or '(not statically visible)'}"
    )
    return line, keys


def _rule_checks(tree: ast.Module, field_keys: list[str]) -> list[str]:
    """PASS/FAIL/WARN lines for the AGENTS.md rules that can be checked statically."""
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module.split(".")[0])
    bypass = sorted(imports & FORBIDDEN_IMPORTS)

    try_lines = [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Try)]
    nondeterministic = sorted({
        f"{node.func.value.id}.{node.func.attr}()"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and (node.func.value.id, node.func.attr) in NONDETERMINISTIC_CALLS
    })
    secrets = [key for key in field_keys if SECRET_KEY.search(key)]
    ai_content = [key for key in field_keys if AI_KEY.search(key)]
    ids = [key for key in field_keys if ID_KEY.search(key)]

    def line(failed: bool, level: str, passed: str, message: str) -> str:
        return f"- {level} {message}" if failed else f"- PASS {passed}"

    return [
        line(bool(bypass), "FAIL", "fetches only through get()", f"imports {', '.join(bypass)}: fetch only through get()"),
        line(bool(try_lines), "FAIL", "no try/except (errors raise)", f"try/except at line(s) {', '.join(map(str, try_lines))}: errors must raise"),
        line(bool(nondeterministic), "FAIL", "no time- or random-dependent calls", f"nondeterministic calls: {', '.join(nondeterministic)}"),
        line(bool(secrets), "FAIL", "no secret-looking fields", f"secret-looking fields indexed: {', '.join(secrets)}"),
        line(bool(ai_content), "WARN", "no AI-generated-looking fields", f"possibly AI-generated fields indexed: {', '.join(ai_content)}"),
        line(bool(ids), "WARN", "no internal ID fields", f"internal ID fields indexed: {', '.join(ids)}"),
    ]


# ---------------------------------------------------------------- live preview


def _venv_python(rag_server_dir: Path) -> Path:
    if os.name == "nt":
        return rag_server_dir / ".venv_rag" / "Scripts" / "python.exe"
    return rag_server_dir / ".venv_rag" / "bin" / "python"


def _live_preview(rag_server_dir: Path, connector_name: str) -> list[str]:
    python = _venv_python(rag_server_dir)
    if not python.exists():
        return [f"- unavailable: {RAG_SERVER_DIR} is not initialised (run {RAG_SERVER_DIR}/init.sh); chunk quality is unverified"]

    try:
        completed = subprocess.run(
            [str(python), "-c", PREVIEW_SCRIPT, connector_name],
            cwd=rag_server_dir, capture_output=True, text=True, timeout=PREVIEW_TIMEOUT_SECONDS,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return [f"- FAIL connector did not finish within {PREVIEW_TIMEOUT_SECONDS}s"]
    except (json.JSONDecodeError, IndexError):
        detail = (completed.stderr.strip().splitlines() or ["no output"])[-1]
        return [f"- unavailable: preview could not run ({detail}); chunk quality is unverified"]

    if "unreachable" in result:
        return [f"- unavailable: the service is not reachable ({result['unreachable'][:160]}); start it to include chunk quality"]
    if "error" in result:
        return [f"- FAIL the connector raised {result['error'][:200]}"]

    chunks, limit = result["chunks"], result["max_words"]
    if not chunks:
        return ["- WARN the connector ran but produced no records"]

    per_entity: dict[str, int] = {}
    samples: dict[str, str] = {}
    for chunk in chunks:
        per_entity[chunk["entity"]] = per_entity.get(chunk["entity"], 0) + 1
        samples.setdefault(chunk["entity"], chunk["text"])
    words = [len(chunk["text"].split()) for chunk in chunks]
    over_limit = sum(count > limit for count in words)
    duplicate_ids = len(chunks) - len({chunk["id"] for chunk in chunks})
    raw_flags = sum(bool(RAW_FLAG_LINE.search(line)) for chunk in chunks for line in chunk["text"].splitlines())
    empty_titles = sum(not chunk["title"].strip() for chunk in chunks)

    lines = [
        f"- {len(chunks)} chunks ({', '.join(f'{entity}: {count}' for entity, count in per_entity.items())})",
        f"- chunk size: longest {max(words)} words, average {sum(words) // len(words)}, limit {limit}, {over_limit} over the limit",
        f"- {'PASS' if not duplicate_ids else 'FAIL'} chunk ids unique" + (f" ({duplicate_ids} duplicates)" if duplicate_ids else ""),
        f"- {'PASS' if result['stable'] else 'FAIL'} identical ids and text across two runs",
        f"- {'PASS' if not raw_flags else 'WARN'} raw 0/1 or True/False values: {raw_flags} line(s)",
        f"- {'PASS' if not empty_titles else 'FAIL'} empty titles: {empty_titles}",
    ]
    for entity, text in samples.items():
        sample = text if len(text) <= SAMPLE_CHARACTERS else text[:SAMPLE_CHARACTERS] + " ..."
        lines.append(f"Sample chunk ({entity}):\n  " + sample.replace("\n", "\n  "))
    return lines


# -------------------------------------------------------------------- collect


def collect(repo_root: Path, service: ServiceConfig | None) -> tuple[bool, str]:
    rag_server_dir = repo_root / RAG_SERVER_DIR
    if not rag_server_dir.is_dir():
        return False, f"RAG server directory is missing: {RAG_SERVER_DIR}/"
    if service is None:
        return False, "A service is required: the RAG review checks that service's connector."
    if service.key in NO_CONNECTOR_REASONS:
        return False, f"{service.label} has no RAG connector by design: {NO_CONNECTOR_REASONS[service.key]}."
    if service.key not in CONNECTOR_MODULES:
        return False, f"No RAG connector module is mapped for service '{service.key}'."

    problem = _check_structure(rag_server_dir)
    if problem:
        return False, problem

    relative = f"{RAG_SERVER_DIR}/{CONNECTORS_DIR}/{CONNECTOR_MODULES[service.key]}.py"
    source = repo_root / relative
    if not source.is_file():
        return False, f"Connector module is missing: {relative}"
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=relative)
    except SyntaxError as exc:
        return False, f"Connector does not parse: {exc.filename}:{exc.lineno}: {exc.msg}"

    connector_call = next(
        (node for node in ast.walk(tree) if isinstance(node, ast.Call) and _call_name(node) == "Connector"),
        None,
    )
    if connector_call is None:
        return False, f"{relative} does not create a Connector(...)."
    connector_name, base_url = (_constant_strings(connector_call.args) + ["?", "?"])[:2]

    functions = _entity_functions(tree)
    if not functions:
        return False, (
            f"The {service.label} connector ({relative}) is a stub with no entity functions, "
            f"so ingestion skips it and there is nothing to review yet."
        )

    entity_lines, field_keys = [], []
    for function in functions:
        line, keys = _describe_entity_function(function)
        entity_lines.append(line)
        field_keys.extend(keys)

    evidence = [
        f"RAG server: {RAG_SERVER_DIR}/ has all {len(REQUIRED_PYTHON_FILES)} required files and "
        f"{len(REQUIRED_RAG_ROUTES)} routes bound to endpoint functions.",
        f"Connector for {service.label}: {relative}",
        f"Service name \"{connector_name}\", base URL {base_url}, {len(functions)} entity function(s):",
        *entity_lines,
        "Static rule checks (AGENTS.md):",
        *_rule_checks(tree, list(dict.fromkeys(field_keys))),
        "Live preview (connector run twice against the running service):",
        *_live_preview(rag_server_dir, connector_name),
    ]
    return True, "\n".join(evidence)
