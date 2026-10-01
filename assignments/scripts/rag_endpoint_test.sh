#!/usr/bin/env bash
# Exercise the assignment backend's HTTP routes that proxy to the shared RAG server.
# The assignment stack, RAG server, populated assignment index, and Ollama must be running.
#
# Usage:
#   bash assignments/scripts/rag_endpoint_test.sh
#   ASSIGNMENTS_BACKEND_URL=http://127.0.0.1:5003 bash assignments/scripts/rag_endpoint_test.sh
#   ASSIGNMENTS_RAG_LOG_FILE=/tmp/assignments-rag.log bash assignments/scripts/rag_endpoint_test.sh
set -Eeuo pipefail

BACKEND="${ASSIGNMENTS_BACKEND_URL:-http://localhost:5003}"
BACKEND="${BACKEND%/}"
CURL_MAX_TIME="${ASSIGNMENTS_RAG_CURL_MAX_TIME:-180}"
LOG_FILE="${ASSIGNMENTS_RAG_LOG_FILE:-}"
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
    local method="$1" path="$2" response_file="$3"
    shift 3
    local url="$BACKEND$path"
    local status

    log "" >&2
    log ">>> $method $url" >&2
    status="$(curl --silent --show-error --connect-timeout 3 \
        --max-time "$CURL_MAX_TIME" -X "$method" "$@" \
        --output "$response_file" --write-out '%{http_code}' "$url")" || {
        log "<<< request failed" >&2
        return 1
    }

    log "<<< HTTP $status" >&2
    log "$(<"$response_file")" >&2
    printf '%s' "$status"
}

expect_status() {
    local expected="$1" actual="$2" label="$3"
    if [[ "$actual" != "$expected" ]]; then
        log "FAIL $label: expected HTTP $expected, got $actual"
        FAILURES=$((FAILURES + 1))
        return 1
    fi
    log "PASS $label -> HTTP $actual"
}

status_body="$TMP_DIR/status.json"
status="$(request GET /integration/rag/status "$status_body")" || exit 1
expect_status 200 "$status" "GET /integration/rag/status" || true
if [[ "$status" == "200" ]]; then
    if jq -e '.enabled == true and .rag_enabled == true' "$status_body" >/dev/null; then
        log "PASS RAG integration reports enabled"
    else
        log "FAIL RAG status did not report the integration enabled"
        FAILURES=$((FAILURES + 1))
    fi
fi

health_body="$TMP_DIR/health.json"
status="$(request GET /integration/rag/health "$health_body" -H 'X-RAG-Mode: on')" || exit 1
expect_status 200 "$status" "GET /integration/rag/health" || true
if [[ "$status" == "200" ]] && ! jq -e '.status == "ok"' "$health_body" >/dev/null; then
    log "FAIL RAG health response did not report status=ok"
    FAILURES=$((FAILURES + 1))
fi

ingest_body="$TMP_DIR/ingest.json"
status="$(request POST /integration/rag/ingest "$ingest_body" \
    -H 'Content-Type: application/json' -H 'X-RAG-Mode: on' --data '{}')" || exit 1
expect_status 200 "$status" "POST /integration/rag/ingest" || true
if [[ "$status" == "200" ]] && ! jq -e '.status == "success" and any(.services[]; .service == "assignments" and .status == "success" and .chunk_count > 0)' "$ingest_body" >/dev/null; then
    log "FAIL assignment ingest did not report successfully indexed chunks"
    FAILURES=$((FAILURES + 1))
fi

query_payload='{"query":"What must the Release 0 Technical Report include?"}'
retrieve_body="$TMP_DIR/retrieve.json"
status="$(request POST /integration/rag/retrieve "$retrieve_body" \
    -H 'Content-Type: application/json' -H 'X-RAG-Mode: on' \
    --data "$query_payload")" || exit 1
expect_status 200 "$status" "POST /integration/rag/retrieve" || true
if [[ "$status" == "200" ]] && ! jq -e '.status == "success" and any(.results[]; .service == "assignments" and (.title | contains("Release 0 Technical Report")))' "$retrieve_body" >/dev/null; then
    log "FAIL retrieval did not return the expected assignment evidence"
    FAILURES=$((FAILURES + 1))
fi

answer_body="$TMP_DIR/answer.json"
status="$(request POST /integration/rag/answer "$answer_body" \
    -H 'Content-Type: application/json' -H 'X-RAG-Mode: on' \
    --data "$query_payload")" || exit 1
expect_status 200 "$status" "POST /integration/rag/answer" || true
if [[ "$status" == "200" ]] && ! jq -e '
    .status == "success" and
    (.answer | type == "string") and
    (.citations | type == "array") and
    (.confidence_category | IN("High", "Medium", "Low", "None")) and
    any(.citations[]; .service == "assignments" and (.title | contains("Release 0 Technical Report")))
' "$answer_body" >/dev/null; then
    log "FAIL answer was missing the expected assignment citation or response fields"
    FAILURES=$((FAILURES + 1))
fi

# This query contains only stopwords removed by the embedding tokenizer. It must
# produce no retrieval context, so answer generation must return the fixed fallback.
empty_payload='{"query":"what is it"}'
empty_body="$TMP_DIR/insufficient.json"
status="$(request POST /integration/rag/answer "$empty_body" \
    -H 'Content-Type: application/json' -H 'X-RAG-Mode: on' \
    --data "$empty_payload")" || exit 1
expect_status 200 "$status" "POST /integration/rag/answer (insufficient context)" || true
if [[ "$status" == "200" ]] && ! jq -e '.status == "success" and .answer == "Insufficient evidence." and (.citations | length == 0) and .confidence_category == "None"' "$empty_body" >/dev/null; then
    log "FAIL insufficient-context response was not the expected grounded fallback"
    FAILURES=$((FAILURES + 1))
fi

disabled_body="$TMP_DIR/disabled.json"
status="$(request POST /integration/rag/retrieve "$disabled_body" \
    -H 'Content-Type: application/json' -H 'X-RAG-Mode: off' \
    --data "$query_payload")" || exit 1
expect_status 403 "$status" "POST /integration/rag/retrieve with request mode off" || true

if (( FAILURES > 0 )); then
    log "Assignment RAG endpoint test failed: $FAILURES check(s) failed."
    exit 1
fi

log "All assignment RAG backend endpoint checks passed."