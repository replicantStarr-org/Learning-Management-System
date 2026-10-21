#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# validate profile = default or bonus
PROFILE="${PROFILE:-default}"
[[ "$PROFILE" == default || "$PROFILE" == bonus ]] || exit 2
export PROFILE

# ensure the demo resource group has not expired
bash scripts/cloud/check-expiry.sh

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
  # Retry only the observed identity-resolution failure. Recheck existence because
  # a rejected write may still leave an app resource behind.
  for attempt in 1 2 3 4; do
    operation=create
    if az containerapp show -n "lh-$name" -g "$RESOURCE_GROUP" >/dev/null 2>&1; then
      operation=update
    fi
    log "Applying $name: $operation attempt $attempt/4"
    # Suppress resource output because it may contain configuration secrets.
    if output="$(az containerapp "$operation" -n "lh-$name" -g "$RESOURCE_GROUP" --yaml "$STATE_DIR/manifests/$name.yaml" -o none 2>&1)"; then
      [[ -z "$output" ]] || printf '%s\n' "$output" | tee -a "$REPORT_DIR/deployment.log"
      break
    else
      status=$?
      printf '%s\n' "$output" | tee -a "$REPORT_DIR/deployment.log"
    fi
    if [[ "$output" != *IdentityDoesNotExist* || "$output" != *NotFound* ||
          "$output" != *"/providers/Microsoft.App/containerApps/lh-$name"* ]]; then
      log "Deployment failed for $name; error is not retryable"
      exit "$status"
    fi
    if (( attempt == 4 )); then
      log "Deployment failed for $name after 4 attempts"
      exit "$status"
    fi
    delay=$((15 * 2 ** (attempt - 1)))
    log "Transient identity-resolution failure for $name; retrying in ${delay}s"
    sleep "$delay"
  done

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
