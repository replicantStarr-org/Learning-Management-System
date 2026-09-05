import json
import re
from pathlib import Path

import yaml

from config.review_config import ServiceConfig


REQUIRED_JOB_PARTS = ("build", "smoke", "evidence")
REQUIRED_REPORT_KEY_PARTS = ("name", "id", "commit", "branch", "timestamp")
TEARDOWN = re.compile(r"docker(?:-|\s+)compose\s+down\b[^\n]*(?:-v\b|--volumes\b)", re.IGNORECASE)


def _all_keys(value) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [key for child in value.values() for key in _all_keys(child)]
    if isinstance(value, list):
        return [key for child in value for key in _all_keys(child)]
    return []


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    workflow_path = repo_root / ".github" / "workflows" / service.workflow
    reports_root = repo_root / "reports" / service.reports_directory
    if not workflow_path.is_file():
        return False, f"Missing mapped workflow: {workflow_path.relative_to(repo_root)}"
    if not reports_root.is_dir():
        return False, f"Missing mapped reports directory: {reports_root.relative_to(repo_root)}"

    run_directories = sorted(path for path in reports_root.iterdir() if path.is_dir())
    if not run_directories:
        return False, f"No downloaded artifact run exists under {reports_root.relative_to(repo_root)}."

    workflow_text = workflow_path.read_text(encoding="utf-8")
    try:
        workflow = yaml.safe_load(workflow_text) or {}
    except yaml.YAMLError as exc:
        return False, f"Invalid workflow YAML: {exc}"
    jobs = workflow.get("jobs", {})
    if not isinstance(jobs, dict):
        return False, "Workflow does not define a jobs mapping."
    missing_jobs = [
        part
        for part in REQUIRED_JOB_PARTS
        if not any(
            part in str(job_id).lower()
            or (isinstance(job, dict) and part in str(job.get("name", "")).lower())
            for job_id, job in jobs.items()
        )
    ]
    if missing_jobs:
        return False, "Workflow missing job IDs or names containing: " + ", ".join(missing_jobs)
    if not TEARDOWN.search(workflow_text):
        return False, "Workflow teardown must run docker compose down with -v or --volumes."

    summaries: list[str] = []
    errors: list[str] = []
    for run_directory in run_directories:
        json_files = list(run_directory.glob("*report.json"))
        markdown_files = list(run_directory.glob("*report.md"))
        if not json_files or not markdown_files:
            errors.append(f"{run_directory.name}: requires one *report.json and one *report.md")
            continue
        try:
            report = json.loads(json_files[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{json_files[0].name}: invalid JSON ({exc})")
            continue
        keys = [key.lower() for key in _all_keys(report)]
        missing_keys = [part for part in REQUIRED_REPORT_KEY_PARTS if not any(part in key for key in keys)]
        if missing_keys:
            errors.append(f"{json_files[0].name}: missing keys containing {', '.join(missing_keys)}")
        summaries.append(f"{run_directory.name}: {json_files[0].name}, {markdown_files[0].name}")

    if errors:
        return False, "; ".join(errors)
    return True, (
        f"Validated jobs: {', '.join(jobs)}. Validated artifact runs: {'; '.join(summaries)}. "
        "Teardown removes volumes.\n\nWorkflow YAML:\n" + workflow_text
    )
