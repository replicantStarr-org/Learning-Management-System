#!/usr/bin/env bash
# ./run.sh [start]   start the RAG server in this terminal (Ctrl+C stops it)
# ./run.sh stop      stop a RAG server started from this folder
set -euo pipefail
cd "$(dirname "$0")"

VENV_PYTHON=.venv_rag/bin/python
PID_FILE=rag-server.pid
STOP_TIMEOUT_SECONDS=30

# Prints the server's pid if it is running. A pid file left by a crash, or a
# pid since reused by an unrelated process, does not count.
running_pid() {
    [ -f "$PID_FILE" ] || return 1
    local pid
    pid=$(cat "$PID_FILE")
    ps -p "$pid" -o args= 2>/dev/null | grep -q "server.http_server" || return 1
    echo "$pid"
}

start() {
    if [ ! -x "$VENV_PYTHON" ]; then
        echo "error: $VENV_PYTHON not found; run ./init.sh first" >&2
        exit 1
    fi
    if pid=$(running_pid); then
        echo "error: RAG server is already running (pid $pid); stop it with ./run.sh stop" >&2
        exit 1
    fi
    exec "$VENV_PYTHON" -m server.http_server
}

stop() {
    if ! pid=$(running_pid); then
        rm -f "$PID_FILE"
        echo "RAG server is not running"
        return
    fi

    echo "Stopping RAG server (pid $pid)"
    kill -TERM "$pid"
    for _ in $(seq "$STOP_TIMEOUT_SECONDS"); do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "RAG server stopped"
            return
        fi
        sleep 1
    done

    echo "warning: still running after ${STOP_TIMEOUT_SECONDS}s; forcing it to stop" >&2
    kill -KILL "$pid"
    rm -f "$PID_FILE"
}

case "${1:-start}" in
    start) start ;;
    stop) stop ;;
    *)
        echo "usage: ./run.sh [start|stop]" >&2
        exit 2
        ;;
esac
