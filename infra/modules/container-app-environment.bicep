metadata name = 'Container Apps environment'
metadata description = 'Creates a Consumption Container Apps environment connected to Log Analytics.'

@description('The managed environment name.')
param environmentName string

@description('The Azure region for the environment.')
param location string

@description('The AppOnboard session tags.')
param tags object

@description('The Log Analytics workspace name.')
param workspaceName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2026-03-01' existing = {
  name: workspaceName
}

resource environment 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

@description('The managed environment resource name.')
output name string = environment.name

@description('The managed environment resource ID.')
output id string = environment.id
