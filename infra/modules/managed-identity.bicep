metadata name = 'User-assigned managed identity'
metadata description = 'Creates the identity used by the application for secretless Azure access.'

@description('The user-assigned identity name.')
param identityName string

@description('The Azure region for the identity.')
param location string

@description('The AppOnboard session tags.')
param tags object

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: identityName
  location: location
  tags: tags
}

@description('The identity resource name.')
output name string = identity.name

@description('The identity resource ID.')
output id string = identity.id

@description('The identity client ID.')
output clientId string = identity.properties.clientId

@description('The identity principal ID.')
output principalId string = identity.properties.principalId
