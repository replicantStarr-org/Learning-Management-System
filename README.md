# ASD-Assessment
Assessment group assessment for Advanced Software Development

## Local security checks

From the repository root, using Python 3.11 or newer:

```sh
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
pre-commit install
pre-commit run --all-files
```

Hooks install pinned tools in isolated environments and block commits on findings or scan errors:

- **Ruff:** security rules across the repository, explicitly using root `pyproject.toml` so nested service lint settings cannot override this scan. Virtual environments are excluded.
- **detect-secrets:** all Git-tracked files, including newly staged files. Only the exact non-secret Ollama placeholder `ollama` is excluded. No credential verification requests are sent.
- **pip-audit:** independently audits every tracked or non-ignored new `requirements*.txt`, including development and supporting-service requirements, with transitive dependency resolution. Separate audits avoid conflicts between services’ version pins and never audit the hook/system environment.

Checks run on every commit, regardless of which files changed. Dependency audits continue after individual failures so every requirements file gets a result. Secret scanning excludes untracked files until staged.

Each hook writes its latest timestamped JSON evidence to `reports/pre-commit/` (Git-ignored), including the base commit and each scan’s command, status, exit code, and output. Evidence is overwritten on the next run; a PASS is not a release approval. During commits, pre-commit hides unstaged changes to tracked files; manual runs inspect the working tree.
