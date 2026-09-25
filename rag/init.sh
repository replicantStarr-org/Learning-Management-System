set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
VENV=.venv_rag
VENV_PYTHON=$VENV/bin/python

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "error: $PYTHON not found; install Python 3.11 or newer" >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    echo "error: Python 3.11 or newer is required, found $("$PYTHON" --version 2>&1)" >&2
    exit 1
fi

if [[ ! -x $VENV_PYTHON ]]; then
    echo "Creating $VENV"
    rm -rf "$VENV"
    "$PYTHON" -m venv "$VENV"
fi

echo "Installing dependencies (chromadb can take a few minutes)"
"$VENV_PYTHON" -m pip install -q --upgrade pip
"$VENV_PYTHON" -m pip install -q -r requirements.txt

echo
echo "Setup complete. Start the server with:"
echo "  $VENV_PYTHON http_server.py"
