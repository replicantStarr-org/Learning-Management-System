#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

if [[ "${CONFIRM_DELETE:-}" != "$RESOURCE_GROUP" ]]; then
  echo "Permanent deletion includes all demo data and model deployments. Set CONFIRM_DELETE=$RESOURCE_GROUP to confirm." >&2
  exit 1
fi

az group delete -n "$RESOURCE_GROUP" --yes --no-wait
log 'Deletion requested. You can verify completion and remaining subscription charges in Azure.'
