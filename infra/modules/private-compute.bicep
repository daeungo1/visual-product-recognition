metadata name = 'Private Container Apps compute'
metadata description = 'Creates the VNet-integrated Container Apps environment, real API app, and manual bootstrap job.'

@description('The delegated ACA subnet resource ID.')
param acaSubnetId string

@description('The existing application UAMI name.')
param appIdentityName string

@description('The existing Application Insights component name.')
param appInsightsName string

@description('The Container App name.')
param appName string

@description('Optional real API origin for bootstrap activation or invitation work.')
param bootstrapApiUrl string?

@description('Optional SHA-256 device invite hash.')
@secure()
param bootstrapDeviceInviteHash string?

@description('Optional invite expiration time as a Unix epoch value.')
param bootstrapInviteExpiresAt string?

@description('The bootstrap job name.')
param bootstrapJobName string

@description('The bootstrap operation.')
param bootstrapOperation string

@description('The actual ACR image used by the app and job.')
param containerImage string?

@description('The existing Cosmos DB account name.')
param cosmosAccountName string

@description('The existing OpenAI account name.')
param foundryAccountName string

@description('The Azure region.')
param location string

@description('The existing Log Analytics workspace name.')
param logAnalyticsName string

@description('The private Container Apps environment name.')
param privateEnvironmentName string

@description('The existing ACR name.')
param registryName string

@description('The existing AI Search name.')
param searchName string

@description('The setup identity name.')
param setupIdentityName string

@description('Deploy the real private Container App after bootstrap prepare succeeds.')
param shouldDeployApplication bool

@description('The existing Blob Storage account name.')
param storageAccountName string

@description('The AppOnboard session tags.')
param tags object

resource workspace 'Microsoft.OperationalInsights/workspaces@2026-03-01' existing = {
  name: logAnalyticsName
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: appIdentityName
}

resource setupIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: setupIdentityName
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2026-03-15' existing = {
  name: cosmosAccountName
}

resource storage 'Microsoft.Storage/storageAccounts@2026-09-01' existing = {
  name: storageAccountName
}

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchName
}

resource foundry 'Microsoft.CognitiveServices/accounts@2026-09-01' existing = {
  name: foundryAccountName
}

var deployRealApplication = shouldDeployApplication && !empty(containerImage)
var deployBootstrapJob = !empty(containerImage)
var cosmosEndpoint = 'https://${cosmos.name}.documents.azure.com:443/'
var storageAccountUrl = 'https://${storage.name}.blob.core.windows.net'
var searchEndpoint = 'https://${search.name}.search.windows.net'
var foundryEndpoint = 'https://${foundry.name}.openai.azure.com/'

var commonRuntimeEnv = [
  {
    name: 'VISUAL_GUIDE_MODE'
    value: 'cloud'
  }
  {
    name: 'COSMOS_ENDPOINT'
    value: cosmosEndpoint
  }
  {
    name: 'COSMOS_DATABASE'
    value: 'visualguide'
  }
  {
    name: 'AZURE_STORAGE_ACCOUNT_URL'
    value: storageAccountUrl
  }
  {
    name: 'BLOB_CONTAINER'
    value: 'assets'
  }
  {
    name: 'AZURE_SEARCH_ENDPOINT'
    value: searchEndpoint
  }
  {
    name: 'AZURE_SEARCH_INDEX'
    value: 'product-images'
  }
  {
    name: 'AZURE_OPENAI_ENDPOINT'
    value: foundryEndpoint
  }
  {
    name: 'AZURE_OPENAI_API_VERSION'
    value: '2025-04-01-preview'
  }
  {
    name: 'AZURE_OPENAI_VERIFY_DEPLOYMENT'
    value: 'guide-verify'
  }
  {
    name: 'AZURE_OPENAI_AUTHOR_DEPLOYMENT'
    value: 'guide-author'
  }
  {
    name: 'EMBEDDING_MODEL_PATH'
    value: '/opt/models/siglip2-base-patch16-224'
  }
  {
    name: 'PORT'
    value: '8000'
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appInsights.properties.ConnectionString
  }
  {
    name: 'OMP_NUM_THREADS'
    value: '2'
  }
  {
    name: 'MKL_NUM_THREADS'
    value: '2'
  }
  {
    name: 'TOKENIZERS_PARALLELISM'
    value: 'false'
  }
]

var bootstrapEnv = concat(
  [
    {
      name: 'BOOTSTRAP_OPERATION'
      value: bootstrapOperation
    }
  ],
  empty(bootstrapApiUrl) ? [] : [
    {
      name: 'BOOTSTRAP_API_URL'
      value: bootstrapApiUrl!
    }
  ],
  empty(bootstrapDeviceInviteHash) ? [] : [
    {
      name: 'BOOTSTRAP_DEVICE_INVITE_HASH'
      value: bootstrapDeviceInviteHash!
    }
  ],
  empty(bootstrapInviteExpiresAt) ? [] : [
    {
      name: 'BOOTSTRAP_INVITE_EXPIRES_AT'
      value: bootstrapInviteExpiresAt!
    }
  ]
)

resource environment 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: privateEnvironmentName
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
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: false
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource containerApp 'Microsoft.App/containerApps@2026-07-01' = if (deployRealApplication) {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${appIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8000
        transport: 'auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          identity: appIdentity.id
          server: registry.properties.loginServer
        }
      ]
      secrets: []
    }
    template: {
      containers: [
        {
          name: 'guide-api'
          image: containerImage!
          env: concat(
            [
              {
                name: 'AZURE_CLIENT_ID'
                value: appIdentity.properties.clientId
              }
            ],
            commonRuntimeEnv
          )
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/healthz'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 10
              failureThreshold: 60
              timeoutSeconds: 5
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/healthz'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 60
              periodSeconds: 15
              failureThreshold: 6
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/readyz'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 60
              periodSeconds: 15
              failureThreshold: 20
              timeoutSeconds: 5
            }
          ]
          resources: {
            cpu: 2
            memory: '4Gi'
          }
        }
      ]
      scale: {
        maxReplicas: 2
        minReplicas: 1
      }
    }
  }
}

resource bootstrapJob 'Microsoft.App/jobs@2025-01-01' = if (deployBootstrapJob) {
  name: bootstrapJobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${setupIdentity.id}': {}
    }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      replicaRetryLimit: 0
      replicaTimeout: 1800
      registries: [
        {
          identity: setupIdentity.id
          server: registry.properties.loginServer
        }
      ]
      triggerType: 'Manual'
    }
    template: {
      containers: [
        {
          name: 'bootstrap'
          image: containerImage!
          command: [
            'python'
            '-m'
            'guide_api.bootstrap'
          ]
          env: concat(
            [
              {
                name: 'AZURE_CLIENT_ID'
                value: setupIdentity.properties.clientId
              }
            ],
            commonRuntimeEnv,
            bootstrapEnv
          )
          resources: {
            cpu: 2
            memory: '4Gi'
          }
        }
      ]
    }
  }
}

@description('The private Container Apps environment resource ID.')
output environmentId string = environment.id

@description('The private Container App resource ID, or null before activation.')
output containerAppId string? = deployRealApplication ? containerApp!.id : null

@description('The private Container App HTTPS URL, or null before activation.')
output apiUrl string? = deployRealApplication ? 'https://${containerApp!.properties.configuration.ingress.fqdn}' : null

@description('The bootstrap job resource ID, or null until an image is supplied.')
output bootstrapJobId string? = deployBootstrapJob ? bootstrapJob!.id : null

@description('The existing application UAMI client ID.')
output appRuntimeClientId string = appIdentity.properties.clientId
