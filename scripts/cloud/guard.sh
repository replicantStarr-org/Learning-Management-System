#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# guard to the stop script
# if the set expiry on the resource group has elapsed
# cleanup will be invoked instead
# the expiresAt value is a tag set by the provision script

if ! az group show -n "$RESOURCE_GROUP" >/dev/null 2>&1; then log 'Resource group no longer exists.'; exit 0; fi

EXPIRES="$(az group show -n "$RESOURCE_GROUP" --query tags.expiresAt -o tsv)"
if [[ -z "$EXPIRES" ]]; then echo 'Resource expiry is not set. Refusing indefinite operation' >&2; exit 1; fi

if (( $(date -u +%s) >= $(date -u -d "$EXPIRES" +%s) )); then
  CONFIRM_DELETE="$RESOURCE_GROUP" bash scripts/cloud/cleanup.sh
else
  bash scripts/cloud/stop.sh
fi
