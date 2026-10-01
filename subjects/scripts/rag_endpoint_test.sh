#!/usr/bin/env bash
# Exercise the RAG server directly and through the subject backend.
#
# Usage:
#   ./scripts/rag_endpoint_test.sh
#   RAG_DIRECT_URL=http://localhost:5003 RAG_REFRESH_PATH=/rag/refresh \
#       ./scripts/rag_endpoint_test.sh
#
# The repository's RAG server uses port 5010 by default. Set RAG_DIRECT_URL to
# the port used by another local RAG deployment (for example, 5003). The
# backend route is called /rag/ingest in this repository; deployments exposing
# the equivalent /rag/refresh route can set RAG_REFRESH_PATH=/rag/refresh.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

RAG_DIRECT_URL="${RAG_DIRECT_URL:-${RAG_SERVER_URL:-http://localhost:5010}}"
RAG_DIRECT_URL="${RAG_DIRECT_URL%/}"
BACKEND_URL="${RAG_BACKEND_URL:-http://localhost:5001}"
BACKEND_URL="${BACKEND_URL%/}"
RAG_REFRESH_PATH="${RAG_REFRESH_PATH:-/rag/ingest}"
CURL_MAX_TIME="${RAG_CURL_MAX_TIME:-180}"
LOG_FILE="${RAG_LOG_FILE:-}"
TMP_DIR="$(mktemp -d)"
FAILURES=0

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ -n "$LOG_FILE" ]]; then
    : > "$LOG_FILE" || {
        printf 'Unable to write RAG log file: %s\n' "$LOG_FILE" >&2
        exit 1
    }
fi

log() {
    if [[ -n "$LOG_FILE" ]]; then
        printf '%s\n' "$*" | tee -a "$LOG_FILE"
    else
        printf '%s\n' "$*"
    fi
}

request() {
    local base_url="$1" method="$2" path="$3" response_file="$4"
    shift 4
    local status

    # Keep request logging on stderr so command substitution returns only the
    # HTTP status to the caller.
    log "" >&2
    log ">>> $method $base_url$path" >&2

    status="$(curl --silent --show-error --connect-timeout 3 \
        --max-time "$CURL_MAX_TIME" -X "$method" "$@" \
        --output "$response_file" --write-out '%{http_code}' \
        "$base_url$path")" \
        || {
            log "<<< request failed" >&2
            return 1
        }

    log "<<< HTTP $status" >&2
    log "$(<"$response_file")" >&2
    printf '%s' "$status"
}

check_json() {
    local name="$1" base_url="$2" method="$3" path="$4" expected="$5" marker="$6"
    shift 6
    local response_file="$TMP_DIR/response" status

    status="$(request "$base_url" "$method" "$path" "$response_file" "$@")" || {
        log "FAIL: $name request failed"
        return 1
    }
    [[ "$status" == "$expected" ]] || {
        log "FAIL: $name expected HTTP $expected, got $status"
        return 1
    }
    grep -Eq "$marker" "$response_file" || {
        log "FAIL: $name response did not contain the expected JSON"
        return 1
    }
    log "PASS: $name"
}

check_success_json() {
    local name="$1" base_url="$2" method="$3" path="$4" marker="$5"
    shift 5
    local response_file="$TMP_DIR/response" status

    status="$(request "$base_url" "$method" "$path" "$response_file" "$@")" || {
        log "FAIL: $name request failed"
        return 1
    }
    [[ "$status" =~ ^2[0-9][0-9]$ ]] || {
        log "FAIL: $name expected a successful HTTP response, got $status"
        return 1
    }
    grep -Eq "$marker" "$response_file" || {
        log "FAIL: $name response did not contain the expected JSON"
        return 1
    }
    log "PASS: $name"
}

# Direct RAG liveness check.
check_json "direct RAG health" "$RAG_DIRECT_URL" GET "/health" 200 \
    '"status"[[:space:]]*:[[:space:]]*"ok"' \
    || FAILURES=$((FAILURES + 1))

# The remaining checks exercise the backend relay. The backend sends JSON to
# the RAG service, which is equivalent to the form-style curl examples:
#   POST /rag/refresh
#   POST /rag/retrieve  query=students enrolled in ASD101&k=5
#   POST /rag/answer    query=Which students are enrolled in ASD101?&k=5
check_json "backend RAG status" "$BACKEND_URL" GET "/rag/status" 200 \
    '"enabled"[[:space:]]*:[[:space:]]*true' \
    || FAILURES=$((FAILURES + 1))
check_json "backend RAG health relay" "$BACKEND_URL" GET "/rag/health" 200 \
    '"status"[[:space:]]*:[[:space:]]*"ok"' \
    || FAILURES=$((FAILURES + 1))

check_success_json "backend RAG refresh/ingest" "$BACKEND_URL" POST "$RAG_REFRESH_PATH" \
    '"status"[[:space:]]*:' \
    -H 'Content-Type: application/json' \
    -H 'X-RAG-Mode: on' \
    --data '{}' \
    || FAILURES=$((FAILURES + 1))

query_payload='{"query":"subject coordinator ASD101","k":5}'
check_json "backend RAG retrieve" "$BACKEND_URL" POST "/rag/retrieve" 200 \
    '"results"[[:space:]]*:' \
    -H 'Content-Type: application/json' \
    -H 'X-RAG-Mode: on' \
    --data "$query_payload" \
    || FAILURES=$((FAILURES + 1))

answer_payload='{"query":"Who is the subject coordinator for ASD101?","k":5}'
check_json "backend RAG answer" "$BACKEND_URL" POST "/rag/answer" 200 \
    '"answer"[[:space:]]*:' \
    -H 'Content-Type: application/json' \
    -H 'X-RAG-Mode: on' \
    --data "$answer_payload" \
    || FAILURES=$((FAILURES + 1))

if (( FAILURES > 0 )); then
    log ""
    log "RAG endpoint test failed: $FAILURES check(s) failed."
    exit 1
fi

log ""
log "All RAG endpoint checks passed."
