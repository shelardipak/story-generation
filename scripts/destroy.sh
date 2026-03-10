#!/usr/bin/env bash

set -euo pipefail

source scripts/constants.sh

source scripts/helpers/get_project_deploy_token.sh

# shellcheck source=/dev/null
source .config/.env

get_project_deploy_token \
  "${AZURE_CLIENT_ID}" \
  "${AZURE_CLIENT_SECRET}" \
  "${AZURE_SUBSCRIPTION_ID}" \
  "${AZURE_TENANT_ID}" \
  "${ENVIRONMENT}" \
  "${SHORT_LOCATION}" \
  "${PROJECT_NAME}"

oc login \
  --token "${project_deploy_token}" \
  --server "https://api.app-services.${ENVIRONMENT}-${SHORT_LOCATION}.cust.az.mandg.com:6443"

helm uninstall "${SERVICE}" src/helm \
  --namespace "${PROJECT_NAME}" \
  --wait \
  --dry-run

oc logout
