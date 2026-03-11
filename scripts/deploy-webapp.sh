#!/usr/bin/env bash

set -euo pipefail

# Azure Web App Service Deployment Script
# This script deploys the application to Azure Web App Service

# Required environment variables:
# AZURE_SUBSCRIPTION_ID - Azure subscription ID
# AZURE_RESOURCE_GROUP - Azure resource group name
# AZURE_WEBAPP_NAME - Azure Web App Service name
# CONTAINER_REGISTRY_NAME - Azure Container Registry name
# CONTAINER_REGISTRY_URL - Full URL of the container registry (e.g., acr0ct0hub0weu0pas.azurecr.io)
# AZURE_CLIENT_ID - Service principal client ID
# AZURE_CLIENT_SECRET - Service principal client secret
# AZURE_TENANT_ID - Azure tenant ID

if [ -z "${AZURE_SUBSCRIPTION_ID:-}" ] || [ -z "${AZURE_RESOURCE_GROUP:-}" ] || [ -z "${AZURE_WEBAPP_NAME:-}" ]; then
    echo "Error: Required environment variables not set"
    echo "Required: AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, AZURE_WEBAPP_NAME"
    exit 1
fi

VERSION=$(cat ./VERSION)
IMAGE_NAME="${CONTAINER_REGISTRY_NAME}/qa-testgen-interactive-dashboard:${VERSION}"
FULL_IMAGE_URL="${CONTAINER_REGISTRY_URL}/${IMAGE_NAME}"

echo "Deploying to Azure Web App Service..."
echo "Subscription: ${AZURE_SUBSCRIPTION_ID}"
echo "Resource Group: ${AZURE_RESOURCE_GROUP}"
echo "Web App Name: ${AZURE_WEBAPP_NAME}"
echo "Image: ${FULL_IMAGE_URL}"

# Login to Azure
az login --service-principal \
  -u "${AZURE_CLIENT_ID}" \
  -p "${AZURE_CLIENT_SECRET}" \
  --tenant "${AZURE_TENANT_ID}"

# Set subscription
az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

# Configure Web App to use container from registry
az webapp config container set \
  --name "${AZURE_WEBAPP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --docker-custom-image-name "${FULL_IMAGE_URL}" \
  --docker-registry-server-url "https://${CONTAINER_REGISTRY_URL}" \
  --docker-registry-server-user "${AZURE_CLIENT_ID}" \
  --docker-registry-server-password "${AZURE_CLIENT_SECRET}"

# Restart the Web App
az webapp restart \
  --name "${AZURE_WEBAPP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}"

echo "Deployment completed successfully!"
echo "Web App URL: https://${AZURE_WEBAPP_NAME}.azurewebsites.net"

# Logout
az logout
