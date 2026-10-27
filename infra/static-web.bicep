targetScope = 'resourceGroup'

@description('Name of the isolated static mock-up resource.')
param staticWebAppName string

@description('Supported Static Web Apps resource region.')
param location string

@description('Resource tags for ownership and purpose.')
param tags object

resource staticWebApp 'Microsoft.Web/staticSites@2024-11-01' = {
  name: staticWebAppName
  location: location
  tags: tags
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {}
}

@description('HTTPS address for the mobile mock-up.')
output webUrl string = 'https://${staticWebApp.properties.defaultHostname}'

@description('Resource ID of the isolated static app.')
output resourceId string = staticWebApp.id
