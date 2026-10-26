targetScope = 'resourceGroup'

metadata name = 'Visual Guide private runtime activation'
metadata description = 'Deploys only the real API into an existing private environment.'

@description('The real immutable application image.')
param containerImage string

@description('The application name.')
param appName string

@description('The existing VNet-integrated environment name.')
param environmentName string

@description('The existing runtime identity name.')
param identityName string

@description('The existing registry name.')
param registryName string

@description('The existing Cosmos account name.')
param cosmosAccountName string

@description('The existing private Blob account name.')
param storageAccountName string

@description('The existing image-search service name.')
param searchName string

@description('The existing OpenAI account name.')
param foundryAccountName string

@description('The existing telemetry component name.')
param appInsightsName string

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2026-03-15' existing = {
  name: cosmosAccountName
}

resource storage 'Microsoft.Storage/storageAccounts@2025-01-01' existing = {
  name: storageAccountName
}

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

module runtime './modules/container-app.bicep' = {
  name: 'api-runtime'
  params: {
    appInsightsConnectionString: appInsights.properties.ConnectionString
    appName: appName
    containerImage: containerImage
    cosmosEndpoint: cosmos.properties.documentEndpoint
    environmentName: environmentName
    foundryEndpoint: foundry.properties.endpoint
    identityName: identityName
    location: resourceGroup().location
    registryName: registryName
    searchEndpoint: 'https://${searchName}.search.windows.net'
    shouldDeployApplication: true
    storageAccountUrl: storage.properties.primaryEndpoints.blob
    tags: union(resourceGroup().tags, {
      environment: 'svg-dev-private'
    })
  }
}

@description('The real deployed HTTPS API origin.')
output apiUrl string = runtime.outputs.apiUrl!
