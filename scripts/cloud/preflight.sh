#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# check for required commands and tools
for cmd in az docker python3 openssl; do command -v "$cmd" >/dev/null; done
python3 -c 'import yaml, requests'
docker info >/dev/null
az extension show --name containerapp >/dev/null

# make sure spending limit is enabled
# so we don't have to pay out of pocket
SPENDING_LIMIT="$(az rest --method get --url "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID?api-version=2022-12-01" --query subscriptionPolicies.spendingLimit -o tsv)"
if [[ "$SPENDING_LIMIT" != On && "${ALLOW_PAID_SUBSCRIPTION:-false}" != true ]]; then
  echo 'Subscription spending limit is not On. Set ALLOW_PAID_SUBSCRIPTION=true only after cost approval.' >&2
  exit 1
fi

# validat profile = default or bonus
PROFILE="${PROFILE:-default}"
[[ "$PROFILE" == default || "$PROFILE" == bonus ]] || { echo 'PROFILE must be default or bonus' >&2; exit 1; }

# location should be australiaeast by default
[[ "$LOCATION" == australiaeast ]] || log "Using explicitly configured region $LOCATION"

# output account and quota information
az account show --query '{subscription:name,id:id,state:state}' -o json > "$REPORT_DIR/account.json"
az containerapp list-usages --location "$LOCATION" -o json > "$REPORT_DIR/quota.json"

log "Preflight passed with profile=$PROFILE region=$LOCATION."
