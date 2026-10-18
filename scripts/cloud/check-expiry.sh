#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# Exit codes: 0 = unexpired, 1 = expired, 2 = missing/invalid expiry or lookup failure
# keep any errors distinct from expiry so guard script never deletes resources on a failed check

if ! EXPIRES="$(az group show -n "$RESOURCE_GROUP" --query tags.expiresAt -o tsv)"; then
  echo 'Unable to read resource group expiry.' >&2
  exit 2
fi

if [[ -z "$EXPIRES" ]]; then
  echo 'Resource group expiresAt tag is missing; refusing operation.' >&2
  exit 2
fi

if ! EXPIRES_EPOCH="$(date -u -d "$EXPIRES" +%s 2>/dev/null)"; then
  printf 'Invalid resource group expiresAt tag: %s; refusing operation.\n' "$EXPIRES" >&2
  exit 2
fi

if ! NOW_EPOCH="$(date -u +%s)"; then
  echo 'Unable to determine current time; refusing operation.' >&2
  exit 2
fi

if (( NOW_EPOCH >= EXPIRES_EPOCH )); then
  printf 'Resource group expired at %s.\n' "$EXPIRES" >&2
  exit 1
fi

exit 0
