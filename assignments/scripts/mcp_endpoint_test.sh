#!/usr/bin/env bash
# Exercise the assignment backend's HTTP routes that call the shared MCP server.
# The backend, assignment database, and MCP server must already be running.
#
# Usage:
#   bash assignments/scripts/mcp_endpoint_test.sh
#   ASSIGNMENTS_MCP_LOG_FILE=/tmp/assignments-mcp.log bash assignments/scripts/mcp_endpoint_test.sh
set -Eeuo pipefail

BACKEND="${ASSIGNMENTS_BACKEND_URL:-http://localhost:5003}"
BACKEND="${BACKEND%/}"
CURL_MAX_TIME="${ASSIGNMENTS_MCP_CURL_MAX_TIME:-20}"
LOG_FILE="${ASSIGNMENTS_MCP_LOG_FILE:-}"
TMP_DIR="$(mktemp -d)"
FAILURES=0

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ -n "$LOG_FILE" ]]; then
    : > "$LOG_FILE" || {
        printf 'Unable to write MCP log file: %s\n' "$LOG_FILE" >&2
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
status="$(request GET /integration/mcp/status "$status_body")" || exit 1
expect_status 200 "$status" "GET /integration/mcp/status" || true
if [[ "$status" == "200" ]]; then
    if jq -e '.enabled == true and .mcp_enabled == true' "$status_body" >/dev/null; then
        log "PASS MCP integration reports enabled"
    else
        log "FAIL MCP status did not report the integration enabled"
        FAILURES=$((FAILURES + 1))
    fi
fi

list_body="$TMP_DIR/list.json"
status="$(request POST /integration/mcp/assignments "$list_body" \
    -H 'Content-Type: application/json' -H 'X-MCP-Mode: on' \
    --data '{"action":"list"}')" || exit 1
expect_status 200 "$status" "POST /integration/mcp/assignments (list)" || true
if [[ "$status" == "200" ]] && ! jq -e '.status == "success" and .tool == "assignments_list" and (.result | type == "array")' "$list_body" >/dev/null; then
    log "FAIL assignment list response had an unexpected shape"
    FAILURES=$((FAILURES + 1))
fi
assignment_id="$(jq -r '.result[0].assignment_id // empty' "$list_body")"
if [[ ! "$assignment_id" =~ ^[1-9][0-9]*$ ]]; then
    log "FAIL assignments_list returned no valid assignment_id to use for the detail check"
    FAILURES=$((FAILURES + 1))
fi

upcoming_body="$TMP_DIR/upcoming.json"
status="$(request POST /integration/mcp/assignments "$upcoming_body" \
    -H 'Content-Type: application/json' -H 'X-MCP-Mode: on' \
    --data '{"action":"upcoming","days":365}')" || exit 1
expect_status 200 "$status" "POST /integration/mcp/assignments (upcoming)" || true
if [[ "$status" == "200" ]] && ! jq -e '.status == "success" and .tool == "assignments_upcoming" and (.result | type == "array")' "$upcoming_body" >/dev/null; then
    log "FAIL assignment upcoming response had an unexpected shape"
    FAILURES=$((FAILURES + 1))
fi

if [[ "$assignment_id" =~ ^[1-9][0-9]*$ ]]; then
    detail_body="$TMP_DIR/detail.json"
    status="$(request POST /integration/mcp/assignments "$detail_body" \
        -H 'Content-Type: application/json' -H 'X-MCP-Mode: on' \
        --data "{\"action\":\"get\",\"assignment_id\":$assignment_id}")" || exit 1
    expect_status 200 "$status" "POST /integration/mcp/assignments (get $assignment_id)" || true
    if [[ "$status" == "200" ]] && ! jq -e --argjson id "$assignment_id" '.status == "success" and .tool == "assignments_get" and .result.assignment_id == $id' "$detail_body" >/dev/null; then
        log "FAIL assignment detail response did not match the requested ID"
        FAILURES=$((FAILURES + 1))
    fi
fi

for invalid in '{"action":"get","assignment_id":0}' '{"action":"upcoming","days":0}'; do
    error_body="$TMP_DIR/error.json"
    status="$(request POST /integration/mcp/assignments "$error_body" \
        -H 'Content-Type: application/json' -H 'X-MCP-Mode: on' --data "$invalid")" || exit 1
    expect_status 400 "$status" "invalid MCP request $invalid" || true
done

if (( FAILURES > 0 )); then
    log "Assignment MCP endpoint test failed: $FAILURES check(s) failed."
    exit 1
fi

log "All assignment MCP backend endpoint checks passed."