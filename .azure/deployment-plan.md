# Azure Deployment Plan

> **Status:** Deployed

## 1. Project Overview

**Project:** Visual Product Guide

**Path:** New Project

**Purpose:** Build and deploy a PoC that resolves a reviewed Samsung product
and filter-replacement guide, proposes the current operation region with a GPT
vision model, and serves an Android client that tracks confirmed regions locally.

## 2. Requirements

| Requirement | Selection |
|---|---|
| Classification | PoC |
| Scale | Small, fewer than 1,000 users |
| Budget | Balanced |
| Subscription | ME-MngEnvMCAP359144-daeungo-1 (`2cf925b6-80cb-4567-abda-5ccd3010aab5`) |
| Region | Sweden Central |
| Image policy | Explicit consent, step-scoped snapshots, no API retention |
| Product scope | Two or three reviewed Samsung air-conditioner and monitor filter scenarios |
| Inference | Existing `gpt-6-1-terra` deployment, optional `gpt-6.1-sol` adjudication later |
| Open-source inference | SAM 3 on an interruptible GPU Spot VM after the GPT baseline demonstrates a measured need |

The user was unavailable for the structured confirmation form. These selections
use the recommended defaults and the user's explicit authorization to use their
Azure resources. No deployment occurs until this completed plan is approved.

## 3. Components Detected

| Component | Type | Technology | Path |
|---|---|---|---|
| Rebuild design | Specification | Markdown | `docs/superpowers/specs/` |
| Implementation plan | Plan | Markdown | `docs/superpowers/plans/` |
| VELA reference | Separate nested Git repository | Python research project | `VELA-photo-guide-lab-202610/VELA-photo-guide-lab/` |

No application source, Dockerfile, `azure.yaml` or infrastructure currently
exists. The VELA repository remains reference-only and is excluded from the root
Git repository.

## 4. Recipe Selection

**Recipe:** Azure CLI with Bicep

Azure CLI with Bicep is selected because Docker Desktop cannot start in the
current shared Windows environment. Infrastructure remains declarative Bicep,
while Azure Container Registry performs the container build remotely. This
removes the local Docker daemon dependency without changing the application or
resource architecture.

## 5. Architecture

```text
Android application
  -> explicit snapshot consent
  -> public HTTPS Container Apps API
     -> managed identity
     -> existing Foundry GPT-6.1 Terra
     -> private Blob and Table data via RBAC
  -> confirmed region returned to Android
  -> ARCore performs current-frame tracking
```

### Service Mapping

| Component | Azure service | Configuration |
|---|---|---|
| Visual guide API | Azure Container Apps | External HTTPS ingress, scale 0 to 2, 0.5 CPU, 1 GiB |
| Container image | Azure Container Registry | Basic SKU |
| Model inference | Existing Microsoft Foundry account `brk445demo-01` | Existing `gpt-6-1-terra`, GlobalStandard |
| Reviewed assets | Azure Blob Storage | Private container, shared-key access disabled |
| Guide and session records | Azure Table Storage | Managed identity, no connection string |
| Identity | User-assigned managed identity | API access to ACR, Storage and Foundry |
| Telemetry | Application Insights | Request metrics without image or token bodies |
| Logs | Log Analytics | Container and platform logs |

### Supporting Services

No Key Vault is required for the first PoC because the application uses managed
identity and stores no application secrets. No Cosmos DB, AI Search or always-on GPU resource is included in the initial
deployment. A separate Spot VM experiment may be provisioned for SAM 3 after
the GPT baseline is measured. Its eviction policy must delete the VM and retain
only reproducible configuration and approved derived metrics.

### Data Boundaries

* Local inputs are placed under `img/` and ignored by Git.
* Official Samsung images are not copied into the repository unless reuse rights
  are documented.
* User-provided images are used for local and explicitly approved Foundry tests.
* Runtime snapshots are decoded in memory and are not written to Blob Storage.
* Reviewed derived metadata may be stored only after human confirmation.

### Policy Constraints

Azure MCP reported subscription and inherited management-group assignments for
Microsoft Defender, Security Center, MCAPSGov Deny, Audit, Deploy/Modify,
resource-creation blocking and MFA enforcement. The exact template was evaluated
against these policies by ARM validation and subscription-scope what-if. Both
passed, so the selected resources and Sweden Central are allowed for this
deployment. Provisioning may still require an interactive MFA claim.

## 6. Provisioning Limit Checklist

### Phase 1: Prepare Resource Inventory

| Resource | Planned | Existing in Sweden Central | Limit source |
|---|---:|---:|---|
| Container Apps managed environment | 1 | 0 | Azure Quota CLI |
| Container Apps sandbox cores | 1 | 0 | Azure Quota CLI |
| Storage account | 1 | 6 | Azure Quota CLI |
| Container registry | 1 | 3 | Resource inventory; quota API returned no rows |
| Log Analytics workspace | 1 | Existing unrelated resources only | Resource inventory |
| Application Insights | 1 | Existing unrelated resources only | Resource inventory |
| User-assigned managed identity | 1 | Existing unrelated resources only | Resource inventory |
| Foundry account and model deployment | 0 new | Existing account and Terra deployment | Foundry deployment query |
| GPU Spot VM | 0 initially, 1 optional experiment | Pending SKU and quota check | Compute quota and retail price query |

