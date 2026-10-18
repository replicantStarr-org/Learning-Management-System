#!/bin/sh
# Runs when the nginx container starts. The pages ship with the local development
# addresses; this script swaps in the deployed addresses from the environment.
# With no variable set it changes nothing, so local use is unaffected.
set -eu

root="${PAGE_ROOT:-/usr/share/nginx/html}"

replace() {
    local_url="$1"
    new_url="$2"
    [ -n "$new_url" ] || return 0
    escaped=$(printf '%s' "$new_url" | sed 's/[&|\]/\&/g')
    find "$root" -maxdepth 1 \( -name '*.html' -o -name '*.js' \) -exec sed -i "s|$local_url|$escaped|g" {} +
    echo "set-public-urls: $local_url -> $new_url"
}

replace "http://localhost:5004" "${QUIZ_BACKEND_URL:-}"
replace "http://localhost:3000" "${HOME_URL:-}"
replace "http://localhost:3001" "${SUBJECTS_URL:-}"
replace "http://localhost:3002" "${RESOURCES_URL:-}"
replace "http://localhost:3003" "${ASSIGNMENTS_URL:-}"
replace "http://localhost:3005" "${TIMETABLE_URL:-}"
