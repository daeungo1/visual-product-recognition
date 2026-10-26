metadata name = 'Guide API Container App'
metadata description = 'Optionally deploys the real FastAPI image after backing resources and RBAC exist.'

@description('The Application Insights connection string.')
param appInsightsConnectionString string

@description('The Container App name.')
param appName string

@description('The real ACR image. Null means no application resource is created.')
param containerImage string?

@description('The Cosmos DB endpoint.')
param cosmosEndpoint string

@description('The managed environment name.')
param environmentName string

@description('The Microsoft Foundry endpoint.')
param foundryEndpoint string

@description('The user-assigned identity name.')
param identityName string

@description('The Azure region for the application.')
param location string

@description('The ACR name.')
param registryName string

@description('The AI Search endpoint.')
param searchEndpoint string

@description('Deploy the application only when a real image is supplied.')
param shouldDeployApplication bool

@description('The Blob Storage account URL.')
param storageAccountUrl string

@description('The AppOnboard session tags.')
param tags object

var deployRealApplication = shouldDeployApplication && !empty(containerImage)
var appPort = 8000

resource managedEnvironment 'Microsoft.App/managedEnvironments@2026-07-01' existing = {
  name: environmentName
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' existing = {
  name: identityName
}

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = {
  name: registryName
}

resource containerApp 'Microsoft.App/containerApps@2026-07-01' = if (deployRealApplication) {
  name: appName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      ingress: {
        allowInsecure: false
        external: true
        targetPort: appPort
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
          identity: identity.id
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
          env: [
            {
              name: 'VISUAL_GUIDE_MODE'
              value: 'cloud'
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: identity.properties.clientId
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
              value: string(appPort)
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              value: appInsightsConnectionString
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
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/healthz'
                port: appPort
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
                port: appPort
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
                port: appPort
                scheme: 'HTTP'
              }
              initialDelaySeconds: 60
              periodSeconds: 15
              failureThreshold: 20
              timeoutSeconds: 5
            }
          ]
          resources: {
            cpu: '2'
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

@description('The Container App resource ID, or null when phase 1 leaves the app undeployed.')
output id string? = deployRealApplication ? containerApp.id : null

@description('The public HTTPS API URL, or null when phase 1 leaves the app undeployed.')
output apiUrl string? = shouldDeployApplication && !empty(containerImage) ? 'https://${containerApp!.properties.configuration.ingress.fqdn}' : null
