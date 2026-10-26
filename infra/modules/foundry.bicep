metadata name = 'Azure OpenAI in Microsoft Foundry'
metadata description = 'Creates a keyless OpenAI account and pinned GlobalStandard deployments.'

@description('The OpenAI account name and custom subdomain.')
param accountName string

@description('The Azure region for the account.')
param location string

@description('The AppOnboard session tags.')
param tags object

@description('The GlobalStandard capacity for the verification model deployment.')
param verifyModelCapacity int

resource account 'Microsoft.CognitiveServices/accounts@2026-09-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource verifyDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: 'guide-verify'
  sku: {
    name: 'GlobalStandard'
    capacity: verifyModelCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.6-luna'
      version: '2026-07-09'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource authorDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: 'guide-author'
  // The account rejects simultaneous model-deployment operations.
  dependsOn: [
    verifyDeployment
  ]
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.6-terra'
      version: '2026-07-09'
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

@description('The AI Services account resource name.')
output name string = account.name

@description('The AI Services account resource ID.')
output id string = account.id

@description('The endpoint used by the Azure OpenAI-compatible client.')
output endpoint string = account.properties.endpoint
