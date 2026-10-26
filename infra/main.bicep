targetScope = 'subscription'

metadata name = 'Samsung Visual Guide PoC infrastructure'
metadata description = 'Creates the backing Azure resources for the CPU-based visual guide API.'

/* Deployment identity and session metadata */

@description('The deployment environment name.')
@minLength(1)
@maxLength(64)
param environmentName string

@description('The Azure region for all regional resources.')
@minLength(1)
param location string

@description('The AppOnboard session identifier.')
param sessionId string

@description('The display name of the deployment principal.')
param deployedBy string

@description('The ISO 8601 timestamp for this scaffold.')
param createdAt string

@description('The object ID of the user running the deployment.')
param deployerObjectId string

/* Application phase switch */

@description('Deploy the real Container App only when an actual ACR image is supplied.')
param shouldDeployApplication bool = false

@description('The fully qualified ACR image for phase 2. Leave null for phase 1.')
param containerImage string?

@description('The GlobalStandard capacity for the verification model deployment.')
param verifyModelCapacity int = 10

var tags = {
  'app-onboard-skill': 'true'
  'app-onboard-session-id': sessionId
  'created-at': createdAt
  environment: environmentName
  'deployed-by': deployedBy
}

resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module identity './modules/managed-identity.bicep' = {
  name: 'managed-identity'
  scope: rg
  params: {
    identityName: 'id-svg-dev-4ca0'
    location: location
    tags: tags
  }
}

module logAnalytics './modules/log-analytics.bicep' = {
  name: 'log-analytics'
  scope: rg
  params: {
    workspaceName: 'log-svg-dev-4ca0'
    location: location
    tags: tags
  }
}

module storage './modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    storageAccountName: 'stsvgdev4ca0'
    location: location
    tags: tags
  }
}

module registry './modules/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    registryName: 'crsvgdev4ca0'
    location: location
    tags: tags
  }
}

module foundry './modules/foundry.bicep' = {
  name: 'foundry'
  scope: rg
  params: {
    accountName: 'ai-svg-dev-4ca0'
    location: location
    tags: tags
    verifyModelCapacity: verifyModelCapacity
  }
}

module search './modules/search.bicep' = {
  name: 'search'
  scope: rg
  params: {
    searchName: 'srch-svg-dev-4ca0'
    location: location
    tags: tags
  }
}

module cosmos './modules/cosmos.bicep' = {
  name: 'cosmos'
  scope: rg
  params: {
    accountName: 'cosmos-svg-dev-4ca0'
    databaseName: 'visualguide'
    deployerObjectId: deployerObjectId
    identityName: identity.outputs.name
    location: location
    tags: tags
  }
  dependsOn: [
    identity
  ]
}

module appInsights './modules/application-insights.bicep' = {
  name: 'application-insights'
  scope: rg
  params: {
    componentName: 'appi-svg-dev-4ca0'
    location: location
    tags: tags
    workspaceName: logAnalytics.outputs.name
  }
  dependsOn: [
    logAnalytics
  ]
}

module managedEnvironment './modules/container-app-environment.bicep' = {
  name: 'container-app-environment'
  scope: rg
  params: {
    environmentName: 'cae-svg-dev-4ca0'
    location: location
    tags: tags
    workspaceName: logAnalytics.outputs.name
  }
  dependsOn: [
    logAnalytics
  ]
}

module roleAssignments './modules/role-assignments.bicep' = {
  name: 'role-assignments'
  scope: rg
  params: {
    acrName: registry.outputs.name
    deployerObjectId: deployerObjectId
    foundryName: foundry.outputs.name
    identityName: identity.outputs.name
    searchName: search.outputs.name
    storageAccountName: storage.outputs.name
  }
  dependsOn: [
    identity
    registry
    storage
    search
    foundry
  ]
}

module containerApp './modules/container-app.bicep' = {
  name: 'container-app'
  scope: rg
  params: {
    appInsightsConnectionString: appInsights.outputs.connectionString
    appName: 'ca-svg-dev-4ca0'
    containerImage: containerImage
    cosmosEndpoint: cosmos.outputs.endpoint
    environmentName: managedEnvironment.outputs.name
    foundryEndpoint: foundry.outputs.endpoint
    identityName: identity.outputs.name
    location: location
    registryName: registry.outputs.name
    searchEndpoint: search.outputs.endpoint
    shouldDeployApplication: shouldDeployApplication
    storageAccountUrl: storage.outputs.accountUrl
    tags: tags
  }
  dependsOn: [
    managedEnvironment
    roleAssignments
    appInsights
    cosmos
  ]
}

/* Handoff outputs */

@description('The resource group created by this deployment.')
output resourceGroupName string = rg.name

@description('The managed Container Apps environment resource ID.')
output managedEnvironmentId string = managedEnvironment.outputs.id

@description('The Container Registry login server.')
output registryLoginServer string = registry.outputs.loginServer

@description('The user-assigned managed identity client ID.')
output uamiClientId string = identity.outputs.clientId

@description('The user-assigned managed identity principal ID.')
output uamiPrincipalId string = identity.outputs.principalId

@description('The Cosmos DB endpoint.')
output cosmosEndpoint string = cosmos.outputs.endpoint

@description('The Blob Storage account URL.')
output storageAccountUrl string = storage.outputs.accountUrl

@description('The AI Search endpoint.')
output searchEndpoint string = search.outputs.endpoint

@description('The Microsoft Foundry endpoint.')
output foundryEndpoint string = foundry.outputs.endpoint

@description('The Application Insights connection string.')
output applicationInsightsConnectionString string = appInsights.outputs.connectionString

@description('The deployed API URL, or null until phase 2 deploys the real image.')
output apiUrl string? = shouldDeployApplication && !empty(containerImage) ? containerApp.outputs.apiUrl : null
