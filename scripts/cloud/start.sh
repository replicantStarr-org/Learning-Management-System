#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# Resume an already deployed release without rebuilding it. Profile stays unchanged.

bash scripts/cloud/check-expiry.sh

UNTIL="$(date -u -d '+1 hour' +%FT%TZ)"
while IFS=$'\t' read -r name id revision; do
  [[ -n "$name" && -n "$revision" ]] || continue
  # renew activeUntil timestamp for the container app
  az tag update --resource-id "$id" --operation Merge --tags activeUntil="$UNTIL" -o none
  az containerapp revision activate -n "$name" -g "$RESOURCE_GROUP" --revision "$revision" -o none
  log "Resumed $name through $UNTIL (existing release/profile)."
done < <(az containerapp list -g "$RESOURCE_GROUP" --query '[].[name,id,properties.latestRevisionName]' -o tsv)
