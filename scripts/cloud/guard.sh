#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# guard to the stop script
# if the set expiry on the resource group has elapsed
# cleanup will be invoked instead
# the expiresAt value is a tag set by the provision script

if ! az group show -n "$RESOURCE_GROUP" >/dev/null 2>&1; then log 'Resource group no longer exists.'; exit 0; fi

if bash scripts/cloud/check-expiry.sh; then
  bash scripts/cloud/stop.sh
else
  STATUS=$?
  if [[ "$STATUS" -eq 1 ]]; then
    CONFIRM_DELETE="$RESOURCE_GROUP" bash scripts/cloud/cleanup.sh
  else
    exit "$STATUS"
  fi
fi
