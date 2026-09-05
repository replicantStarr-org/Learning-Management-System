from pathlib import Path

import yaml

from config.review_config import ServiceConfig, service_path


SERVICE_KINDS = ("frontend", "backend", "database")


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    root = service_path(repo_root, service)
    missing_directories = [name for name in SERVICE_KINDS if not (root / name).is_dir()]
    if missing_directories:
        return False, "Missing required service directories: " + ", ".join(missing_directories)

    required = [root / "frontend" / "app.py", root / "backend" / "app.py"]
    index_candidates = [root / "frontend" / "index.html", root / "frontend" / "templates" / "index.html", root / "frontend" / "src" / "index.html"]
    missing = [str(path.relative_to(repo_root)) for path in required if not path.is_file()]
    if not any(path.is_file() for path in index_candidates):
        missing.append(f"{service.directory}/frontend/**/index.html")
    if missing:
        return False, "Architecture files missing: " + ", ".join(missing)

    compose_files = sorted(root.glob("*compose.yml")) + sorted(root.glob("*compose.yaml"))
    if not compose_files:
        return False, f"No *compose.yml or *compose.yaml file found in {service.directory}."

    compose_path = compose_files[0]
    compose_text = compose_path.read_text(encoding="utf-8")
    try:
        document = yaml.safe_load(compose_text) or {}
    except yaml.YAMLError as exc:
        return False, f"Invalid Compose YAML: {exc}"
    services = document.get("services")
    if not isinstance(services, dict):
        return False, "Compose file does not contain a services mapping."
    if len(services) != 3:
        return False, f"Compose file must define exactly 3 services; found {len(services)}."

    assignments: dict[str, str] = {}
    for name in services:
        matches = [kind for kind in SERVICE_KINDS if kind in name.lower()]
        if len(matches) != 1:
            return False, f"Compose service '{name}' must contain exactly one of: {', '.join(SERVICE_KINDS)}."
        if matches[0] in assignments:
            return False, f"Multiple Compose services represent '{matches[0]}'."
        assignments[matches[0]] = name
    if set(assignments) != set(SERVICE_KINDS):
        return False, "Compose services do not uniquely represent frontend, backend, and database."

    return True, (
        f"Required folders, app.py files, and frontend index.html are present. "
        f"Compose services: {', '.join(services)}.\n\nCompose file ({compose_path.name}):\n{compose_text}"
    )
