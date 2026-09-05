#!/usr/bin/env bash
set -euo pipefail

# Download the latest artifacts for every workflow whose GitHub Actions name
# contains "CI". The script is intentionally rooted at its own directory.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI (gh) is not installed." >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Error: GitHub CLI is not authenticated. Run 'gh auth login'." >&2
  exit 1
fi

reports_dir="$script_dir/reports"
last_download_file="$reports_dir/LAST_DOWNLOAD_TIME"
mkdir -p "$reports_dir"

# Capture this before querying GitHub. It is written only after all downloads,
# so a run that starts while this script is working is picked up next time.
download_started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

gh_checked() {
  local output
  if ! output="$(gh "$@" 2>&1)"; then
    echo "Error: gh command failed: gh $*" >&2
    [[ -n "$output" ]] && printf '%s\n' "$output" >&2
    return 1
  fi
  printf '%s' "$output"
}

parse_epoch() {
  local value="$1"
  local epoch

  if epoch="$(date -d "$value" +%s 2>/dev/null)"; then
    printf '%s' "$epoch"
    return 0
  fi

  # BSD/macOS date fallback for the UTC format written by this script.
  if epoch="$(date -j -f '%Y-%m-%dT%H:%M:%SZ' "$value" +%s 2>/dev/null)"; then
    printf '%s' "$epoch"
    return 0
  fi

  return 1
}

last_download_at=""
if [[ -f "$last_download_file" ]]; then
  IFS= read -r last_download_at < "$last_download_file" || true
  if [[ -n "$last_download_at" ]]; then
    if ! last_download_epoch="$(parse_epoch "$last_download_at")"; then
      echo "Error: reports/LAST_DOWNLOAD_TIME is not a valid timestamp: $last_download_at" >&2
      exit 1
    fi
  fi
fi

latest_run_at="$(gh_checked run list --limit 1 --json updatedAt --jq '.[0].updatedAt // empty')"
if [[ -z "$latest_run_at" ]]; then
  echo "Error: no GitHub Actions runs were found." >&2
  exit 1
fi

if ! latest_run_epoch="$(parse_epoch "$latest_run_at")"; then
  echo "Error: GitHub returned an invalid latest-run timestamp: $latest_run_at" >&2
  exit 1
fi

if [[ -n "$last_download_at" && "$last_download_epoch" -gt "$latest_run_epoch" ]]; then
  echo "Reports are up to date."
  exit 0
fi

workflow_rows="$(gh_checked workflow list --all --json name,path \
  --jq '.[] | select(.name | contains("CI")) | [.name, .path] | @tsv')"

tmp_dirs=()
cleanup() {
  local tmp_dir
  for tmp_dir in "${tmp_dirs[@]}"; do
    [[ -e "$tmp_dir" ]] && rm -rf -- "$tmp_dir"
  done
}
trap cleanup EXIT

while IFS=$'\t' read -r workflow_name workflow_path; do
  [[ -z "${workflow_path:-}" ]] && continue

  workflow_file="${workflow_path##*/}"
  workflow_id="${workflow_file%.*}"
  if [[ -z "$workflow_id" || "$workflow_id" == "$workflow_file" ]]; then
    echo "Error: could not determine a safe reports folder for $workflow_path" >&2
    exit 1
  fi

  run_row="$(gh_checked run list --workflow "$workflow_path" --limit 1 \
    --json databaseId,createdAt --jq '.[0] | [.databaseId, .createdAt] | @tsv')"
  if [[ -z "$run_row" ]]; then
    echo "Error: no run found for workflow '$workflow_name'." >&2
    exit 1
  fi

  IFS=$'\t' read -r run_id run_created_at <<< "$run_row"
  [[ -z "${run_id:-}" ]] && { echo "Error: invalid run returned for '$workflow_name'." >&2; exit 1; }

  target_dir="$reports_dir/$workflow_id"
  tmp_dir="$reports_dir/.${workflow_id}.tmp.$$"
  rm -rf -- "$tmp_dir"
  mkdir -p "$tmp_dir"
  tmp_dirs+=("$tmp_dir")

  echo "Downloading artifacts for $workflow_name (run $run_id)..."
  download_output=""
  download_status=0
  # Capture the status explicitly so a missing-artifacts response can be
  # handled before errexit terminates the script.
  if download_output="$(gh run download "$run_id" --dir "$tmp_dir" 2>&1)"; then
    download_status=0
  else
    download_status=$?
  fi

  if [[ "$download_status" -ne 0 ]]; then
    if [[ "$download_output" =~ [Nn]o[[:space:]]+.*[Aa]rtifacts? ]] || \
       [[ "$download_output" =~ [Aa]rtifacts?[[:space:]]+(not[[:space:]]+found|found[[:space:]]+for) ]] || \
       [[ "$download_output" =~ [Hh][Tt][Tt][Pp].*404 ]]; then
      echo "Warning: no artifacts found for $workflow_name (run $run_id); continuing."
      # Treat a run without artifacts as an empty replacement, so stale files
      # from an older run are not retained.
      rm -rf -- "$tmp_dir"
      mkdir -p "$tmp_dir"
    else
      echo "Error: gh command failed: gh run download $run_id --dir $tmp_dir" >&2
      [[ -n "$download_output" ]] && printf '%s\\n' "$download_output" >&2
      exit 1
    fi
  fi

  # Replace the complete workflow directory, rather than merging into stale
  # contents. This leaves one top-level folder per workflow in reports/.
  rm -rf -- "$target_dir"
  mv -- "$tmp_dir" "$target_dir"
done <<< "$workflow_rows"

last_download_tmp="$reports_dir/.LAST_DOWNLOAD_TIME.tmp.$$"
printf '%s\n' "$download_started_at" > "$last_download_tmp"
mv -- "$last_download_tmp" "$last_download_file"

echo "Reports downloaded successfully."
