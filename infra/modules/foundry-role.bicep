targetScope = 'resourceGroup'

@description('Existing Microsoft Foundry account name.')
param foundryResourceName string

@description('Managed identity principal ID.')
param principalId string

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryResourceName
}

resource foundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, principalId, 'foundry-openai-user')
  scope: foundry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
    )
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}
