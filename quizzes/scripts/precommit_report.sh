#!/usr/bin/env bash
# Runs the three Release 2 pre-commit security hooks and writes quizzes/evidence/precommit-report.md.
# Needs `pre-commit` on PATH (pip install pre-commit). Run it from anywhere inside the repository.
set -uo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"
report="quizzes/evidence/precommit-report.md"
mkdir -p "$(dirname "$report")"

hooks=(ruff-check detect-secrets pip-audit)
declare -A exit_codes outputs

for hook in "${hooks[@]}"; do
  outputs[$hook]="$(pre-commit run "$hook" --all-files --color never 2>&1)"
  exit_codes[$hook]=$?
done

overall=0
for hook in "${hooks[@]}"; do
  [[ "${exit_codes[$hook]}" -eq 0 ]] || overall=1
done

{
  echo "# Quizzes pre-commit security report"
  echo
  echo "- **Generated:** $(date --utc +'%Y-%m-%dT%H:%M:%SZ')"
  echo "- **Branch:** $(git rev-parse --abbrev-ref HEAD)"
  echo "- **Commit:** $(git rev-parse --short HEAD)"
  echo "- **pre-commit:** $(pre-commit --version)"
  echo "- **Config:** \`.pre-commit-config.yaml\` (Ruff rules in \`quizzes/pyproject.toml\`, baseline in \`.secrets.baseline\`)"
  echo "- **Overall:** $([[ $overall -eq 0 ]] && echo PASSED || echo FAILED)"
  echo
  echo "| Hook | Scan | Exit code | Result |"
  echo "| --- | --- | --- | --- |"
  echo "| ruff-check | Ruff security rules (flake8-bandit, \`S\`) over quizzes Python | ${exit_codes[ruff-check]} | $([[ ${exit_codes[ruff-check]} -eq 0 ]] && echo Passed || echo Failed) |"
  echo "| detect-secrets | Secrets in tracked files, against the baseline | ${exit_codes[detect-secrets]} | $([[ ${exit_codes[detect-secrets]} -eq 0 ]] && echo Passed || echo Failed) |"
  echo "| pip-audit | Known vulnerabilities in the quizzes backend, database and test requirements | ${exit_codes[pip-audit]} | $([[ ${exit_codes[pip-audit]} -eq 0 ]] && echo Passed || echo Failed) |"
  echo
  for hook in "${hooks[@]}"; do
    echo "## $hook output"
    echo
    echo '```text'
    echo "${outputs[$hook]}"
    echo '```'
    echo
  done
  cat <<'FINDINGS'
## Findings from the first scan and how they were resolved

| Scan | Finding | Resolution |
| --- | --- | --- |
| pip-audit | flask 3.0.3 (PYSEC-2026-2151), flask-cors 4.0.1 (PYSEC-2024-71 and three PYSEC-2026 advisories), requests 2.32.3 (PYSEC-2026-1872, PYSEC-2026-2275), pytest 8.3.3 (PYSEC-2026-1845) | Upgraded to flask 3.1.3, flask-cors 6.0.0, requests 2.33.0, pytest 9.0.3. Endpoint tests and CORS headers rechecked after the upgrade. |
| Ruff S104 | Flask binds to 0.0.0.0 in backend/app.py and database/app.py | Documented with `noqa`: the service must listen on all interfaces inside its container. |
| Ruff S608 | SQL built with an f-string in database/app.py (quiz update) | Documented with `noqa`: column names come from the fixed QUIZ_FIELDS list and all values are bound parameters. |
| Ruff S101 | `assert` in the pytest tests | Ignored for `tests/` in quizzes/pyproject.toml, since pytest tests assert by design. |
| detect-secrets | No findings | Baseline is empty. |
FINDINGS
} > "$report"

echo "Wrote $report (overall: $([[ $overall -eq 0 ]] && echo PASSED || echo FAILED))"
exit "$overall"
