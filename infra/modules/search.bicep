metadata name = 'Azure AI Search'
metadata description = 'Creates an AAD-only Basic Azure AI Search service.'

@description('The search service name.')
param searchName string

@description('The Azure region for the search service.')
param location string

@description('The AppOnboard session tags.')
param tags object

resource searchService 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchName
  location: location
  tags: tags
  sku: {
    name: 'basic'
  }
  properties: {
    // AAD-only mode rejects an explicit authOptions value.
    disableLocalAuth: true
    hostingMode: 'Default'
    partitionCount: 1
    publicNetworkAccess: 'enabled'
    replicaCount: 1
  }
}

@description('The search service resource name.')
output name string = searchService.name

@description('The search service resource ID.')
output id string = searchService.id

@description('The search service endpoint.')
output endpoint string = 'https://${searchService.name}.search.windows.net'
