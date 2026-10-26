metadata name = 'Private Blob Storage'
metadata description = 'Creates a TLS-only StorageV2 account and private assets container.'

@description('The globally unique storage account name.')
param storageAccountName string

@description('The Azure region for the storage account.')
param location string

@description('The AppOnboard session tags.')
param tags object

resource account 'Microsoft.Storage/storageAccounts@2026-09-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2025-01-01' = {
  parent: account
  name: 'default'
}

resource assetsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2025-01-01' = {
  parent: blobService
  name: 'assets'
  properties: {
    publicAccess: 'None'
  }
}

@description('The storage account resource name.')
output name string = account.name

@description('The storage account resource ID.')
output id string = account.id

@description('The Blob Storage account URL.')
output accountUrl string = account.properties.primaryEndpoints.blob
