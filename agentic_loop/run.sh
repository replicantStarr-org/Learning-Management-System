#!/usr/bin/env bash

set -euo pipefail

VENV=.venv
STAMP="$VENV/.requirements-installed"

if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi

if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r requirements.txt
    touch "$STAMP"
fi

exec "$VENV/bin/python" agentic_loop.py "$@"