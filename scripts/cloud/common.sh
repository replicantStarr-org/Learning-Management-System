#!/usr/bin/env bash

# Sets up the common environment variables and directories for the cloud deployment.
# Also defines some common functions
# Source this file; never enable shell tracing while handling credentials.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
RESOURCE_GROUP="${RESOURCE_GROUP:-learning-hub-demo}"
LOCATION="${LOCATION:-australiaeast}"
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}"
[[ "$RESOURCE_GROUP" =~ ^[a-zA-Z0-9-]{1,50}$ ]] || { echo 'Invalid resource group' >&2; exit 1; }
SUFFIX="$(printf '%s' "$SUBSCRIPTION_ID/$RESOURCE_GROUP" | sha256sum | cut -c1-10)"
REGISTRY="lh${SUFFIX}"
ENVIRONMENT="${ENVIRONMENT:-lh-demo}"
RUNTIME_IDENTITY="lh-runtime"
DEPLOY_IDENTITY="lh-github"
MODEL_ACCOUNT="lh-model-${SUFFIX}"
STATE_DIR="${STATE_DIR:-$ROOT/.cloud}"
REPORT_DIR="${REPORT_DIR:-$ROOT/reports/cloud/local}"
umask 077
mkdir -p "$STATE_DIR" "$REPORT_DIR"
az account set --subscription "$SUBSCRIPTION_ID"
export RESOURCE_GROUP LOCATION SUBSCRIPTION_ID REGISTRY ENVIRONMENT STATE_DIR REPORT_DIR MODEL_ACCOUNT
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$REPORT_DIR/deployment.log"; }
# The native command must remain the pipeline's exit status. Never tee raw secrets/manifests.
run_logged() { "$@" 2>&1 | tee -a "$REPORT_DIR/deployment.log"; }
