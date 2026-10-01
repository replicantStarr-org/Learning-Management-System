#!/usr/bin/env bash
# Terminal validation of the quiz MCP integration: calls every backend /mcp
# route, which calls the shared MCP server, and logs each request and response.
#
# Needs the quiz containers and the MCP server (../mcp/run.sh) running.
#
# Usage:
#   ./scripts/mcp_endpoint_test.sh
#   MCP_LOG_FILE=mcp-validation.log ./scripts/mcp_endpoint_test.sh
set -Eeuo pipefail

BACKEND_URL="${MCP_BACKEND_URL:-http://localhost:5004}"
BACKEND_URL="${BACKEND_URL%/}"
CURL_MAX_TIME="${MCP_CURL_MAX_TIME:-30}"
LOG_FILE="${MCP_LOG_FILE:-}"
RESPONSE="$(mktemp)"
FAILURES=0
trap 'rm -f "$RESPONSE"' EXIT

[[ -z "$LOG_FILE" ]] || : > "$LOG_FILE"

log() {
    if [[ -n "$LOG_FILE" ]]; then
        printf '%s\n' "$*" | tee -a "$LOG_FILE"
    else
        printf '%s\n' "$*"
    fi
}

# check METHOD PATH EXPECTED_STATUS EXPECTED_TEXT [JSON_BODY]
check() {
    local method="$1" path="$2" expected_status="$3" expected_text="$4" body="${5:-}"
    local -a args=(--silent --show-error --connect-timeout 3 --max-time "$CURL_MAX_TIME" -X "$method")
    [[ -z "$body" ]] || args+=(-H 'Content-Type: application/json' --data "$body")

    log ""
    log ">>> $method $BACKEND_URL$path ${body}"
    local status
    status="$(curl "${args[@]}" --output "$RESPONSE" --write-out '%{http_code}' "$BACKEND_URL$path")" || {
        log "FAIL: request could not be sent"
        FAILURES=$((FAILURES + 1))
        return
    }
    log "<<< HTTP $status"
    log "$(head -c 1500 "$RESPONSE")"

    if [[ "$status" != "$expected_status" ]]; then
        log "FAIL: expected HTTP $expected_status"
        FAILURES=$((FAILURES + 1))
    elif ! grep -Fq -- "$expected_text" "$RESPONSE"; then
        log "FAIL: response did not contain $expected_text"
        FAILURES=$((FAILURES + 1))
    else
        log "PASS"
    fi
}

check GET /mcp/status 200 '"enabled":true'

# One successful call per tool, through the backend to the MCP server.
check POST /mcp/quizzes 200 '"tool":"quizzes_list"' '{"difficulty": "Easy"}'
check POST /mcp/quizzes 200 '"DBS102 - Database Systems"' '{"subject": "dbs102"}'
check POST /mcp/quiz 200 '"tool":"quizzes_get"' '{"quiz_id": 3}'
check POST /mcp/attempts 200 '"tool":"quizzes_attempts_list"' '{"quiz_id": 1}'
check POST /mcp/student-results 200 '"tool":"quizzes_student_results"' '{"student_name": "Ben Carter"}'
check POST /mcp/search 200 '"tool":"quizzes_search_questions"' '{"keyword": "primary key"}'

# Tool boundaries: the backend rejects malformed input before calling MCP (400),
# and the MCP tool itself refuses a quiz that does not exist (400).
check POST /mcp/quiz 400 'quiz_id must be a positive integer' '{"quiz_id": 0}'
check POST /mcp/quizzes 400 'difficulty must be Easy, Medium or Hard' '{"difficulty": "Impossible"}'
check POST /mcp/search 400 'keyword is required' '{"keyword": "  "}'
check POST /mcp/quiz 400 'Quiz not found' '{"quiz_id": 999999}'
check POST /mcp/student-results 400 'No quiz attempts exist' '{"student_name": "No Such Student"}'

log ""
if (( FAILURES > 0 )); then
    log "MCP endpoint validation failed: $FAILURES check(s) failed."
    exit 1
fi
log "All MCP endpoint checks passed."
