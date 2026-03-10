#!/usr/bin/env bash

set -euo pipefail
source scripts/constants.sh

source scripts/helpers/get_project_deploy_token.sh
source scripts/helpers/push_image_to_cluster.sh
source scripts/helpers/write_values_file.sh

# shellcheck source=/dev/null
#source .config/.env

push_image_to_cluster \
  "${AZURE_CLIENT_ID}" \
  "${AZURE_CLIENT_SECRET}" \
  "${AZURE_SUBSCRIPTION_ID}" \
  "${AZURE_TENANT_ID}" \
  "${ENVIRONMENT}" \
  "${SHORT_LOCATION}" \
  "${PROJECT_NAME}" \
  "${CONTAINER_REGISTRY_NAME}" \
  "${ADO_PROJECT_NAME}/${SERVICE_NAME}:${VERSION}" \
  "${PROJECT_NAME}/${SERVICE_NAME}:${VERSION}"

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

write_values_file \
  "${PROJECT_NAME}" \
  "${SERVICE_NAME}" \
  "${VERSION}" \
  "${REPLICA_COUNT}" \

helm upgrade "${SERVICE_NAME}" src/helm \
  --namespace "${PROJECT_NAME}" \
  --values "${values_file_path}" \
  --install \
  --wait

oc logout
