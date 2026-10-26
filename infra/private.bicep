targetScope = 'resourceGroup'

metadata name = 'Samsung Visual Guide private network extension'
metadata description = 'Adds VNet integration, private endpoints, a private Container Apps environment, and an optional bootstrap job without recreating base resources.'

/* Deployment metadata */

@description('The Azure region for the private extension.')
param location string

@description('The AppOnboard session identifier.')
param sessionId string

@description('The display name of the deployment principal.')
param deployedBy string

@description('The ISO 8601 timestamp for this private extension.')
param createdAt string

/* Existing resource names */

@description('The existing Cosmos DB account name.')
param cosmosAccountName string

@description('The existing Blob Storage account name.')
param storageAccountName string

@description('The existing Container Registry name.')
param registryName string

@description('The existing AI Search service name.')
param searchName string

@description('The existing OpenAI account name.')
param foundryAccountName string

@description('The existing application UAMI name.')
param appIdentityName string

@description('The existing Log Analytics workspace name.')
param logAnalyticsName string

@description('The existing Application Insights component name.')
param appInsightsName string

/* New network and compute names */

@description('The new VNet name.')
param vnetName string

@description('The new Container Apps environment name.')
param privateEnvironmentName string

@description('The Container App name.')
param appName string

@description('The manual bootstrap job name.')
param bootstrapJobName string

@description('The new setup identity name.')
param setupIdentityName string

@description('The VNet address space.')
param vnetAddressSpace string = '10.48.0.0/16'

@description('The delegated Container Apps subnet name.')
param acaSubnetName string = 'snet-aca-svg-dev-4ca0'

@description('The delegated Container Apps subnet prefix.')
param acaSubnetPrefix string = '10.48.0.0/23'

@description('The private endpoint subnet name.')
param endpointSubnetName string = 'snet-endpoints-svg-dev-4ca0'

@description('The private endpoint subnet prefix.')
param endpointSubnetPrefix string = '10.48.2.0/24'

/* Application activation and bootstrap inputs */

@description('Deploy the real private Container App only after bootstrap prepare succeeds.')
param shouldDeployApplication bool = false

@description('The actual ACR image used by both the application and bootstrap job.')
param containerImage string?

@description('The bootstrap operation. Prepare is the safe initial operation.')
param bootstrapOperation string = 'prepare'

@description('Optional real API origin for bootstrap activation or invitation work.')
param bootstrapApiUrl string?

@description('Optional SHA-256 device invite hash. Never pass the plaintext invite.')
@secure()
param bootstrapDeviceInviteHash string?

@description('Optional invite expiration time as a Unix epoch value.')
param bootstrapInviteExpiresAt string?

var tags = {
  'app-onboard-skill': 'true'
  'app-onboard-session-id': sessionId
  'created-at': createdAt
  environment: 'svg-dev-private'
  'deployed-by': deployedBy
}

module network './modules/private-network.bicep' = {
  name: 'private-network'
  params: {
    acaSubnetName: acaSubnetName
    acaSubnetPrefix: acaSubnetPrefix
    cosmosAccountName: cosmosAccountName
    endpointSubnetName: endpointSubnetName
    endpointSubnetPrefix: endpointSubnetPrefix
    location: location
    storageAccountName: storageAccountName
    tags: tags
    vnetAddressSpace: vnetAddressSpace
    vnetName: vnetName
  }
}

module identity './modules/private-identity.bicep' = {
  name: 'private-identity'
  params: {
    cosmosAccountName: cosmosAccountName
    identityName: setupIdentityName
    location: location
    registryName: registryName
    searchName: searchName
    storageAccountName: storageAccountName
    tags: tags
  }
}

module compute './modules/private-compute.bicep' = {
  name: 'private-compute'
  params: {
    acaSubnetId: network.outputs.acaSubnetId
    appIdentityName: appIdentityName
    appInsightsName: appInsightsName
    appName: appName
    bootstrapApiUrl: bootstrapApiUrl
    bootstrapDeviceInviteHash: bootstrapDeviceInviteHash
    bootstrapInviteExpiresAt: bootstrapInviteExpiresAt
    bootstrapJobName: bootstrapJobName
    bootstrapOperation: bootstrapOperation
    containerImage: containerImage
    cosmosAccountName: cosmosAccountName
    foundryAccountName: foundryAccountName
    location: location
    logAnalyticsName: logAnalyticsName
    privateEnvironmentName: privateEnvironmentName
    registryName: registryName
    searchName: searchName
    setupIdentityName: setupIdentityName
    shouldDeployApplication: shouldDeployApplication
    storageAccountName: storageAccountName
    tags: tags
  }
  dependsOn: [
    network
    identity
  ]
}

/* Handoff outputs */

@description('The new VNet resource ID.')
output vnetId string = network.outputs.vnetId

@description('The delegated Container Apps subnet resource ID.')
output acaSubnetId string = network.outputs.acaSubnetId

@description('The private endpoint subnet resource ID.')
output endpointSubnetId string = network.outputs.endpointSubnetId

@description('The NAT Gateway resource ID.')
output natGatewayId string = network.outputs.natGatewayId

@description('The NAT Gateway static public IP address.')
output natPublicIpAddress string = network.outputs.natPublicIpAddress

@description('The Cosmos private endpoint resource ID.')
output cosmosPrivateEndpointId string = network.outputs.cosmosPrivateEndpointId

@description('The Blob private endpoint resource ID.')
output storagePrivateEndpointId string = network.outputs.storagePrivateEndpointId

@description('The private Container Apps environment resource ID.')
output privateEnvironmentId string = compute.outputs.environmentId

@description('The private Container App resource ID, or null before activation.')
output containerAppId string? = shouldDeployApplication && !empty(containerImage) ? compute.outputs.containerAppId : null

@description('The private Container App HTTPS URL, or null before activation.')
output apiUrl string? = shouldDeployApplication && !empty(containerImage) ? compute.outputs.apiUrl : null

@description('The bootstrap job resource ID, or null until an actual image is supplied.')
output bootstrapJobId string? = !empty(containerImage) ? compute.outputs.bootstrapJobId : null

@description('The existing application UAMI client ID.')
output appRuntimeClientId string = compute.outputs.appRuntimeClientId

@description('The separate bootstrap job UAMI client ID.')
output setupJobClientId string = identity.outputs.clientId
