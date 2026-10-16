# Quizzes pre-commit security report

- **Generated:** 2026-10-16T02:04:37Z
- **Branch:** mitch/quizzes-release2
- **Commit:** 0646b07
- **pre-commit:** pre-commit 4.7.0
- **Config:** `.pre-commit-config.yaml` (Ruff rules in `quizzes/pyproject.toml`, baseline in `.secrets.baseline`)
- **Overall:** PASSED

| Hook | Scan | Exit code | Result |
| --- | --- | --- | --- |
| ruff-check | Ruff security rules (flake8-bandit, `S`) over quizzes Python | 0 | Passed |
| detect-secrets | Secrets in tracked files, against the baseline | 0 | Passed |
| pip-audit | Known vulnerabilities in the quizzes backend, database and test requirements | 0 | Passed |

## ruff-check output

```text
ruff security rules (flake8-bandit)......................................Passed
```

## detect-secrets output

```text
detect-secrets...........................................................Passed
```

## pip-audit output

```text
pip-audit (known vulnerabilities in pinned dependencies).......................Passed
```

## Findings from the first scan and how they were resolved

| Scan | Finding | Resolution |
| --- | --- | --- |
| pip-audit | flask 3.0.3 (PYSEC-2026-2151), flask-cors 4.0.1 (PYSEC-2024-71 and three PYSEC-2026 advisories), requests 2.32.3 (PYSEC-2026-1872, PYSEC-2026-2275), pytest 8.3.3 (PYSEC-2026-1845) | Upgraded to flask 3.1.3, flask-cors 6.0.0, requests 2.33.0, pytest 9.0.3. Endpoint tests and CORS headers rechecked after the upgrade. |
| Ruff S104 | Flask binds to 0.0.0.0 in backend/app.py and database/app.py | Documented with `noqa`: the service must listen on all interfaces inside its container. |
| Ruff S608 | SQL built with an f-string in database/app.py (quiz update) | Documented with `noqa`: column names come from the fixed QUIZ_FIELDS list and all values are bound parameters. |
| Ruff S101 | `assert` in the pytest tests | Ignored for `tests/` in quizzes/pyproject.toml, since pytest tests assert by design. |
| detect-secrets | No findings | Baseline is empty. |
