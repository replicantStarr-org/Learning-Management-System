#!/usr/bin/env bash
# Terminal validation of the quiz RAG integration: exercises the RAG server
# directly, then the same operations through the quiz backend's /rag routes,
# including a grounded answer and an insufficient-context answer.
#
# Needs the quiz containers, the RAG server (../rag-server/run.sh) and Ollama
# running. Answers come from a local model and can take a minute or more each.
#
# Usage:
#   ./scripts/rag_endpoint_test.sh
#   RAG_LOG_FILE=rag-validation.log ./scripts/rag_endpoint_test.sh
set -Eeuo pipefail

RAG_URL="${RAG_DIRECT_URL:-${RAG_SERVER_URL:-http://localhost:5010}}"
RAG_URL="${RAG_URL%/}"
BACKEND_URL="${RAG_BACKEND_URL:-http://localhost:5004}"
BACKEND_URL="${BACKEND_URL%/}"
CURL_MAX_TIME="${RAG_CURL_MAX_TIME:-240}"
LOG_FILE="${RAG_LOG_FILE:-}"
RESPONSE="$(mktemp)"
FAILURES=0
trap 'rm -f "$RESPONSE"' EXIT

GROUNDED_QUESTION="What score did Daniel Kim get on Web Security Essentials?"
UNSUPPORTED_QUESTION="What is the capital city of France?"

[[ -z "$LOG_FILE" ]] || : > "$LOG_FILE"

log() {
    if [[ -n "$LOG_FILE" ]]; then
        printf '%s\n' "$*" | tee -a "$LOG_FILE"
    else
        printf '%s\n' "$*"
    fi
}

# check METHOD URL [JSON_BODY] -- EXPECTED_TEXT...
# Passes on HTTP 200 when the response contains every expected text.
check() {
    local method="$1" url="$2" body=""
    shift 2
    if [[ "$1" != "--" ]]; then
        body="$1"
        shift
    fi
    shift
    local -a args=(--silent --show-error --connect-timeout 3 --max-time "$CURL_MAX_TIME" -X "$method")
    [[ -z "$body" ]] || args+=(-H 'Content-Type: application/json' --data "$body")

    log ""
    log ">>> $method $url ${body}"
    local status
    status="$(curl "${args[@]}" --output "$RESPONSE" --write-out '%{http_code}' "$url")" || {
        log "FAIL: request could not be sent"
        FAILURES=$((FAILURES + 1))
        return
    }
    log "<<< HTTP $status"
    log "$(head -c 2500 "$RESPONSE")"

    if [[ "$status" != "200" ]]; then
        log "FAIL: expected HTTP 200"
        FAILURES=$((FAILURES + 1))
        return
    fi
    local expected
    for expected in "$@"; do
        if ! grep -Eq -- "$expected" "$RESPONSE"; then
            log "FAIL: response did not match $expected"
            FAILURES=$((FAILURES + 1))
            return
        fi
    done
    log "PASS"
}

log "== RAG server, called directly =="
check GET "$RAG_URL/health" -- '"status": ?"ok"'
check POST "$RAG_URL/ingest" '{"service": "quizzes"}' -- '"service": ?"quizzes"' '"status": ?"success"'
check POST "$RAG_URL/retrieve" '{"query": "What is a primary key?", "service": "quizzes"}' \
    -- 'quizzes:quiz_question:9:'

log ""
log "== Through the quiz backend =="
check GET "$BACKEND_URL/rag/status" -- '"enabled": ?true' '"service": ?"quizzes"'
check GET "$BACKEND_URL/rag/health" -- '"status": ?"ok"'
check POST "$BACKEND_URL/rag/ingest" -- '"status": ?"success"'
check POST "$BACKEND_URL/rag/retrieve" '{"query": "primary key"}' -- '"results"' '"service": ?"quizzes"'
# Grounded answer: cites the attempt record and carries a confidence category.
check POST "$BACKEND_URL/rag/answer" "{\"query\": \"$GROUNDED_QUESTION\"}" \
    -- 'quizzes:quiz_attempt:8:' '"confidence_category": ?"(High|Medium|Low)"'
# Insufficient context: nothing relevant is indexed, so no answer is invented.
check POST "$BACKEND_URL/rag/answer" "{\"query\": \"$UNSUPPORTED_QUESTION\"}" \
    -- '"answer": ?"Insufficient evidence."' '"confidence_category": ?"None"' '"citations": ?\[\]'

log ""
if (( FAILURES > 0 )); then
    log "RAG endpoint validation failed: $FAILURES check(s) failed."
    exit 1
fi
log "All RAG endpoint checks passed."
