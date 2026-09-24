VENV=.venv_rag
if [[ ! -f VENV ]]; then
    echo "Creating .venv"
    python3 -m venv $VENV
fi

$VENV/bin/python -m pip install -q -r requirements.txt
