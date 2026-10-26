metadata name = 'Azure Container Registry'
metadata description = 'Creates a Basic registry with administrator credentials disabled.'

@description('The registry name.')
param registryName string

@description('The Azure region for the registry.')
param location string

@description('The AppOnboard session tags.')
param tags object

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

@description('The registry resource name.')
output name string = registry.name

@description('The registry resource ID.')
output id string = registry.id

@description('The registry login server.')
output loginServer string = registry.properties.loginServer
