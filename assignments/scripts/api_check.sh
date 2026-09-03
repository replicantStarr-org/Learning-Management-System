#!/usr/bin/env bash
# Exercises the assignment REST API end to end against a running stack.
# Only the non-AI paths are covered: CI has no Ollama runtime, so the summary
# endpoint is validated locally instead (see assignments/design.md).
set -euo pipefail

BACKEND="${BACKEND_BASE:-http://localhost:5003}"

fail() {
  echo "::error::$1"
  exit 1
}

expect_status() {
  local expected="$1" actual="$2" label="$3"
  [[ "$actual" == "$expected" ]] || fail "$label expected HTTP $expected but got $actual"
  echo "$label -> HTTP $actual"
}

# Read: the seeded catalogue must be there, and filtering must narrow it.
total="$(curl -sf "$BACKEND/assignments" | jq 'length')"
[[ "$total" -ge 10 ]] || fail "Expected at least 10 seeded assignments, found $total"
echo "GET /assignments -> $total records"

filtered="$(curl -sf "$BACKEND/assignments?status=In%20Progress" | jq 'length')"
[[ "$filtered" -le "$total" ]] || fail "Filtered list is larger than the unfiltered list"
echo "GET /assignments?status=In Progress -> $filtered records"

upcoming="$(curl -sf "$BACKEND/assignments/upcoming?days=30" | jq 'length')"
echo "GET /assignments/upcoming?days=30 -> $upcoming records"

# Create.
created="$(curl -sf -X POST "$BACKEND/assignments" \
  -H 'Content-Type: application/json' \
  -d '{"subject_id":1,"subject_name":"ASD101 - Advanced Software Development",
       "title":"CI lifecycle probe","description":"Created by the CI API check.",
       "requirements":"Deleted again before the job finishes.",
       "due_at":"2099-01-01 09:00:00","priority":"Low","weighting":5}')"
new_id="$(jq -r '.assignment_id' <<<"$created")"
[[ "$new_id" =~ ^[0-9]+$ ]] || fail "POST /assignments did not return an assignment_id"
echo "POST /assignments -> id $new_id"

# Read one, and confirm the automatic reminder was scheduled with it.
reminders="$(curl -sf "$BACKEND/assignments/$new_id" | jq '.reminders | length')"
[[ "$reminders" -ge 1 ]] || fail "No reminder was scheduled for the new assignment"
echo "GET /assignments/$new_id -> $reminders reminder(s)"

# Update.
status="$(curl -s -o /dev/null -w '%{http_code}' -X PUT "$BACKEND/assignments/$new_id" \
  -H 'Content-Type: application/json' -d '{"status":"In Progress"}')"
expect_status 200 "$status" "PUT /assignments/$new_id"

# Validation must be enforced at the backend, not only in the browser.
status="$(curl -s -o /dev/null -w '%{http_code}' -X PUT "$BACKEND/assignments/$new_id" \
  -H 'Content-Type: application/json' -d '{"status":"Nonsense"}')"
expect_status 400 "$status" "PUT /assignments/$new_id with an invalid status"

status="$(curl -s -o /dev/null -w '%{http_code}' "$BACKEND/assignments/999999")"
expect_status 404 "$status" "GET /assignments/999999"

# Delete.
status="$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$BACKEND/assignments/$new_id")"
expect_status 200 "$status" "DELETE /assignments/$new_id"

status="$(curl -s -o /dev/null -w '%{http_code}' "$BACKEND/assignments/$new_id")"
expect_status 404 "$status" "GET /assignments/$new_id after deletion"

# The count must be back where it started.
final="$(curl -sf "$BACKEND/assignments" | jq 'length')"
[[ "$final" == "$total" ]] || fail "Expected $total assignments after cleanup, found $final"

echo "Assignment REST API check passed."
