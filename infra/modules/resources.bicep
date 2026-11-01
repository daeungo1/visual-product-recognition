targetScope = 'resourceGroup'

@description('AZD environment name.')
param environmentName string

@description('Resource location.')
param location string = resourceGroup().location

@description('Tags applied to resources.')
param tags object = {}

@description('Bearer token required by protected API routes.')
@secure()
param apiBearerToken string

@description('Access code exchanged for a secure mobile demo session cookie.')
@secure()
param demoAccessCode string

@description('Dedicated signing secret for expiring demo session cookies.')
@secure()
param demoSessionSecret string

@description('Existing Foundry endpoint.')
param foundryEndpoint string

@description('Existing GPT deployment name.')
param foundryDeploymentName string

var resourceToken = uniqueString(subscription().id, resourceGroup().id, location, environmentName)
var identityName = 'azid${resourceToken}'
var registryName = 'azcr${resourceToken}'
var storageName = 'azst${resourceToken}'
var logAnalyticsName = 'azlaw${resourceToken}'
var appInsightsName = 'azap${resourceToken}'
var environmentNameResource = 'azcae${resourceToken}'
var apiName = 'azapi${resourceToken}'
var keyVaultName = 'azkv${resourceToken}'

module identity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.0' = {
  params: {
    name: identityName
    location: location
    tags: tags
  }
}

module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.12.0' = {
  params: {
    name: logAnalyticsName
    location: location
    tags: tags
    dailyQuotaGb: 1
    dataRetention: 30
  }
}

module appInsights 'br/public:avm/res/insights/component:0.6.0' = {
  params: {
    name: appInsightsName
    location: location
    tags: tags
    workspaceResourceId: logAnalytics.outputs.resourceId
    applicationType: 'web'
  }
}

module registry 'br/public:avm/res/container-registry/registry:0.9.0' = {
  params: {
    name: registryName
    location: location
    tags: tags
    acrSku: 'Basic'
    acrAdminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
    roleAssignments: [
      {
        principalId: identity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
      }
    ]
  }
}

module storage 'br/public:avm/res/storage/storage-account:0.26.0' = {
  params: {
    name: storageName
    location: location
    tags: tags
    skuName: 'Standard_LRS'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    publicNetworkAccess: 'Enabled'
    roleAssignments: [
      {
        principalId: identity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
      }
      {
        principalId: identity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
      }
    ]
  }
}

module keyVault 'br/public:avm/res/key-vault/vault:0.13.0' = {
  params: {
    name: keyVaultName
    location: location
    tags: tags
    enableRbacAuthorization: true
    publicNetworkAccess: 'Enabled'
    roleAssignments: [
      {
        principalId: identity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'
      }
    ]
    secrets: [
      {
        name: 'api-bearer-token'
        value: apiBearerToken
      }
      {
        name: 'demo-access-code'
        value: demoAccessCode
      }
      {
        name: 'demo-session-secret'
        value: demoSessionSecret
      }
    ]
  }
}

module containerEnvironment 'br/public:avm/res/app/managed-environment:0.11.0' = {
  params: {
    name: environmentNameResource
    location: location
    tags: tags
    zoneRedundant: false
    publicNetworkAccess: 'Enabled'
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.outputs.logAnalyticsWorkspaceId
        sharedKey: logAnalytics.outputs.primarySharedKey
      }
    }
  }
}

module api 'br/public:avm/res/app/container-app:0.18.0' = {
  params: {
    name: apiName
    location: location
    tags: union(tags, {
      'azd-service-name': 'api'
    })
    environmentResourceId: containerEnvironment.outputs.resourceId
    managedIdentities: {
      userAssignedResourceIds: [
        identity.outputs.resourceId
      ]
    }
    registries: [
      {
        server: registry.outputs.loginServer
        identity: identity.outputs.resourceId
      }
    ]
    secrets: [
      {
        name: 'api-bearer-token'
        value: apiBearerToken
      }
      {
        name: 'demo-access-code'
        value: demoAccessCode
      }
      {
        name: 'demo-session-secret'
        value: demoSessionSecret
      }
    ]
    ingressExternal: true
    ingressAllowInsecure: false
    ingressTargetPort: 8000
    corsPolicy: {
      allowCredentials: false
      allowedHeaders: [
        'Authorization'
        'Content-Type'
      ]
      allowedMethods: [
        'GET'
        'POST'
      ]
      allowedOrigins: [
        '*'
      ]
    }
    scaleSettings: {
      minReplicas: 0
      maxReplicas: 2
    }
    containers: [
      {
        name: 'api'
        image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        resources: {
          cpu: json('0.5')
          memory: '1Gi'
        }
        env: [
          {
            name: 'API_BEARER_TOKEN'
            secretRef: 'api-bearer-token'
          }
          {
            name: 'DEMO_ACCESS_CODE'
            secretRef: 'demo-access-code'
          }
          {
            name: 'DEMO_SESSION_SECRET'
            secretRef: 'demo-session-secret'
          }
          {
            name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
            value: appInsights.outputs.connectionString
          }
          {
            name: 'AZURE_CLIENT_ID'
            value: identity.outputs.clientId
          }
          {
            name: 'FOUNDRY_DEPLOYMENT'
            value: foundryDeploymentName
          }
          {
            name: 'FOUNDRY_ENDPOINT'
            value: foundryEndpoint
          }
          {
            name: 'STORAGE_ACCOUNT_URL'
            value: storage.outputs.primaryBlobEndpoint
          }
        ]
        probes: [
          {
            type: 'Liveness'
            periodSeconds: 30
            timeoutSeconds: 5
            httpGet: {
              path: '/healthz'
              port: 8000
              scheme: 'HTTP'
            }
          }
          {
            type: 'Readiness'
            periodSeconds: 10
            timeoutSeconds: 5
            httpGet: {
              path: '/readyz'
              port: 8000
              scheme: 'HTTP'
            }
          }
        ]
      }
    ]
  }
}

@description('Container registry login server.')
output containerRegistryEndpoint string = registry.outputs.loginServer

@description('Public API URL.')
output apiUrl string = 'https://${api.outputs.fqdn}'

@description('User-assigned managed identity principal ID.')
output identityPrincipalId string = identity.outputs.principalId

@description('User-assigned managed identity client ID.')
output identityClientId string = identity.outputs.clientId

@description('Log Analytics workspace resource ID.')
output logAnalyticsWorkspaceId string = logAnalytics.outputs.resourceId
