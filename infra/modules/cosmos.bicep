metadata name = 'Cosmos DB'
metadata description = 'Creates a serverless NoSQL account, schema containers, and native data-plane RBAC.'

@description('The Cosmos DB account name.')
param accountName string

@description('The Cosmos SQL database name.')
param databaseName string

@description('The object ID of the deployment user.')
param deployerObjectId string

@description('The user-assigned identity name.')
param identityName string

@description('The Azure region for the account.')
param location string

@description('The AppOnboard session tags.')
param tags object

resource account 'Microsoft.DocumentDB/databaseAccounts@2026-03-15' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      {
        name: 'EnableServerless'
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    disableLocalAuth: true
    enableAutomaticFailover: false
    enableMultipleWriteLocations: false
    locations: [
      {
        failoverPriority: 0
        isZoneRedundant: false
        locationName: location
      }
    ]
    publicNetworkAccess: 'Disabled'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2025-04-15' = {
  parent: account
  name: databaseName
  properties: {
    resource: {
      id: databaseName
    }
  }
}

resource catalog 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-04-15' = {
  parent: database
  name: 'catalog'
  properties: {
    resource: {
      id: 'catalog'
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/id'
        ]
      }
    }
  }
}

resource sessions 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-04-15' = {
  parent: database
  name: 'sessions'
  properties: {
    resource: {
      id: 'sessions'
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/id'
        ]
      }
    }
  }
}

resource devices 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-04-15' = {
  parent: database
  name: 'devices'
  properties: {
    resource: {
      defaultTtl: 86400
      id: 'devices'
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/id'
        ]
      }
    }
  }
}

resource invites 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2025-04-15' = {
  parent: database
  name: 'invites'
  properties: {
    resource: {
      defaultTtl: 604800
      id: 'invites'
      partitionKey: {
        kind: 'Hash'
        paths: [
          '/id'
        ]
      }
    }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

var cosmosDataContributorRoleId = '00000000-0000-0000-0000-000000000002'
var cosmosDataContributorDefinitionId = '${account.id}/sqlRoleDefinitions/${cosmosDataContributorRoleId}'

resource identityDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-04-15' = {
  parent: account
  name: guid(account.id, identityName, cosmosDataContributorRoleId)
  properties: {
    principalId: identity.properties.principalId
    roleDefinitionId: cosmosDataContributorDefinitionId
    scope: account.id
  }
}

resource deployerDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2025-04-15' = {
  parent: account
  name: guid(account.id, deployerObjectId, cosmosDataContributorRoleId)
  properties: {
    principalId: deployerObjectId
    roleDefinitionId: cosmosDataContributorDefinitionId
    scope: account.id
  }
}

@description('The Cosmos DB account resource name.')
output name string = account.name

@description('The Cosmos DB account resource ID.')
output id string = account.id

@description('The Cosmos DB endpoint.')
output endpoint string = account.properties.documentEndpoint
