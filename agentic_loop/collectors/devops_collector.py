from pathlib import Path


REQUIRED_WORKFLOW_JOBS = ["build-images", "smoke-check", "evidence-pack"]
REQUIRED_REPORT_KEYS = ["workflow_name", "run_id", "commit_sha", "branch", "generated_timestamp"]


def collect(app_dir: Path, repo_root: Path) -> tuple[bool, str]:
    workflow_path = repo_root / ".github" / "workflows" / "lab5-ci.yml"
    reports_dir = app_dir / "reports"

    required_paths = [
        workflow_path,
        reports_dir / "report.json",
        reports_dir / "report.md",
        reports_dir / "run-view.md",
    ]

    missing: list[str] = []
    for path in required_paths:
        if not path.exists():
            if path.is_absolute() and repo_root in path.parents:
                missing.append(str(path.relative_to(repo_root)))
            elif path.is_absolute() and app_dir in path.parents:
                missing.append(str(path.relative_to(app_dir)))
            else:
                missing.append(str(path))

    if missing:
        return False, "DevOps evidence incomplete. Missing: " + ", ".join(missing)

    workflow_text = workflow_path.read_text(encoding="utf-8")
    report_json = (reports_dir / "report.json").read_text(encoding="utf-8")

    missing_jobs = [job for job in REQUIRED_WORKFLOW_JOBS if job not in workflow_text]
    if missing_jobs:
        return False, "Workflow missing required jobs: " + ", ".join(missing_jobs)

    missing_keys = [key for key in REQUIRED_REPORT_KEYS if key not in report_json]
    if missing_keys:
        return False, "report.json missing required keys: " + ", ".join(missing_keys)

    teardown_ok = "docker-compose down -v" in workflow_text
    teardown_text = "includes" if teardown_ok else "does not include"

    return True, (
        "DevOps evidence: workflow defines build-images, smoke-check, and evidence-pack; "
        f"teardown {teardown_text} docker-compose down -v; report.json contains run metadata keys."
    )
