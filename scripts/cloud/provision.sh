#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# provisions the necessary Azure resources
# this script MUST be idempotent
# it will check if any required resource already exist
# and only create the missing ones

# register necessary Azure providers
# App - required for deploying container apps
# ContainerRegistry - required for storing container images
# ManagedIdentity - required for creating managed identities
for provider in Microsoft.App Microsoft.ContainerRegistry Microsoft.ManagedIdentity; do
  if [[ "$(az provider show --namespace "$provider" --query registrationState -o tsv)" != Registered ]]; then
    if [[ "${GITHUB_ACTIONS:-}" == true ]]; then echo "Bootstrap must register $provider before CI deployment" >&2; exit 1; fi
    az provider register --namespace "$provider" --wait --only-show-errors
  fi
done

# create Azure Resource Group
if ! az group show -n "$RESOURCE_GROUP" >/dev/null 2>&1; then
  EXPIRES="$(date -u -d '+42 days' +%FT%TZ)"
  az group create -n "$RESOURCE_GROUP" -l "$LOCATION" --tags purpose=learning-hub-demo expiresAt="$EXPIRES" -o none
fi

# create Azure Container Registry
if ! az acr show -n "$REGISTRY" -g "$RESOURCE_GROUP" >/dev/null 2>&1; then
  run_logged az acr create -n "$REGISTRY" -g "$RESOURCE_GROUP" -l "$LOCATION" --sku Basic --admin-enabled false --role-assignment-mode rbac -o none
fi

# create managed identity for the runtime
if ! az identity show -n "$RUNTIME_IDENTITY" -g "$RESOURCE_GROUP" >/dev/null 2>&1; then
  az identity create -n "$RUNTIME_IDENTITY" -g "$RESOURCE_GROUP" -l "$LOCATION" -o none
fi
IDENTITY_ID="$(az identity show -n "$RUNTIME_IDENTITY" -g "$RESOURCE_GROUP" --query id -o tsv)"

# assign AcrPull role to the managed identity for the container registry
# this is necessary so that the managed identity can pull images from the container registry
PRINCIPAL="$(az identity show -n "$RUNTIME_IDENTITY" -g "$RESOURCE_GROUP" --query principalId -o tsv)"
REGISTRY_ID="$(az acr show -n "$REGISTRY" --query id -o tsv)"
if [[ -z "$(az role assignment list --assignee "$PRINCIPAL" --scope "$REGISTRY_ID" --role AcrPull --query '[0].id' -o tsv)" ]]; then
  az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal --role AcrPull --scope "$REGISTRY_ID" -o none
fi

# create Container Apps environment
if ! az containerapp env show -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" >/dev/null 2>&1; then
  log 'Creating standard Container Apps environment with Consumption profile only (no dedicated nodes or paid log ingestion).'
  run_logged az containerapp env create -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" -l "$LOCATION" --environment-mode WorkloadProfiles --logs-destination none -o none
fi

# wait for the Container Apps environment to be fully provisioned
ENV_STATE=''
for attempt in $(seq 1 60); do
  ENV_STATE="$(az containerapp env show -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" --query properties.provisioningState -o tsv)"
  [[ "$ENV_STATE" == Succeeded ]] && break
  if [[ "$ENV_STATE" == Failed || "$ENV_STATE" == Canceled ]]; then echo "Environment provisioning failed: $ENV_STATE" >&2; exit 1; fi
  sleep 15
done
[[ "$ENV_STATE" == Succeeded ]] || { echo 'Environment did not become ready within 15 minutes' >&2; exit 1; }
# ensure the environment is using the correct mode
# WorkloadProfiles mode is required to run multiple containers (sidecars) within a single container app
if [[ "$(az containerapp env show -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" --query properties.environmentMode -o tsv)" != WorkloadProfiles ]]; then
  echo 'A standard WorkloadProfiles environment is required: Express does not support sidecars.' >&2
  exit 1
fi

az containerapp env show -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" --query '{id:id,domain:properties.defaultDomain,state:properties.provisioningState}' -o json > "$STATE_DIR/environment.json"
printf '%s' "$IDENTITY_ID" > "$STATE_DIR/runtime-identity"

# write credentials to a local file
# These are runtime credentials, never uploaded as evidence or put in source control.
# if running locally and the credentials do not exist yet, create them on the fly
# if already in the github runner, exit early,
# these credentials must be set locally so they are retrieveable to developers
if [[ ! -f "$STATE_DIR/auth.json" ]]; then
  python3 - "$STATE_DIR/auth.json" <<'PY'
import json, os, secrets, subprocess, sys
if all(os.getenv(k) for k in ('DEMO_PASSWORD', 'DEMO_HTPASSWD', 'JWT_SECRET')):
    credentials = {'username': 'demo', 'password': os.environ['DEMO_PASSWORD'],
                   'htpasswd': os.environ['DEMO_HTPASSWD'], 'jwt': os.environ['JWT_SECRET']}
else:
    if os.getenv('GITHUB_ACTIONS'):
        raise SystemExit('Missing cloud environment secrets; run bootstrap.sh locally first')
    password = secrets.token_urlsafe(32)
    hashed = subprocess.run(['openssl', 'passwd', '-apr1', '-stdin'], input=password, text=True, capture_output=True, check=True).stdout.strip()
    credentials = {'username': 'demo', 'password': password, 'htpasswd': 'demo:' + hashed, 'jwt': secrets.token_urlsafe(64)}
with open(sys.argv[1], 'w') as stream:
    json.dump(credentials, stream)
PY
fi

log "Infrastructure ready. Credentials are in $STATE_DIR/auth.json (private local file; do not publish)."
