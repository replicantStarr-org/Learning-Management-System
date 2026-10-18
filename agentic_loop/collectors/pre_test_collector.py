from pathlib import Path

import yaml

from config.review_config import ServiceConfig


REQUIRED_HOOKS = {
    "ruff-security": "ruff",
    "detect-secrets": "detect-secrets",
    "pip-audit": "pip-audit",
}


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    config = repo_root / ".pre-commit-config.yaml"
    runner = repo_root / "scripts" / "pre_commit.py"
    policy = repo_root / "pyproject.toml"
    required = [config, runner, policy]
    missing = [str(path.relative_to(repo_root)) for path in required if not path.is_file()]
    if missing:
        return False, "Pre-test evidence incomplete. Missing: " + ", ".join(missing)
    try:
        config_text = config.read_text(encoding="utf-8")
        data = yaml.safe_load(config_text)
        hooks = {
            hook["id"]: hook
            for repository in data["repos"]
            for hook in repository.get("hooks", [])
        }
        for hook_id, tool in REQUIRED_HOOKS.items():
            hook = hooks.get(hook_id, {})
            if (
                f"scripts/pre_commit.py {tool}" not in hook.get("entry", "")
                or hook.get("pass_filenames") is not False
                or hook.get("always_run") is not True
            ):
                return False, f"Missing or incorrectly wired repository-wide hook: {hook_id}"
    except (yaml.YAMLError, KeyError, TypeError, AttributeError) as exc:
        return False, f"Invalid pre-commit configuration: {exc}"

    evidence = [
        "Repository-wide pre-commit implementation (not service-specific). "
        "Configuration checks do not prove hooks are installed or scans passed.",
    ]
    for path in required:
        evidence.append(f"{path.relative_to(repo_root)}:\n{path.read_text(encoding='utf-8')}")
    exemptions = repo_root / ".pip-audit-exemptions.json"
    if exemptions.is_file():
        evidence.append(f"Dependency exemption policy:\n{exemptions.read_text(encoding='utf-8')}")
    return True, "\n\n".join(evidence)
