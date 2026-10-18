#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

PROFILE="${PROFILE:-default}"
[[ "$PROFILE" == default || "$PROFILE" == bonus ]] || exit 2

RELEASE="${RELEASE:-$(git rev-parse --short=12 HEAD)-$(date -u +%Y%m%d%H%M%S)}"
[[ "$RELEASE" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}$ ]] || exit 2
export RELEASE

# login to the Azure Container Registry for docker
az acr login -n "$REGISTRY" -o none

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

# Apply exclusions even when a backend uses a subdirectory as its build context.
# common.sh uses umask 077 for secrets; preserve source modes during extraction
# so nginx workers can still read the staged HTML/assets copied into images.
tar --exclude='.git' --exclude='.cloud' --exclude='reports' --exclude='.venv*' \
  --exclude='__pycache__' --exclude='.env' --exclude='.env.*' --exclude='*.db' \
  --exclude='*.sqlite*' --exclude='*.jsonl' --exclude='chroma' --exclude='content' \
  --exclude='.pytest_cache' --exclude='.ruff_cache' -cf - . | tar --no-same-owner --same-permissions -xf - -C "$STAGING"

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
  python3 - "$MANIFEST" "$key" "$digest" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); data = json.loads(path.read_text()); data[sys.argv[2]] = sys.argv[3]
path.write_text(json.dumps(data, indent=2) + '\n')
PY
}

# build frontend, backend and database images
# for each service listed in services.json
while IFS=$'\t' read -r name directory; do
  build "$name-frontend" "$directory/frontend/Dockerfile" .
  build "$name-backend" "$directory/backend/Dockerfile" "$directory/backend"
  build "$name-database" "$directory/database/Dockerfile" "$directory/database"
done < <(python3 -c 'import json; [print(s["name"]+"\t"+s["directory"]) for s in json.load(open("cloud/services.json"))]')

# build edge / ingress image
# this image proxies to the real frontend
# and adds the HTTP authentication check to nginx
build edge cloud/edge/Dockerfile .

# run a basic test against a running Subjects docker container
# this is not required for the build process or deployment itself
# hence why it is only currently implemented for Subjects rather than all services
SUBJECTS_IMAGE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["subjects-backend"])' "$MANIFEST")"
run_logged docker run --rm -i "$SUBJECTS_IMAGE" python - < scripts/cloud/test-subjects-runtime.py

# build additional images for AI-related services
# if bonus profile is enabled
if [[ "$PROFILE" == bonus ]]; then
  for service in mcp rag-server multi-agent-server; do
    build "$service" cloud/shared/Dockerfile . --build-arg "SERVICE=$service"
  done
fi

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
