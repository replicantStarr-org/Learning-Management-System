#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd "$script_dir"

skip_reports=false
python_args=()
for arg in "$@"; do
    if [[ "$arg" == "--skip-report-download" ]]; then
        skip_reports=true
    else
        python_args+=("$arg")
    fi
done

if [[ "$skip_reports" == false ]]; then
    if ! "$repo_root/download_reports.sh"; then
        echo "Unable to update reports/. The downloader uses the GitHub CLI (gh) and requires it to be installed and authenticated." >&2
        echo "Run again with --skip-report-download to skip downloading (for non-DevOps reviews or manually supplied reports)." >&2
        exit 1
    fi
fi

VENV=.venv
STAMP="$VENV/.requirements-installed"
if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
fi
if [[ ! -f "$STAMP" || requirements.txt -nt "$STAMP" ]]; then
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r requirements.txt
    touch "$STAMP"
fi

exec "$VENV/bin/python" agentic_loop.py "${python_args[@]}"