### Phase 2: Fetch Quotas and Validate Capacity

| Quota | Limit | Usage | Available | Planned | Result |
|---|---:|---:|---:|---:|---|
| Managed environments | 50 | 0 | 50 | 1 | Pass |
| Sandbox cores | 300 | 0 | 300 | 1 | Pass |
| Storage accounts | 250 | 6 | 244 | 1 | Pass |

Container Registry did not expose a quota row through `az quota` for this
subscription and region. The current count is three. Validation must confirm the
service limit and resource-name availability before deployment.

`Standard_NC4as_T4_v3` is listed without a regional SKU restriction and the
Linux Spot retail rate was USD 0.17404 per hour on 2026-11-01. The subscription
quota for the `NCASv3_T4` family is zero vCPUs, so the Spot experiment is blocked
until a quota increase is separately approved. No GPU resource is included in
this deployment.

**Status:** All queried resources are within limits.

## 7. Execution Checklist

### Phase 1: Planning

- [x] Create deployment-plan skeleton.
- [x] Analyze workspace in NEW mode.
- [x] Gather requirements with pragmatic defaults.
- [x] Scan codebase and existing Azure dependencies.
- [x] Select AZD with Bicep.
- [x] Define architecture and data boundaries.
- [x] Query subscription policies.
- [x] Check Container Apps and Storage quotas.
- [x] Obtain deployment-plan approval through the user's explicit Azure authorization and autopilot default.

### Phase 2: Execution

- [x] Create the ignored `images/` input folder and upload instructions.
- [ ] Scaffold the Kotlin core, Android app and FastAPI service.
- [x] Implement fake-adapter tests before live model integration.
- [x] Add Foundry GPT-6.1 Terra structured-output adapter.
- [ ] Add reviewed-guide registry and image evaluation harness.
- [x] Generate `azure.yaml`, Dockerfile and Bicep infrastructure.
- [x] Run local API, unit and lint checks.
- [x] Run explicitly approved Foundry tests with user-provided images.
- [ ] Compare a GPU Spot VM SAM 3 refinement only if the GPT baseline misses the agreed threshold.
- [x] Update plan status to `Ready for Validation`.

### Phase 3: Validation

- [x] Invoke `azure-validate`.
- [x] Record validation commands, timestamps and results.
- [x] Confirm plan status is `Validated`.
- [x] All validation checks pass.
  - [x] 1. Core Validation (CLI, auth, build, validate and what-if)
  - [x] 2. Remote ACR Docker Build
  - [x] 3. Azure Policy Validation

### Phase 4: Deployment

- [x] Invoke `azure-deploy`.
- [x] Provision through Bicep and deploy the image through remote ACR build.
- [x] Verify health, readiness, login, camera page and protected GPT endpoint.
- [x] Verify live role assignments.
- [x] Record the deployed HTTPS endpoint.

## 8. Validation Proof

Validation run: 2026-11-01, Sweden Central, subscription
`2cf925b6-80cb-4567-abda-5ccd3010aab5`.

| Check | Command or tool | Result |
|---|---|---|
| Python tests | `pytest server/tests -q` | PASS, 21 tests |
| Python lint | `ruff check server/src server/tests eval` | PASS |
| Local API | `/healthz`, `/readyz` on port 8891 | PASS, HTTP 200 |
| Bicep build | `az bicep build --file infra/main.bicep` | PASS |
| ARM validation | Official `validate-deployment.ps1` at subscription scope | PASS |
| ARM what-if | Official `validate-deployment.ps1` at subscription scope | PASS, Create 12, Modify 0, Delete 0 |
| Container build | `az acr build --no-push`, run `dt1` | PASS, Succeeded |
| Policy validation | Azure MCP `policy_assignment_list` plus ARM what-if | PASS |
| Static RBAC | Review of all role assignments in Bicep | PASS |
| Foundry evaluation | GPT-6.1 Terra, three repeats per uploaded image | PASS |

The Foundry evaluation produced stable `located` consensus for the air
conditioner and dark washer. The white washer returned `not_visible` in all
three runs. These results validate grounding behavior only and do not establish
reviewed Samsung repair instructions.

Deployment `visual-guide-poc-20261101` succeeded after applying the documented
direct-secret fallback for initial Container Apps provisioning. ACR image
`visual-guide-api:20261101-secure` has digest
`sha256:1b8b5d2c129c42443987dbd410086944fcd1e9e7ef105fba7840ece784a9e331`.
Container App revision `azapi5ovedhtoyg74w--0000007` is Healthy.

The final mobile smoke test confirmed login GET 200, login POST 303, camera page
GET 200, rear-camera capture markup, client-side resizing and a protected
GPT-6.1 Terra response.

### P0-P2 revalidation

Validation run: 2026-11-02, Sweden Central, subscription
`2cf925b6-80cb-4567-abda-5ccd3010aab5`.

