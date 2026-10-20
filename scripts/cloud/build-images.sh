#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

PROFILE="${PROFILE:-default}"
[[ "$PROFILE" == default || "$PROFILE" == bonus ]] || exit 2

RELEASE="${RELEASE:-$(git rev-parse --short=12 HEAD)-$(date -u +%Y%m%d%H%M%S)}"
[[ "$RELEASE" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$ ]] || exit 2
export RELEASE

# Limit simultaneous builds to avoid exhausting Docker's memory/CPU.
BUILD_JOBS="${BUILD_JOBS:-6}"
[[ "$BUILD_JOBS" =~ ^[1-9][0-9]{0,2}$ ]] || { echo 'BUILD_JOBS must be an integer from 1 to 999' >&2; exit 2; }

# login to the Azure Container Registry for docker
az acr login -n "$REGISTRY" -o none

STAGING="$(mktemp -d)"
DIGEST_DIR="$STAGING.digests"
# Let any outstanding builds finish before removing their build contexts.
trap 'wait; rm -rf "$STAGING" "$DIGEST_DIR"' EXIT
mkdir -p "$DIGEST_DIR"

# Apply exclusions even when a backend uses a subdirectory as its build context.
# common.sh uses umask 077 for secrets; preserve source modes during extraction
# so nginx workers can still read the staged HTML/assets copied into images.
tar --exclude='.git' --exclude='.cloud' --exclude='reports' --exclude='.venv*' \
  --exclude='__pycache__' --exclude='.env' --exclude='.env.*' --exclude='*.db' \
  --exclude='*.sqlite*' --exclude='*.jsonl' --exclude='chroma' --exclude='content' \
  --exclude='.pytest_cache' --exclude='.ruff_cache' -cf - . | tar --no-same-owner --same-permissions -xf - -C "$STAGING"

# Restore only version-controlled seed PDFs, never developer uploads. The broad
# content exclusion above still applies to every other file and service.
git ls-files -z -- 'learning-resource-manager/content/pdf/*.pdf' |
  tar --null -T - -cf - | tar --no-same-owner --same-permissions -xf - -C "$STAGING"

MANIFEST="$STATE_DIR/images.json"
printf '{}\n' > "$MANIFEST"

SERVER="$(az acr show -n "$REGISTRY" --query loginServer -o tsv)"
build() {
  local key="$1" dockerfile="$2" context="$3"; shift 3
  local image="$SERVER/$key:$RELEASE"
  log "Building $key"

  # build and push the Docker image
  run_logged docker build --platform linux/amd64 --file "$STAGING/$dockerfile" --tag "$image" "$@" "$STAGING/$context"
  run_logged docker push "$image"

  local digest
  digest="$(docker image inspect "$image" --format '{{index .RepoDigests 0}}')"

  # record the image digest (image ID) in the manifest
  # the manifest is used to find the corresponding images
  # during the deployment (see deploy.sh)
  # Each build writes its own file; merge only after all builds succeed.
  printf '%s\n' "$digest" > "$DIGEST_DIR/$key"
}

BUILD_PIDS=()
wait_for_builds() {
  local pid failed=0
  for pid in "${BUILD_PIDS[@]}"; do
    if ! wait "$pid"; then
      failed=1
    fi
  done
  BUILD_PIDS=()
  if (( failed )); then
    log 'Image build/push failed; release will not be published.'
    return 1
  fi
}

queue_build() {
  build "$@" &
  BUILD_PIDS+=("$!")
  # Use bounded batches, compatible with Bash versions without wait -n.
  if (( ${#BUILD_PIDS[@]} >= BUILD_JOBS )); then
    wait_for_builds
  fi
}

# build frontend, backend and database images
# for each service listed in services.json
while IFS=$'\t' read -r name directory; do
  queue_build "$name-frontend" "$directory/frontend/Dockerfile" .
  queue_build "$name-backend" "$directory/backend/Dockerfile" "$directory/backend"
  queue_build "$name-database" "$directory/database/Dockerfile" "$directory/database"
done < <(python3 -c 'import json; [print(s["name"]+"\t"+s["directory"]) for s in json.load(open("cloud/services.json"))]')

# build edge / ingress image
# this image proxies to the real frontend
# and adds the HTTP authentication check to nginx
queue_build edge cloud/edge/Dockerfile .

# build additional images for AI-related services
if [[ "$PROFILE" == bonus ]]; then
  for service in mcp rag-server multi-agent-server; do
    queue_build "$service" cloud/shared/Dockerfile . --build-arg "SERVICE=$service"
  done
fi

# wait for all builds to end before creating the image manifest
wait_for_builds

python3 - "$MANIFEST" "$DIGEST_DIR" <<'PY'
import json, sys
from pathlib import Path
images = {path.name: path.read_text().strip() for path in sorted(Path(sys.argv[2]).iterdir())}
Path(sys.argv[1]).write_text(json.dumps(images, indent=2) + '\n')
PY

# run a basic test against a running Subjects docker container
# this is not required for the build process or deployment itself
# hence why it is only currently implemented for Subjects rather than all services
SUBJECTS_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["subjects-backend"])' "$MANIFEST")"
run_logged docker run --rm -i "$SUBJECTS_IMAGE" python - < scripts/cloud/test-subjects-runtime.py

# generate the release information file
# used for a tag in the container app manifests
python3 - "$STATE_DIR/release.json" "$PROFILE" "$RELEASE" "$(git rev-parse HEAD)" <<'PY'
import json, subprocess, sys
from pathlib import Path
json.dump({'profile': sys.argv[2], 'builtProfile': sys.argv[2], 'release': sys.argv[3], 'commit': sys.argv[4],
           'dirty': bool(subprocess.check_output(['git','status','--porcelain']).strip())}, open(sys.argv[1], 'w'), indent=2)
PY

# copy the built images manifest and release information to the report directory
cp "$STATE_DIR/images.json" "$STATE_DIR/release.json" "$REPORT_DIR/"

log "Published $RELEASE using immutable image digests."
