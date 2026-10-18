#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# ensure the model account exists and is ready for deployments
if ! az cognitiveservices account show -n "$MODEL_ACCOUNT" -g "$RESOURCE_GROUP" >/dev/null 2>&1; then
  run_logged az cognitiveservices account create -n "$MODEL_ACCOUNT" -g "$RESOURCE_GROUP" -l "$LOCATION" --kind OpenAI --sku S0 --custom-domain "$MODEL_ACCOUNT" -o none
fi

# create primary and reviewer deployments for the model account
# this is safe to run multiple times. it will update existing deployments if necessary
for deployment in primary reviewer; do
  run_logged az cognitiveservices account deployment create -n "$MODEL_ACCOUNT" -g "$RESOURCE_GROUP" \
    --deployment-name "$deployment" --model-name gpt-4.1-mini --model-version 2025-04-14 \
    --model-format OpenAI --sku-name GlobalStandard --sku-capacity 10 -o none
done

# Write endpoint and inference key directly to a restricted private file; never expose a key in shell tracing or evidence.
az cognitiveservices account keys list -n "$MODEL_ACCOUNT" -g "$RESOURCE_GROUP" --query key1 -o tsv > "$STATE_DIR/model-key"
az cognitiveservices account show -n "$MODEL_ACCOUNT" -g "$RESOURCE_GROUP" --query properties.endpoint -o tsv > "$STATE_DIR/model-endpoint"

# Generate a JSON file containing the model endpoint and key, then remove the key file for security.
python3 - "$STATE_DIR" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
json.dump({'endpoint': (p/'model-endpoint').read_text().strip().rstrip('/')+'/openai/v1/',
           'key': (p/'model-key').read_text().strip()}, open(p/'models.json','w'))
(p/'model-key').unlink()
PY

# output the list of model deployments to the report directory
az cognitiveservices account deployment list -n "$MODEL_ACCOUNT" -g "$RESOURCE_GROUP" --query '[].{name:name,model:properties.model.name,version:properties.model.version,sku:sku.name,capacity:sku.capacity}' -o json > "$REPORT_DIR/models.json"

log 'Two usage-based model deployments ready (same economical model, separate primary/reviewer roles).'
