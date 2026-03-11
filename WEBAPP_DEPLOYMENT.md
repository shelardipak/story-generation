# Azure Web App Service Deployment Guide

This guide explains how to deploy the QA Test Generation Dashboard to Azure Web App Service.

## Prerequisites

1. Azure subscription with access to:
   - Azure Container Registry (ACR)
   - Azure Web App Service
   - Azure CLI installed locally

2. Service Principal credentials with permissions to:
   - Push images to ACR
   - Configure Web App Service

## Phase 1: Minimal Setup (Current)

### Changes Made

1. **Port Configuration** (`src/run.sh`)
   - Changed from port 8501 → 80 (Web App standard)
   - Enabled CORS for cross-domain requests

2. **Docker Image** (`src/Dockerfile`)
   - Simplified base image: `python:3.9-slim` (instead of PowerShell)
   - Updated EXPOSE to port 80
   - Removed unnecessary dependencies

3. **Deployment Scripts**
   - Created `scripts/deploy-webapp.sh` for manual deployment
   - Created `azure-pipelines.webapp.yml` for CI/CD pipeline

### Manual Deployment Steps

#### Step 1: Build and Push Docker Image

```bash
# Login to Azure Container Registry
az acr login --name acr0ct0hub0weu0pas

# Build the image
docker build -t acr0ct0hub0weu0pas.azurecr.io/qa-testgen-interactive-dashboard:latest src/

# Push to ACR
docker push acr0ct0hub0weu0pas.azurecr.io/qa-testgen-interactive-dashboard:latest
```

#### Step 2: Create Web App Service (if not exists)

```bash
# Set variables
RESOURCE_GROUP="rg-qa-testgen"
WEBAPP_NAME="qa-testgen-dashboard"
LOCATION="westeurope"
ACR_NAME="acr0ct0hub0weu0pas"

# Create resource group
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION"

# Create App Service Plan
az appservice plan create \
  --name "plan-qa-testgen" \
  --resource-group "$RESOURCE_GROUP" \
  --sku B2 \
  --is-linux

# Create Web App with container
az webapp create \
  --resource-group "$RESOURCE_GROUP" \
  --plan "plan-qa-testgen" \
  --name "$WEBAPP_NAME" \
  --deployment-container-image-name "$ACR_NAME.azurecr.io/qa-testgen-interactive-dashboard:latest"
```

#### Step 3: Configure Container Registry Access

```bash
# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name acr0ct0hub0weu0pas --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name acr0ct0hub0weu0pas --query passwords[0].value -o tsv)

# Configure Web App to pull from ACR
az webapp config container set \
  --name "$WEBAPP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --docker-custom-image-name "acr0ct0hub0weu0pas.azurecr.io/qa-testgen-interactive-dashboard:latest" \
  --docker-registry-server-url "https://acr0ct0hub0weu0pas.azurecr.io" \
  --docker-registry-server-user "$ACR_USERNAME" \
  --docker-registry-server-password "$ACR_PASSWORD"
```

#### Step 4: Configure Application Settings

```bash
# Set environment variables required by the app
az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --settings \
    INT_DASHBOARD_CLIENT_ID="<your-client-id>" \
    INT_DASHBOARD_TENANT_ID="<your-tenant-id>" \
    INT_DASHBOARD_CLIENT_SECRET="<your-client-secret>" \
    REDIRECT_URI="https://$WEBAPP_NAME.azurewebsites.net/" \
    JIRA_URL="<your-jira-url>" \
    JIRA_USERNAME="<your-jira-username>" \
    JIRA_API_TOKEN="<your-jira-api-token>"
```

#### Step 5: Restart Web App

```bash
az webapp restart \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME"
```

#### Step 6: Access Your App

```
https://qa-testgen-dashboard.azurewebsites.net
```

### Using the Deployment Script

Alternatively, use the provided script:

```bash
chmod +x scripts/deploy-webapp.sh

export AZURE_SUBSCRIPTION_ID="<your-subscription-id>"
export AZURE_RESOURCE_GROUP="rg-qa-testgen"
export AZURE_WEBAPP_NAME="qa-testgen-dashboard"
export CONTAINER_REGISTRY_NAME="acr0ct0hub0weu0pas"
export CONTAINER_REGISTRY_URL="acr0ct0hub0weu0pas.azurecr.io"
export AZURE_CLIENT_ID="<your-client-id>"
export AZURE_CLIENT_SECRET="<your-client-secret>"
export AZURE_TENANT_ID="<your-tenant-id>"

scripts/deploy-webapp.sh
```

## CI/CD Pipeline Setup

### Using Azure Pipelines

1. Update your Azure Pipelines configuration to use `azure-pipelines.webapp.yml`
2. Configure the following service connections in Azure DevOps:
   - `AzureContainerRegistry` - for pushing images to ACR
   - `AzureServiceConnection` - for deploying to Web App

3. Set pipeline variables:
   - `registryUsername` - ACR username
   - `registryPassword` - ACR password

## Important Notes

### Azure AD Redirect URI
After deployment, update your Azure AD app registration:
1. Go to Azure Portal → Azure AD → App registrations
2. Find your app (INT_DASHBOARD_CLIENT_ID)
3. Add redirect URI: `https://qa-testgen-dashboard.azurewebsites.net/`

### Environment Variables
All environment variables from OpenShift deployment should be set in Web App Application Settings:
- `INT_DASHBOARD_CLIENT_ID`
- `INT_DASHBOARD_TENANT_ID`
- `INT_DASHBOARD_CLIENT_SECRET`
- `REDIRECT_URI`
- Jira credentials
- Any other required variables

### Logging
Logs are available in:
- Azure Portal → Web App → Log stream
- Or via CLI: `az webapp log tail --resource-group <rg> --name <webapp-name>`

### Troubleshooting

**App not starting?**
```bash
# Check logs
az webapp log tail --resource-group rg-qa-testgen --name qa-testgen-dashboard

# Check container status
az webapp show --resource-group rg-qa-testgen --name qa-testgen-dashboard --query state
```

**Port issues?**
- Web App Service automatically maps port 80 to HTTP
- Streamlit is configured to listen on port 80 in `src/run.sh`

**CORS issues?**
- CORS is enabled in `src/run.sh`
- Configure additional CORS settings in Web App if needed

## Next Steps (Phase 2)

When ready, implement:
1. Azure Key Vault integration for secrets
2. Application Insights for logging
3. Health checks and monitoring
4. Consider converting to FastAPI for better API support

## Support

For issues or questions, refer to:
- [Azure Web App Documentation](https://docs.microsoft.com/en-us/azure/app-service/)
- [Streamlit Deployment Guide](https://docs.streamlit.io/knowledge-base/tutorials/deploy)
