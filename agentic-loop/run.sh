#!/usr/bin/env bash
#
# Runs the loop in its own virtual environment. Every argument is passed through
# to agentic_loop.py, so:
#
#   ./run.sh --offline --iterations 5
#
set -euo pipefail

# The venv and services.yml are found relative to this script, so it does not
# matter which directory it is called from.
cd "$(dirname "$0")"

VENV=.venv
STAMP="$VENV/.requirements-installed"

if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi

# Installing only when requirements.txt is newer than the last install keeps a
# warm run off the network entirely.
if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r requirements.txt
    touch "$STAMP"
fi

exec "$VENV/bin/python" agentic_loop.py "$@"
