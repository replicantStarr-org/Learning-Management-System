#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# status for the azure control plane only
# do not dump application environments or request payloads
az containerapp env show -n "$ENVIRONMENT" -g "$RESOURCE_GROUP" --query '{name:name,mode:properties.environmentMode,profiles:properties.workloadProfiles,state:properties.provisioningState}' -o json > "$REPORT_DIR/environment.json" || true
az acr show -n "$REGISTRY" --query '{name:name,sku:sku.name,adminUserEnabled:adminUserEnabled,roleAssignmentMode:roleAssignmentMode}' -o json > "$REPORT_DIR/registry-security.json" || true
az containerapp list -g "$RESOURCE_GROUP" --query '[].{name:name,fqdn:properties.configuration.ingress.fqdn,state:properties.provisioningState,profile:tags.profile,release:tags.release}' -o json > "$REPORT_DIR/apps.json"
az monitor activity-log list -g "$RESOURCE_GROUP" --offset 1h --query '[].{timestamp:eventTimestamp,operation:operationName.value,status:status.value,resource:resourceId}' -o json > "$REPORT_DIR/azure-operations.json" || true
az containerapp list -g "$RESOURCE_GROUP" --query '[].{name:name,state:properties.provisioningState,revision:properties.latestRevisionName,ingress:properties.configuration.ingress,scale:properties.template.scale,containers:properties.template.containers[].{name:name,image:image,resources:resources}}' -o json > "$REPORT_DIR/deployed-configuration.json"

# collect system logs for each container app
for name in access subjects resources assignments quizzes timetable; do
  az containerapp logs show -n "lh-$name" -g "$RESOURCE_GROUP" --type system --tail 50 --format json > "$REPORT_DIR/$name-system.log" 2>&1 || true
done

# create a deployment summary in markdown format
python3 - "$REPORT_DIR" <<'PY'
import json, os, sys
from pathlib import Path
p = Path(sys.argv[1])
release = json.loads((p/'release.json').read_text()) if (p/'release.json').exists() else {
    'commit': os.getenv('GITHUB_SHA', 'unknown'), 'release': os.getenv('RELEASE', 'unknown'),
    'profile': os.getenv('PROFILE', 'unknown'), 'dirty': False if os.getenv('GITHUB_ACTIONS') else 'unknown'}
apps = json.loads((p/'apps.json').read_text()) if (p/'apps.json').exists() else []
lines = ['# Azure Container Apps deployment', '', f'- Commit: `{release.get("commit", "unknown")}`',
         f'- Release: `{release.get("release", "unknown")}`', f'- Profile: `{release.get("profile", "unknown")}`',
         f'- Uncommitted source changes: `{release.get("dirty", "unknown")}`',
         ('- Workflow: ' + os.environ['GITHUB_SERVER_URL'] + '/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'])
         if os.getenv('GITHUB_RUN_ID') else '- Execution: local Azure CLI (not GitHub Actions)',
         '', '## Frontends', '']
lines += [f'- {a["name"]}: https://{a["fqdn"]} ({a["state"]})' for a in apps]
lines += ['', '## Evidence', '', 'See deployment.log, cloud-verification.json, deployed-configuration.json, and *-system.log.']
(p/'deployment-summary.md').write_text('\n'.join(lines)+'\n')
PY
