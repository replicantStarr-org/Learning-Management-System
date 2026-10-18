import json
from pathlib import Path

from config.review_config import ServiceConfig


SOURCE_PATHS = (
    ".github/workflows/cloud-deployment.yml",
    "cloud/services.json",
    "scripts/cloud/provision.sh",
    "scripts/cloud/build-images.sh",
    "scripts/cloud/deploy.sh",
    "scripts/cloud/render.py",
    "scripts/cloud/verify.py",
    "cloud/edge/default.conf.template",
    "cloud/edge/15-auth.sh",
)


def collect(repo_root: Path, service: ServiceConfig) -> tuple[bool, str]:
    sources = [repo_root / name for name in SOURCE_PATHS]
    missing = [str(path.relative_to(repo_root)) for path in sources if not path.is_file()]
    if missing:
        return False, "Deployment source evidence incomplete. Missing: " + ", ".join(missing)
    reports = repo_root / "reports" / "cloud"
    verification_files = sorted(reports.rglob("cloud-verification.json"))
    if not verification_files:
        return False, "No reports/cloud/**/cloud-verification.json. Deploy and download cloud deployment artifacts first."

    evidence = [
        f"Shared cloud deployment, with focus on {service.key}. "
        "This application uses user-assigned managed identity and a public edge container "
        "per service; backend/database containers share its network namespace, rather than "
        "separate internal-ingress Container Apps. Validate this topology from source. "
        "Observation success is NOT deployment success. Compare release/commit metadata "
        "across historical runs; do not treat old successful verification as current proof.",
    ]
    try:
        for path in sources:
            evidence.append(f"{path.relative_to(repo_root)}:\n{path.read_text(encoding='utf-8')}")
        for verification in verification_files:
            report = json.loads(verification.read_text(encoding="utf-8"))
            if (
                not isinstance(report, dict)
                or not isinstance(report.get("passed"), bool)
                or not isinstance(report.get("checks"), list)
                or not report["checks"]
            ):
                return False, f"Invalid or empty deployment verification: {verification.relative_to(repo_root)}"
            # Only explicitly sanitized published artifacts; never read .cloud state,
            # rendered manifests, credentials, or raw container logs.
            for name in (
                "cloud-verification.json", "deployment-summary.md", "apps.json",
                "deployed-configuration.json", "registry-security.json", "release.json", "images.json",
            ):
                path = verification.parent / name
                if path.is_file():
                    text = path.read_text(encoding="utf-8")
                    if path.suffix == ".json":
                        json.loads(text)
                    evidence.append(f"{path.relative_to(repo_root)}:\n{text}")
    except (OSError, ValueError) as exc:
        return False, f"Unreadable or malformed deployment evidence: {exc}"
    return True, "\n\n".join(evidence)
