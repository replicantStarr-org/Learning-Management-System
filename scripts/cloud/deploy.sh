#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# validate profile = default or bonus
PROFILE="${PROFILE:-default}"
[[ "$PROFILE" == default || "$PROFILE" == bonus ]] || exit 2
export PROFILE

# ensure the demo resource group has not expired
EXPIRES="$(az group show -n "$RESOURCE_GROUP" --query tags.expiresAt -o tsv)"
if [[ -z "$EXPIRES" ]] || (( $(date -u +%s) >= $(date -u -d "$EXPIRES" +%s) )); then
  echo 'Demo resource group has expired or has no expiry; refusing activation.' >&2
  exit 1
fi

# check if the image manifest exists before proceeding with deployment
[[ -f "$STATE_DIR/images.json" ]] || { echo 'Run build-images.sh first' >&2; exit 1; }

# if deploying the bonus profile, ensure the LLM model account and deployments are ready
if [[ "$PROFILE" == bonus ]]; then bash scripts/cloud/models.sh; fi

# update release information
# with the current profile being deployed
# rather than whatever it was built with
# set builtProfile to retain that information
python3 - "$STATE_DIR/release.json" "$PROFILE" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); release = json.loads(p.read_text())
release.setdefault('builtProfile', release['profile'])
release['profile'] = sys.argv[2]
p.write_text(json.dumps(release, indent=2)+'\n')
PY

# render ACA manifests for the current deployment
python3 scripts/cloud/render.py

# apply the rendered ACA manifests for each service
for name in access subjects resources assignments quizzes timetable; do
  log "Applying $name ($PROFILE)"
  # suppress resource output because it may contain configuration secrets
  if az containerapp show -n "lh-$name" -g "$RESOURCE_GROUP" >/dev/null 2>&1; then
    run_logged az containerapp update -n "lh-$name" -g "$RESOURCE_GROUP" --yaml "$STATE_DIR/manifests/$name.yaml" -o none
  else
    run_logged az containerapp create -n "lh-$name" -g "$RESOURCE_GROUP" --yaml "$STATE_DIR/manifests/$name.yaml" -o none
  fi

  # applying identical config to a stopped app may not create a revision
  # reactivate it explicitly if required
  REVISION="$(az containerapp show -n "lh-$name" -g "$RESOURCE_GROUP" --query properties.latestRevisionName -o tsv)"
  ACTIVE="$(az containerapp revision show -n "lh-$name" -g "$RESOURCE_GROUP" --revision "$REVISION" --query properties.active -o tsv)"
  if [[ "$ACTIVE" != true ]]; then
    az containerapp revision activate -n "lh-$name" -g "$RESOURCE_GROUP" --revision "$REVISION" -o none
  fi
 done

# update the report with the current state of container apps
az containerapp list -g "$RESOURCE_GROUP" --query '[].{name:name,fqdn:properties.configuration.ingress.fqdn,state:properties.provisioningState,profile:tags.profile,release:tags.release}' -o json > "$REPORT_DIR/apps.json"
cp "$STATE_DIR/images.json" "$STATE_DIR/release.json" "$REPORT_DIR/"

# verify the deployment by running the verification script
python3 scripts/cloud/verify.py

log 'Deployment and required verification passed.'
