metadata name = 'Bootstrap managed identity'
metadata description = 'Creates the separate bootstrap identity and least-privilege data-plane access.'

@description('The setup identity name.')
param identityName string

@description('The Azure region.')
param location string

@description('The existing ACR name.')
param registryName string

@description('The existing Storage account name.')
param storageAccountName string

@description('The existing Search service name.')
param searchName string

@description('The existing Cosmos DB account name.')
param cosmosAccountName string

@description('The AppOnboard session tags.')
param tags object

resource setupIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: location
  tags: tags
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource storage 'Microsoft.Storage/storageAccounts@2026-09-01' existing = {
  name: storageAccountName
}

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchName
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2026-03-15' existing = {
  name: cosmosAccountName
}

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var storageBlobContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
var searchIndexContributorRoleId = '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource setupAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identityName, acrPullRoleId)
  scope: registry
  properties: {
    principalId: setupIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

resource setupStorageContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identityName, storageBlobContributorRoleId)
  scope: storage
  properties: {
    principalId: setupIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobContributorRoleId)
  }
}

resource setupSearchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, identityName, searchServiceContributorRoleId)
  scope: search
  properties: {
    principalId: setupIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
  }
}

resource setupSearchIndexContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, identityName, searchIndexContributorRoleId)
  scope: search
  properties: {
    principalId: setupIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexContributorRoleId)
  }
}

resource setupCosmosDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-04-15' = {
  parent: cosmos
  name: guid(cosmos.id, identityName, cosmosDataContributorRoleId)
  properties: {
    principalId: setupIdentity.properties.principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosDataContributorRoleId}'
    scope: cosmos.id
  }
}

@description('The setup identity resource name.')
output name string = setupIdentity.name

@description('The setup identity resource ID.')
output id string = setupIdentity.id

@description('The setup identity client ID.')
output clientId string = setupIdentity.properties.clientId

@description('The setup identity principal ID.')
output principalId string = setupIdentity.properties.principalId
