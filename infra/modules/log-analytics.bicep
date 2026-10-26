metadata name = 'Log Analytics workspace'
metadata description = 'Creates the workspace used by Container Apps and Application Insights.'

@description('The Log Analytics workspace name.')
param workspaceName string

@description('The Azure region for the workspace.')
param location string

@description('The AppOnboard session tags.')
param tags object

resource workspace 'Microsoft.OperationalInsights/workspaces@2026-03-01' = {
  name: workspaceName
  location: location
  tags: tags
  sku: {
    name: 'PerGB2018'
  }
  properties: {
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: json('0.5')
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

@description('The Log Analytics workspace resource name.')
output name string = workspace.name

@description('The Log Analytics workspace resource ID.')
output id string = workspace.id

@description('The Log Analytics workspace customer ID.')
output customerId string = workspace.properties.customerId
