metadata name = 'Private network extension'
metadata description = 'Creates the VNet, delegated ACA subnet, NAT Gateway, private DNS, and data-service private endpoints.'

@description('The Cosmos DB account name.')
param cosmosAccountName string

@description('The Blob Storage account name.')
param storageAccountName string

@description('The VNet name.')
param vnetName string

@description('The VNet address space.')
param vnetAddressSpace string

@description('The delegated ACA subnet name.')
param acaSubnetName string

@description('The delegated ACA subnet address prefix.')
param acaSubnetPrefix string

@description('The private endpoint subnet name.')
param endpointSubnetName string

@description('The private endpoint subnet address prefix.')
param endpointSubnetPrefix string

@description('The Azure region.')
param location string

@description('The AppOnboard session tags.')
param tags object

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2026-03-15' existing = {
  name: cosmosAccountName
}

resource storage 'Microsoft.Storage/storageAccounts@2026-09-01' existing = {
  name: storageAccountName
}

resource natPublicIp 'Microsoft.Network/publicIPAddresses@2024-07-01' = {
  name: 'pip-ng-svg-dev-4ca0'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAddressVersion: 'IPv4'
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2024-07-01' = {
  name: 'ng-svg-dev-4ca0'
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    idleTimeoutInMinutes: 4
    publicIpAddresses: [
      {
        id: natPublicIp.id
      }
    ]
  }
}

resource vnet 'Microsoft.Network/virtualNetworks@2024-07-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressSpace
      ]
    }
    subnets: [
      {
        name: acaSubnetName
        properties: {
          addressPrefix: acaSubnetPrefix
          delegations: [
            {
              name: 'aca-environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
          natGateway: {
            id: natGateway.id
          }
        }
      }
      {
        name: endpointSubnetName
        properties: {
          addressPrefix: endpointSubnetPrefix
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

var acaSubnetId = resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, acaSubnetName)
var endpointSubnetId = resourceId('Microsoft.Network/virtualNetworks/subnets', vnet.name, endpointSubnetName)

resource cosmosDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.documents.azure.com'
  location: 'global'
  tags: tags
}

resource storageDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.blob.core.windows.net'
  location: 'global'
  tags: tags
}

resource cosmosDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: cosmosDnsZone
  name: 'vnet-svg-dev-4ca0-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource storageDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: storageDnsZone
  name: 'vnet-svg-dev-4ca0-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

resource cosmosPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = {
  name: 'pe-cosmos-svg-dev-4ca0'
  location: location
  tags: tags
  properties: {
    privateLinkServiceConnections: [
      {
        name: 'cosmos-sql'
        properties: {
          groupIds: [
            'Sql'
          ]
          privateLinkServiceId: cosmos.id
        }
      }
    ]
    subnet: {
      id: endpointSubnetId
    }
  }
}

resource cosmosPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = {
  parent: cosmosPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cosmos'
        properties: {
          privateDnsZoneId: cosmosDnsZone.id
        }
      }
    ]
  }
}

resource storagePrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-07-01' = {
  name: 'pe-storage-svg-dev-4ca0'
  location: location
  tags: tags
  properties: {
    privateLinkServiceConnections: [
      {
        name: 'storage-blob'
        properties: {
          groupIds: [
            'blob'
          ]
          privateLinkServiceId: storage.id
        }
      }
    ]
    subnet: {
      id: endpointSubnetId
    }
  }
}

resource storagePrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-07-01' = {
  parent: storagePrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: storageDnsZone.id
        }
      }
    ]
  }
}

@description('The VNet resource ID.')
output vnetId string = vnet.id

@description('The delegated ACA subnet resource ID.')
output acaSubnetId string = acaSubnetId

@description('The private endpoint subnet resource ID.')
output endpointSubnetId string = endpointSubnetId

@description('The NAT Gateway resource ID.')
output natGatewayId string = natGateway.id

@description('The NAT Gateway public IP address.')
output natPublicIpAddress string = natPublicIp.properties.ipAddress

@description('The Cosmos private endpoint resource ID.')
output cosmosPrivateEndpointId string = cosmosPrivateEndpoint.id

@description('The Blob private endpoint resource ID.')
output storagePrivateEndpointId string = storagePrivateEndpoint.id
