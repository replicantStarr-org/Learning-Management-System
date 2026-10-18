import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = {
    "ruff": ["ruff", "check", "--output-format=json"],
    "detect-secrets": ["detect_secrets", "scan", "--no-verify"],
    "pip-audit": ["pip_audit", "--strict", "--format=json", "--progress-spinner=off"],
}


def run_command(command, root, timeout=600):
    return subprocess.run(  # noqa: S603 - argument lists from local hook configuration; no shell
        command, cwd=root, capture_output=True, text=True, timeout=timeout
    )


def has_findings(tool, output):
    data = json.loads(output)
    if tool == "ruff":
        if not isinstance(data, list):
            raise ValueError("Expected a list of Ruff findings")
        return bool(data)
    if tool == "detect-secrets":
        if not isinstance(data.get("results"), dict):
            raise ValueError("Expected secret scan results")
        return any(data["results"].values())
    if not isinstance(data.get("dependencies"), list):
        raise ValueError("Expected audited dependencies")
    return any(item.get("vulns") or "skip_reason" in item for item in data["dependencies"])


def audit_findings(output, requirements, root):
    data = json.loads(output)
    if not isinstance(data.get("dependencies"), list):
        raise ValueError("Expected audited dependencies")
    policy = root / ".pip-audit-exemptions.json"
    exemptions = json.loads(policy.read_text(encoding="utf-8")) if policy.exists() else []
    if not isinstance(exemptions, list):
        raise ValueError("Expected a list of dependency exemptions")
    applied = []
    fields = {"requirements", "package", "version", "vulnerabilities", "reason", "expires"}
    for exemption in exemptions:
        if (
            not isinstance(exemption, dict)
            or set(exemption) != fields
            or not all(isinstance(exemption[key], str) and exemption[key] for key in fields - {"vulnerabilities"})
            or not isinstance(exemption["vulnerabilities"], list)
            or not exemption["vulnerabilities"]
            or not all(isinstance(item, str) and item for item in exemption["vulnerabilities"])
        ):
            raise ValueError("Invalid dependency exemption; explicit scope, rationale, and expiry are required")
        expiry = date.fromisoformat(exemption["expires"])
        if exemption["requirements"] != requirements:
            continue
        if expiry < datetime.now(timezone.utc).date():
            raise ValueError(f"Expired dependency exemption for {requirements}: {exemption['package']}")
        for package in data["dependencies"]:
            if (package.get("name"), package.get("version")) != (exemption["package"], exemption["version"]):
                continue
            remaining = []
            for vulnerability in package.get("vulns", []):
                if vulnerability["id"] not in exemption["vulnerabilities"]:
                    remaining.append(vulnerability)
                    continue
                accepted = {
                    "requirements": requirements,
                    "package": package["name"],
                    "version": package["version"],
                    "id": vulnerability["id"],
                    "reason": exemption["reason"],
                    "expires": exemption["expires"],
                }
                if accepted not in applied:
                    applied.append(accepted)
            package["vulns"] = remaining
    return has_findings("pip-audit", json.dumps(data)), applied


def scan_arguments(tool, arguments, root):
    if tool != "pip-audit":
        return [arguments]
    if arguments:
        raise ValueError("Dependency audits discover requirements files; no arguments are accepted")
    result = run_command(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--",
         "requirements*.txt", "**/requirements*.txt"],
        root,
        timeout=10,
    )
    if result.returncode != 0:
        raise ValueError(f"Could not discover requirements files: {result.stderr}")
    paths = sorted({path for path in result.stdout.split("\0") if path and (root / path).is_file()})
    if not paths:
        raise ValueError("No requirements files found; refusing to audit the hook environment")
    return [["-r", path] for path in paths]


def scan(tool, arguments, root):
    command = [sys.executable, "-m", *TOOLS[tool], *arguments]
    result = {"command": command[1:], "status": "FAIL", "exit_code": None, "stdout": "", "stderr": ""}
    try:
        completed = run_command(command, root)
        result.update(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        if tool == "pip-audit":
            findings, exemptions = audit_findings(completed.stdout, arguments[1], root)
            result["exemptions"] = exemptions
        else:
            findings = has_findings(tool, completed.stdout)
        exempted_failure = completed.returncode == 1 and bool(result.get("exemptions"))
        if (completed.returncode == 0 or exempted_failure) and not findings:
            result["status"] = "PASS"
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError, KeyError) as exc:
        result["stderr"] += f"\n{exc}"
    return result


def run_scan(tool, arguments, root=ROOT):
    report = {
        "tool": tool,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL",
        "commit": None,
        "scans": [],
    }
    try:
        commit = run_command(["git", "rev-parse", "HEAD"], root, timeout=10)
        if commit.returncode == 0:
            report["commit"] = commit.stdout.strip()
        for scoped_arguments in scan_arguments(tool, arguments, root):
            result = scan(tool, scoped_arguments, root)
            report["scans"].append(result)
            print(f"{tool} {' '.join(scoped_arguments)}: {result['status']}")
            for exemption in result.get("exemptions", []):
                print(f"  Exempted {exemption['package']}=={exemption['version']} {exemption['id']} through {exemption['expires']}")
            if result["status"] != "PASS":
                print(result["stdout"])
                print(result["stderr"], file=sys.stderr)
        if report["scans"] and all(result["status"] == "PASS" for result in report["scans"]):
            report["status"] = "PASS"
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        report["error"] = str(exc)
        print(str(exc), file=sys.stderr)

    report_path = root / "reports" / "pre-commit" / f"{tool}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{tool}: {report['status']} ({report_path.relative_to(root)})")
    return 0 if report["status"] == "PASS" else 1


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TOOLS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(TOOLS)}> [scan arguments]", file=sys.stderr)
        return 2
    return run_scan(sys.argv[1], sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
