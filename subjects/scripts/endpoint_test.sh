#!/usr/bin/env bash
# Exercise the subject endpoints end-to-end on a local stack.
# Unlike the CI NFR smoke test, this script requires Ollama for the AI routes.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

FRONTEND="${SUBJECT_FRONTEND_URL:-http://localhost:3001}"
BACKEND="${SUBJECT_BACKEND_URL:-http://localhost:5001}"
DATABASE="${SUBJECT_DATABASE_URL:-http://localhost:6001}"
TIMEOUT="${ENDPOINT_TEST_TIMEOUT:-100}"
TMP_DIR="$(mktemp -d)"
SUBJECT_ID=""
SUMMARY_ID=""

pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

cleanup() {
    set +e
    if [[ -n "$SUBJECT_ID" ]]; then
        curl --silent --output /dev/null --max-time 10 \
            -X DELETE "$DATABASE/subjects/$SUBJECT_ID"
    fi
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

get_status_body() {
    local body="$1" url="$2"
    shift 2
    curl --silent --show-error --connect-timeout 3 --max-time "$TIMEOUT" \
        "$@" --output "$body" --write-out '%{http_code}' "$url"
}

expect_status() {
    local name="$1" url="$2" expected="$3" body="$TMP_DIR/response" actual
    shift 3
    actual="$(get_status_body "$body" "$url" "$@")" \
        || fail "$name: request failed"
    [[ "$actual" == "$expected" ]] \
        || fail "$name: expected HTTP $expected, got ${actual:-000}"
    cat "$body"
}

expect_contains() {
    local name="$1" file="$2" text="$3"
    grep -Fq "$text" "$file" || fail "$name: response did not contain '$text'"
    pass "$name"
}

# Health and frontend page endpoints.
for entry in \
    "frontend home|$FRONTEND/|Subjects" \
    "create page|$FRONTEND/create.html|Create a subject" \
    "edit page|$FRONTEND/edit.html|Edit subject" \
    "subject page|$FRONTEND/subject.html|Subject details"; do
    IFS='|' read -r name url marker <<< "$entry"
    body="$TMP_DIR/${name// /-}"
    status_code="$(get_status_body "$body" "$url")" \
        || fail "$name: request failed"
    [[ "$status_code" == "200" ]] || fail "$name: expected HTTP 200, got $status_code"
    expect_contains "$name" "$body" "$marker"
done
expect_status "backend health" "$BACKEND/" 200 >/dev/null
expect_status "database health" "$DATABASE/" 200 >/dev/null
pass "service health endpoints"

# List subjects and select an existing subject for read/error checks.
list_body="$TMP_DIR/subjects"
expect_status "list subjects" "$BACKEND/subjects" 200 > /dev/null
# expect_status writes to a fixed response file; fetch the list separately so
# later checks can safely overwrite the response file.
get_status_body "$list_body" "$DATABASE/subjects" >/dev/null
REFERENCE_ID="$(jq -r '.[0].subject_id // empty' "$list_body")"
[[ "$REFERENCE_ID" =~ ^[0-9]+$ ]] || fail "subject list did not contain a usable subject ID"
pass "database subject list contains a usable ID"

# Read and not-found endpoints.
detail_body="$TMP_DIR/detail"
expect_status "get subject details" "$BACKEND/subjects/$REFERENCE_ID" 200 > "$detail_body"
expect_contains "subject details contain a code" "$detail_body" 'badge text-bg-primary'
missing_headers="$TMP_DIR/missing-headers"
missing_body="$TMP_DIR/missing"
missing_status="$(get_status_body "$missing_body" "$DATABASE/subjects/999999999" \
    -D "$missing_headers")"
[[ "$missing_status" == "404" ]] || fail "database not-found expected HTTP 404, got $missing_status"
expect_contains "database subject not-found error" "$missing_body" 'Subject not found'

# Validation endpoint.
validation_headers="$TMP_DIR/validation-headers"
validation_body="$TMP_DIR/validation"
validation_status="$(get_status_body "$validation_body" "$BACKEND/subjects" \
    -D "$validation_headers" -X POST --data-urlencode 'code=LOCAL-BAD' \
    --data-urlencode 'name=')"
[[ "$validation_status" == "200" ]] || fail "validation expected the HTMX HTTP 200 error response"
expect_contains "backend validation error" "$validation_headers" 'HX-Error: true'

# Create, read, and update through the public HTML/HTMX backend.
TEST_CODE="LOCAL${EPOCHSECONDS}${RANDOM}"
create_headers="$TMP_DIR/create-headers"
create_body="$TMP_DIR/create"
create_status="$(get_status_body "$create_body" "$BACKEND/subjects" \
    -D "$create_headers" -X POST \
    --data-urlencode "code=$TEST_CODE" \
    --data-urlencode 'name=Local Endpoint Subject' \
    --data-urlencode 'description=Created by the local endpoint test.' \
    --data-urlencode 'semester=Spring' \
    --data-urlencode 'coordinator=Local Tester' \
    --data-urlencode 'status=Open')"
[[ "$create_status" == "201" ]] || fail "create subject expected HTTP 201, got $create_status"
redirect="$(awk 'BEGIN { IGNORECASE=1 } /^HX-Redirect:/ { print $2 }' "$create_headers" \
    | tr -d '\r' | tail -n 1)"
[[ "$redirect" =~ id=([0-9]+) ]] || fail "create response did not contain a subject ID"
SUBJECT_ID="${BASH_REMATCH[1]}"
pass "create subject"

expect_status "read created subject" "$BACKEND/subjects/$SUBJECT_ID" 200 > "$detail_body"
expect_contains "created subject is rendered" "$detail_body" 'Local Endpoint Subject'
expect_status "database read created subject" "$DATABASE/subjects/$SUBJECT_ID" 200 > "$TMP_DIR/db-detail"
expect_contains "created subject is persisted" "$TMP_DIR/db-detail" "$TEST_CODE"

update_headers="$TMP_DIR/update-headers"
update_body="$TMP_DIR/update"
update_status="$(get_status_body "$update_body" "$BACKEND/subjects/update" \
    -D "$update_headers" -X POST \
    --data-urlencode "subject_id=$SUBJECT_ID" \
    --data-urlencode 'name=Updated Local Subject')"
[[ "$update_status" == "200" ]] || fail "update subject expected HTTP 200, got $update_status"
expect_contains "update response contains redirect" "$update_headers" 'HX-Redirect:'
expect_status "read updated subject" "$BACKEND/subjects/$SUBJECT_ID" 200 > "$detail_body"
expect_contains "updated subject is rendered" "$detail_body" 'Updated Local Subject'

# AI summary generation, cache reuse, summary persistence, and question answer.
summary_body="$TMP_DIR/summary"
summary_headers="$TMP_DIR/summary-headers"
summary_status="$(get_status_body "$summary_body" "$BACKEND/subjects/$SUBJECT_ID/summary" \
    -D "$summary_headers" -X POST)"
[[ "$summary_status" == "200" ]] || fail "summary endpoint expected HTTP 200, got $summary_status"
expect_contains "AI summary response" "$summary_body" 'ai-result'
expect_contains "AI summary timestamp" "$summary_body" 'Summary timestamp:'

cached_body="$TMP_DIR/cached-summary"
cached_status="$(get_status_body "$cached_body" "$BACKEND/subjects/$SUBJECT_ID/summary" -X POST)"
[[ "$cached_status" == "200" ]] || fail "cached summary expected HTTP 200, got $cached_status"
expect_contains "fresh summary is reused" "$cached_body" 'Cached summary'

summaries_body="$TMP_DIR/summaries"
summary_list_status="$(get_status_body "$summaries_body" \
    "$DATABASE/subjects/$SUBJECT_ID/summaries")"
[[ "$summary_list_status" == "200" ]] || fail "summary list expected HTTP 200, got $summary_list_status"
SUMMARY_ID="$(jq -r '.[0].summary_id // empty' "$summaries_body")"
[[ "$SUMMARY_ID" =~ ^[0-9]+$ ]] || fail "summary was not persisted in the database"
summary_get_body="$TMP_DIR/summary-get"
summary_get_status="$(get_status_body "$summary_get_body" "$DATABASE/summaries/$SUMMARY_ID")"
[[ "$summary_get_status" == "200" ]] || fail "summary get expected HTTP 200, got $summary_get_status"
expect_contains "stored summary contains AI response" "$summary_get_body" 'ai_response'

question_body="$TMP_DIR/question"
question_status="$(get_status_body "$question_body" "$BACKEND/subjects/questions" \
    -X POST --data-urlencode "subject_id=$SUBJECT_ID" \
    --data-urlencode 'question=What is this subject about?')"
[[ "$question_status" == "200" ]] || fail "question endpoint expected HTTP 200, got $question_status"
expect_contains "AI question response" "$question_body" 'Answer'

# Exercise summary deletion through the JSON API, then subject deletion through
# the public backend.
delete_summary_status="$(get_status_body "$TMP_DIR/delete-summary" \
    "$DATABASE/summaries/$SUMMARY_ID" -X DELETE)"
[[ "$delete_summary_status" == "204" ]] \
    || fail "summary delete expected HTTP 204, got $delete_summary_status"
SUMMARY_ID=""
pass "delete stored summary"

delete_headers="$TMP_DIR/delete-headers"
delete_status="$(get_status_body "$TMP_DIR/delete-subject" "$BACKEND/subjects/delete" \
    -D "$delete_headers" -X POST --data-urlencode "subject_id=$SUBJECT_ID")"
[[ "$delete_status" == "200" ]] || fail "delete subject expected HTTP 200, got $delete_status"
SUBJECT_ID=""
pass "delete subject"

printf '%s\n' 'All local subject endpoint checks passed (including Ollama-backed endpoints).'
