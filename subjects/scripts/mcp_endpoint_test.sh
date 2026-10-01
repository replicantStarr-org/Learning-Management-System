#!/usr/bin/env bash
# Exercise the backend MCP HTTP endpoints and log each request and response.
#
# Usage:
#   ./scripts/mcp_endpoint_test.sh
#   MCP_LOG_FILE=/tmp/mcp.log ./scripts/mcp_endpoint_test.sh
set -Eeuo pipefail

BACKEND_URL="${MCP_BACKEND_URL:-http://localhost:5001}"
BACKEND_URL="${BACKEND_URL%/}"
CURL_MAX_TIME="${MCP_CURL_MAX_TIME:-10}"
LOG_FILE="${MCP_LOG_FILE:-}"
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
    local url="$BACKEND_URL$path"
    local status

    # Logs go to stderr here so command substitution can return only the HTTP
    # status to the caller.
    log "" >&2
    log ">>> $method $url" >&2

    status="$(curl --silent --show-error --connect-timeout 3 \
        --max-time "$CURL_MAX_TIME" -X "$method" "$@" \
        --output "$response_file" --write-out '%{http_code}' "$url")" \
        || {
            log "<<< request failed" >&2
            return 1
        }

    log "<<< HTTP $status" >&2
    log "$(<"$response_file")" >&2
    printf '%s' "$status"
}

call_html_endpoint() {
    local path="$1" title="$2" response_file="$TMP_DIR/response"
    shift 2
    local -a curl_args=(
        -H 'X-MCP-Mode: on'
    )
    local form_data

    for form_data in "$@"; do
        curl_args+=(--data-urlencode "$form_data")
    done

    local status
    status="$(request POST "$path" "$response_file" "${curl_args[@]}")" || return 1

    [[ "$status" =~ ^2[0-9][0-9]$ ]] || {
        log "FAIL: expected a successful HTTP response"
        return 1
    }
    grep -Fq "<h3>$title</h3>" "$response_file" || {
        log "FAIL: response did not contain title '$title'"
        return 1
    }
    grep -Fq '<pre>' "$response_file" || {
        log "FAIL: response did not contain a JSON payload"
        return 1
    }
}

call_json_endpoint() {
    local path="$1" response_file="$TMP_DIR/response"
    shift

    local status
    status="$(request GET "$path" "$response_file")" || return 1
    [[ "$status" == "200" ]] || {
        log "FAIL: expected HTTP 200"
        return 1
    }
    grep -Fq '"enabled"' "$response_file" || {
        log "FAIL: response did not contain the MCP status JSON"
        return 1
    }
}

# These are the routes declared in backend/routes/mcp.py. The POST routes
# return HTML fragments containing the MCP tool title and formatted JSON.
call_json_endpoint "/mcp/status" || FAILURES=$((FAILURES + 1))
call_json_endpoint "/mcp/mode" || FAILURES=$((FAILURES + 1))

call_html_endpoint "/mcp/query/tag" \
    "MCP Tool: subjects_query_by_tag" \
    "tag=core" || FAILURES=$((FAILURES + 1))
call_html_endpoint "/mcp/subjects/query/tag" \
    "MCP Tool: subjects_query_by_tag" \
    "tag=core" || FAILURES=$((FAILURES + 1))
call_html_endpoint "/mcp/query/field" \
    "MCP Tool: subjects_query_by_field" \
    "field=code" "value=ASD101" || FAILURES=$((FAILURES + 1))
call_html_endpoint "/mcp/subjects/query/field" \
    "MCP Tool: subjects_query_by_field" \
    "field=code" "value=ASD101" || FAILURES=$((FAILURES + 1))

if (( FAILURES > 0 )); then
    log ""
    log "MCP endpoint test failed: $FAILURES endpoint(s) failed."
    exit 1
fi

log ""
log "All MCP endpoint checks passed."
