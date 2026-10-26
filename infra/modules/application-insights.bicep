metadata name = 'Application Insights'
metadata description = 'Creates workspace-based web Application Insights for the API.'

@description('The Application Insights component name.')
param componentName string

@description('The Azure region for the component.')
param location string

@description('The AppOnboard session tags.')
param tags object

@description('The Log Analytics workspace name.')
param workspaceName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2026-03-01' existing = {
  name: workspaceName
}

resource component 'Microsoft.Insights/components@2020-02-02' = {
  name: componentName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

@description('The Application Insights component resource ID.')
output id string = component.id

@description('The non-secret Application Insights connection string.')
output connectionString string = component.properties.ConnectionString
