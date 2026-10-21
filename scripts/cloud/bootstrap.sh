#!/usr/bin/env bash

source "$(dirname "$0")/common.sh"

# One-time local privileged setup. Ordinary CI does not receive role-assignment rights.

# check gh is installed and authenticated
command -v gh >/dev/null
gh auth status >/dev/null

# provision the cloud infrastructure first
# this will also generate local secrets
# if they do not already exist
bash scripts/cloud/provision.sh

# create identity for the deployment
az identity create -n "$DEPLOY_IDENTITY" -g "$RESOURCE_GROUP" -l "$LOCATION" -o none
CLIENT_ID="$(az identity show -n "$DEPLOY_IDENTITY" -g "$RESOURCE_GROUP" --query clientId -o tsv)"
PRINCIPAL="$(az identity show -n "$DEPLOY_IDENTITY" -g "$RESOURCE_GROUP" --query principalId -o tsv)"
GROUP_ID="$(az group show -n "$RESOURCE_GROUP" --query id -o tsv)"
REGISTRY_ID="$(az acr show -n "$REGISTRY" --query id -o tsv)"

# Assign necessary roles to the deployment identity
for role in Contributor AcrPush; do
  SCOPE="$GROUP_ID"; [[ "$role" == AcrPush ]] && SCOPE="$REGISTRY_ID"
  if [[ -z "$(az role assignment list --assignee "$PRINCIPAL" --role "$role" --scope "$SCOPE" --query '[0].id' -o tsv)" ]]; then
    az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal --role "$role" --scope "$SCOPE" -o none
  fi
done

# Environment-scoped OIDC. If a repository customizes its subject, set OIDC_SUBJECT explicitly.
# allows GitHub Actions to authenticate using OIDC to Azure
REPO="${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"
ENV_NAME=cloud
OIDC_PREFIX="$(gh api "repos/$REPO/actions/oidc/customization/sub" --jq '.sub_claim_prefix // empty')"
SUBJECT="${OIDC_SUBJECT:-${OIDC_PREFIX:-repo:$REPO}:environment:$ENV_NAME}"
az identity federated-credential create -n github-cloud --identity-name "$DEPLOY_IDENTITY" -g "$RESOURCE_GROUP" \
  --issuer https://token.actions.githubusercontent.com --subject "$SUBJECT" --audiences api://AzureADTokenExchange -o none

# Permit main and the current implementation branch (remove the latter after merge)
# to deploy to the newly created GitHub 'cloud' environment
printf '%s' '{"deployment_branch_policy":{"protected_branches":false,"custom_branch_policies":true}}' > "$STATE_DIR/github-environment.json"
gh api --method PUT "repos/$REPO/environments/$ENV_NAME" --input "$STATE_DIR/github-environment.json" >/dev/null
for branch in "$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)" "$(git branch --show-current)"; do
  EXISTS="$(gh api "repos/$REPO/environments/$ENV_NAME/deployment-branch-policies" --jq ".branch_policies[] | select(.name == \"$branch\") | .id")"
  if [[ -z "$EXISTS" ]]; then gh api --method POST "repos/$REPO/environments/$ENV_NAME/deployment-branch-policies" -f name="$branch" -f type=branch >/dev/null; fi
done

# Add GitHub environment variables and secrets for the cloud environment
gh variable set AZURE_CLIENT_ID --repo "$REPO" --env "$ENV_NAME" --body "$CLIENT_ID"
gh variable set AZURE_TENANT_ID --repo "$REPO" --env "$ENV_NAME" --body "$(az account show --query tenantId -o tsv)"
gh variable set AZURE_SUBSCRIPTION_ID --repo "$REPO" --env "$ENV_NAME" --body "$SUBSCRIPTION_ID"
gh variable set RESOURCE_GROUP --repo "$REPO" --env "$ENV_NAME" --body "$RESOURCE_GROUP"
for mapping in 'DEMO_PASSWORD password' 'DEMO_HTPASSWD htpasswd' 'JWT_SECRET jwt'; do  # pragma: allowlist secret
  read -r secret key <<< "$mapping"
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]], end="")' "$STATE_DIR/auth.json" "$key" | gh secret set "$secret" --repo "$REPO" --env "$ENV_NAME"
done
log "GitHub cloud environment configured. OIDC subject: $SUBJECT. No Azure client secret or registry password stored."
