import json
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from config.review_config import ServiceConfig


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    workflow = repo_root / ".github" / "workflows" / service.workflow
    reports = repo_root / "reports" / service.reports_directory
    test_directory = repo_root / "tests" / service.directory
    tests = sorted(test_directory.glob("*.py"))
    tests += sorted((repo_root / service.directory / "scripts").glob("*test*.sh"))
    if not workflow.is_file():
        return False, f"Missing mapped workflow: {workflow.relative_to(repo_root)}"
    if not tests:
        return False, f"No test implementation found for {service.key}."
    artifacts = sorted({
        path
        for pattern in ("test-results.md", "test-audit.jsonl", "*report.json", "*report.md", "*.xml")
        for path in reports.rglob(pattern)
        if path.is_file()
    })
    if not artifacts:
        return False, f"No downloaded test evidence under {reports.relative_to(repo_root)}. Run CI and download its artifacts first."

    evidence = [
        "Service-specific CI/CD evidence. Multiple artifact runs may be historical; "
        "compare commit/run metadata before making a release decision. "
        "Observation success means readable evidence, NOT passing tests. "
        "Do not infer token-auth coverage from endpoint tests alone.",
    ]
    try:
        for path in [workflow, *tests, *artifacts]:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                return False, f"Empty evidence file: {path.relative_to(repo_root)}"
            if path.suffix == ".json":
                json.loads(text)
            elif path.suffix == ".jsonl":
                entries = [json.loads(line) for line in text.splitlines() if line.strip()]
                if not entries:
                    return False, f"Empty audit: {path.relative_to(repo_root)}"
            elif path.suffix == ".xml":
                ElementTree.fromstring(text)
            evidence.append(f"{path.relative_to(repo_root)}:\n{text}")
    except (OSError, ValueError, ParseError, DefusedXmlException) as exc:
        return False, f"Unreadable or malformed CI/CD evidence: {exc}"
    return True, "\n\n".join(evidence)