| Check | Command or tool | Result |
|---|---|---|
| Python tests | Preserved Python 3.11 environment, `pytest` | PASS, 63 tests |
| Python lint | `ruff check server eval` | PASS |
| Bicep build | `az bicep build --file infra/main.bicep --stdout` | PASS |
| ARM validation | Official `validate-deployment.ps1`, subscription scope | PASS |
| ARM what-if | Official script plus `ResourceIdOnly` inspection | PASS, no resource deletes |
| Policy gate | ARM validation/what-if; Azure MCP policy read returned RBAC 403 | PASS for deployment, MCP inventory unavailable |
| Static RBAC | Existing ACR, Storage, Key Vault and Foundry assignments | PASS, unchanged |
| Reviewed manual | Official Samsung manual and uploaded file SHA-256 | PASS, exact hash match |
| WD80H25BHS live evaluation | GPT-6.1 Terra, 3 images × 3 repeats × 2 targets | PASS, 18/18 located and point-in-box |

The P0-P2 update adds one container environment variable and packages the
reviewed manual in the private application image. It does not create a new
resource or remove an existing resource.

The reviewed evaluation produced no false `not_visible` outcomes. Mean IoU was
0.781 for the lower-front detergent dispenser cover and 0.684 for the
upper-center control panel. Request latency was 20.858 seconds p50 and
26.111 seconds maximum.

ACR remote build `dt5` produced
`visual-guide-api:20261102-p0p2-r1` with digest
`sha256:1fd4ccfc7dfe38e69694cbbbf7ec1fd0d4cfb16ab1f93cc12e6a303d284ef4d1`.
Container App revision `azapi5ovedhtoyg74w--0000009` provisioned successfully
and receives 100% traffic. The deployed smoke test confirmed health, readiness,
login, the reviewed WD80H25BHS mobile page and two `located` targets on
`bespoke1.png`.

### Hybrid issue guidance deployment

Validation run: 2026-11-03, Sweden Central, existing resources unchanged.

| Check | Result |
|---|---|
| Python tests | PASS, 118 tests |
| Python lint | PASS |
| Bicep build | PASS |
| Hybrid issue live evaluation | PASS, six registered/candidate/unknown cases |
| Exact registered wording | Product, intent, two targets and reviewed mode correct |
| Alternate user wording | Product, intent, two targets and reviewed guide correct |
| Candidate without model | Candidate and zero-shot mode correct |
| Unknown product | Unknown and zero-shot locate-only mode correct |
| Four-target issue | Three-target cap and truncation correct |
| Deployed registered E2E | Resolve 200, two reviewed targets located |
| Deployed unknown E2E | Resolve 200, zero-shot target located, no instruction |

ACR remote build `dt6` produced `visual-guide-api:20261102-hybrid` with digest
`sha256:dee75ecb0d112c82c7cbaf699e946f05a8530cf16904dd01f4c7272d6a24caed`.
Container App revision `azapi5ovedhtoyg74w--0000010` is Healthy and receives
100% traffic. The free-form mobile page, legacy reviewed routes and both hybrid
support modes were verified against the deployed HTTPS endpoint.

## Role Assignment Verification

* Status: Verified statically.
* Identity: the API user-assigned managed identity.
* ACR: `AcrPull`, scoped to the generated registry.
* Storage: Blob Data Contributor and Table Data Contributor, scoped to the
  generated storage account.
* Key Vault: Secrets Officer, scoped to the generated vault, as required by the
  selected Azure IaC rules.
* Foundry: Cognitive Services OpenAI User, scoped to existing
  `brk445demo-01`.

Live verification confirmed principal
`de90ee6e-26a5-49aa-a4fc-324a539e1896` has all four role groups at their
resource scopes.

## Deployment Endpoint

* API and mobile demo origin:
  `https://azapi5ovedhtoyg74w.calmcoast-1ab8f441.swedencentral.azurecontainerapps.io`
* Mobile login:
  `https://azapi5ovedhtoyg74w.calmcoast-1ab8f441.swedencentral.azurecontainerapps.io/demo/login`

## 9. Files to Generate

| File | Purpose | Status |
|---|---|---|
| `img/README.md` | Local authorized-image upload instructions | Pending approval |
| `azure.yaml` | AZD service definition | Pending |
| `infra/main.bicep` | Deployment entry point | Pending |
| `infra/main.parameters.json` | AZD parameters | Pending |
| `infra/modules/*.bicep` | Container Apps, ACR, Storage, identity and telemetry | Pending |
| `server/pyproject.toml` | Python dependencies and tools | Pending |
| `server/src/visual_guide/` | FastAPI service and model adapters | Pending |
| `server/Dockerfile` | API container image | Pending |
| `core/` | Pure Kotlin guide contracts | Pending |
| `app-android/` | Android confirmation and AR tracking client | Pending |
| `eval/` | Grounding and refusal evaluation | Pending |
| `.github/workflows/validate.yml` | Local-quality CI | Pending |

## 10. Next Steps

Approve this plan. Execution then creates the ignored image folder, implements
the testable local baseline, validates user-provided images, prepares Azure
infrastructure, invokes `azure-validate`, and deploys only after validation.
