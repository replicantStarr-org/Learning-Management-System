#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

FORCE="${FORCE:-false}"
export FORCE

# all stopped revisions must be in-active
# by default activeUntil is set for an hour in the future on deployment
az containerapp list -g "$RESOURCE_GROUP" --query '[].{name:name,until:tags.activeUntil}' -o json > "$STATE_DIR/stop-targets.json"
while read -r name; do
  [[ -n "$name" ]] || continue
  while read -r revision; do
    [[ -n "$revision" ]] || continue
    log "Deactivating $revision"
    az containerapp revision deactivate -n "$name" -g "$RESOURCE_GROUP" --revision "$revision" -o none
  done < <(az containerapp revision list -n "$name" -g "$RESOURCE_GROUP" --query '[?properties.active].name' -o tsv)

  # only stop revisions where activeUntil is in the past
  # or stop all if FORCE is set to true
done < <(python3 - "$STATE_DIR/stop-targets.json" <<'PY'
import json, os, sys
from datetime import datetime, timezone
for item in json.load(open(sys.argv[1])):
    if os.getenv('FORCE') == 'true' or not item['until'] or datetime.fromisoformat(item['until'].replace('Z','+00:00')) <= datetime.now(timezone.utc):
        print(item['name'])
PY
)
