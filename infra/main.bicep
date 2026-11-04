targetScope = 'subscription'

@description('AZD environment name.')
@minLength(3)
@maxLength(20)
param environmentName string

@description('Primary Azure location.')
param location string

@description('Bearer token required by protected API routes.')
@secure()
param apiBearerToken string

@description('Existing Microsoft Foundry account name.')
param foundryResourceName string = 'brk445demo-01'

@description('Resource group containing the existing Foundry account.')
param foundryResourceGroupName string = 'rg-brk445demo'

@description('Existing GPT deployment name.')
param foundryDeploymentName string = 'gpt-6-1-terra'

var resourceGroupName = 'rg-${environmentName}'
var tags = {
  'azd-env-name': environmentName
  application: 'visual-product-guide'
  environment: environmentName
}

resource rg 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: resourceGroupName
  location: location
  tags: {
    'azd-env-name': environmentName
  }
}

module resources './modules/resources.bicep' = {
  scope: rg
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    apiBearerToken: apiBearerToken
    foundryDeploymentName: foundryDeploymentName
    foundryEndpoint: 'https://${foundryResourceName}.cognitiveservices.azure.com/'
  }
}

module foundryRole './modules/foundry-role.bicep' = {
  scope: resourceGroup(foundryResourceGroupName)
  params: {
    foundryResourceName: foundryResourceName
    principalId: resources.outputs.identityPrincipalId
  }
}

@description('Resource group identifier.')
output RESOURCE_GROUP_ID string = rg.id

@description('Resource group name.')
output AZURE_RESOURCE_GROUP string = rg.name

@description('Container registry login server.')
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.containerRegistryEndpoint

@description('Public API URL.')
output API_URL string = resources.outputs.apiUrl

@description('User-assigned managed identity client ID.')
output AZURE_CLIENT_ID string = resources.outputs.identityClientId

@description('Log Analytics workspace resource ID.')
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = resources.outputs.logAnalyticsWorkspaceId
