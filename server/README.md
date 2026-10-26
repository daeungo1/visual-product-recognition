---
title: Visual Guide API
description: Separate local synthetic demo and authenticated real Azure visual-guide adapters
ms.date: 2026-10-21
ms.topic: how-to
---

## Modes and boundaries

`VISUAL_GUIDE_MODE=local` is the explicit default. The seven original SQLite demo tests
and unversioned routes remain local-only. `VISUAL_GUIDE_MODE=cloud` exposes `/v1`
and never falls back to SQLite, invented products or unconditional AI success.
The shared contract is [cloud-api-contract.md](../docs/cloud-api-contract.md).

Cloud mode uses managed identity for Cosmos, private Blob, AI Search and Azure OpenAI.
One-time invitations and 24-hour device tokens are opaque random values stored only
as SHA-256 hashes. PoC pairing is not enterprise SSO. Sessions are owner-scoped.
Their state, replay ledger and step-scoped 30-second proofs share one Cosmos item and
one conditional ETag write. Manual, OCR and VLM sources remain distinct. OCR currently
requires the entire normalized display text to equal the authoritative expected state.
VLM verification never advances a session without a subsequent accepted event.

Only reviewed registered references enter Search. A 768-dimensional, L2-normalized,
pinned SigLIP2 vector retrieves candidates; actual VLM query/reference comparison must
also match. Scores are not probabilities. Unknown or uncertain identity remains unknown.
Draft generation never publishes. Source text, images and instructions from clients are
untrusted model input, not authority to override server steps.

Images are bounded to 2 MiB decoded and 8 megapixels, JPEG/PNG only. Bodies are bounded
before JSON parsing. CPU inference and VLM calls have separate bounded gates; model
admission is never held while waiting for the VLM network response. A timed-out
operation keeps its slot until it actually exits. Retrying while busy returns 429.
Cosmos/Search/OpenAI SDK failures return explicit 503/504 responses. `/healthz` is liveness;
`/readyz` loads the actual local model and checks Cosmos containers and Search data-plane
access, document count and a filtered 768-D vector query. Schema inspection/creation stays
in the owner CLI. Runtime needs Search Index Data Contributor, not Search Service Contributor.
It transparently reports `search_document_count`, including zero for a prepared empty index;
positive indexing is an activation requirement, not a readiness bootstrap dependency.
No inference dependencies or configuration means not ready, never a local-mode fallback.

Photos are sent to configured Azure OpenAI for requested identification/verification only.
The API does not persist query photos or request bodies. Reference assets are stored privately.
Do not enable SDK HTTP body/debug logging. GlobalStandard model processing is not a
Japan-only residency guarantee. Obtain consent and assess cloud retention/residency before
using real photos. Console logs contain dependency/error types, never image/token/code bodies.

## Configuration

Set these environment variables on the existing cloud deployment:

```text
VISUAL_GUIDE_MODE=cloud
AZURE_CLIENT_ID=<user-assigned managed identity client ID>
COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
COSMOS_DATABASE=visualguide
AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
BLOB_CONTAINER=assets
AZURE_SEARCH_ENDPOINT=https://<service>.search.windows.net
AZURE_SEARCH_INDEX=product-images
AZURE_OPENAI_ENDPOINT=https://<account>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_VERIFY_DEPLOYMENT=guide-verify
AZURE_OPENAI_AUTHOR_DEPLOYMENT=guide-author
EMBEDDING_MODEL_PATH=/opt/models/siglip2-base-patch16-224
PORT=8000
```

Cosmos containers `catalog`, `sessions`, `devices`, `invites` each use partition `/id`.
TTL must be enabled on `devices` and `invites`. The service checks expiry explicitly,
not just eventual TTL deletion. Role assignments and resources are provisioned separately;
neither the API nor the owner helper creates Azure resources or changes RBAC.

## Local validation

From the repository directory on Windows:

```powershell
uv --native-tls sync --project .\server --python C:\Users\daeungo\AppData\Local\Programs\Python\Python311\python.exe --default-index https://packagefeedproxy.microsoft.io/pypi/simple/ --extra cloud
.\server\.venv\Scripts\python.exe -m pytest .\server\tests -q
.\server\.venv\Scripts\python.exe -m ruff check .\server\src .\server\tests .\pipeline\provision_cloud.py
```

`cloud` installs Azure/OpenAI SDKs without Torch. `inference` adds Torch/Transformers and is
installed in the Linux image only. Tests use explicit adapter doubles, not pretend cloud
results. A passing test suite does not prove actual inference, Search, Cosmos or deployment.

## Owner registration and pairing

Authenticate the owner using Azure CLI first. The helper explicitly uses
`AzureCliCredential(process_timeout=120)`; it does not use app secrets or the container UAMI.
The same endpoint environment variables above must be available in the owner shell.
Run the helper with the already-synced server environment, not an implicit package sync.
Create a private, ignored output directory first, for example `server\data\private`.
Restrict its Windows ACL to the operator. Output must be a new file covered by `.gitignore`.
Never publish it, copy it into an APK or print its pairing code in logs.

```powershell
New-Item -ItemType Directory -Force .\server\data\private
.\server\.venv\Scripts\python.exe .\pipeline\provision_cloud.py --seed-demo --prepare-only
```

Run preparation after base resources exist but before application deployment. It needs no
API URL, token or output file, creates no invitations, and does not load Torch locally.
Then build/deploy the application separately. Once its empty-index readiness succeeds:

```powershell
.\server\.venv\Scripts\python.exe .\pipeline\provision_cloud.py --activate-only --api-url https://<api-origin> --output .\server\data\private\device-pair.json
.\server\.venv\Scripts\python.exe .\pipeline\provision_cloud.py --issue-device-code --api-url https://<api-origin> --code-valid-hours 168 --output .\server\data\private\later-device-pair.json
```

Seeding validates the **existing** `assets\demo-target.png`, `assets\panel_map.json` and
`DEMO_GUIDE`, uploads the immutable content-addressed PNG and reviewed typed Cosmos
documents, and creates the exact HNSW cosine Search index if missing. Activation issues
an ephemeral admin invitation, pairs with the deployed API, and calls actual `/v1/admin/reindex`.
That endpoint computes embeddings inside the container. The helper revokes its temporary
admin token afterward and writes a separate device invitation only to the private output.
No normal device invite is issued until indexing succeeds with a positive indexed count.
Later `--issue-device-code` checks that the index contains documents. Omitting `--prepare-only`
with `--seed-demo` or `--register-real` performs preparation and activation in one command.
Re-running identical registration is safe; differing reviewed assets are never overwritten.
Use new versioned guide/target IDs for changes.

Real assets require user-owned local files and explicit human review:

```powershell
.\server\.venv\Scripts\python.exe .\pipeline\provision_cloud.py --register-real --api-url https://<api-origin> --guide <guide.json> --panel-map <panel_map.json> --reference <reference.png> --product-id <registered-product-id> --model "<exact-applicable-model>" --category aircon --target-kind remote --source-url https://<official-source> --reviewed --output .\server\data\private\reviewed-device-pair.json
```

The guide keeps the shared `id`, `target_id`, `title`, `demo`, `steps` format, with
`demo=false` for real products. The panel map keeps the original pixel-dimension,
physical-width and normalized-array geometry format, with `demo=false`. The helper
checks actual reference dimensions, rectangle bounds, positive area, unique steps,
button IDs, applicable model, official source metadata and review confirmation.
The connected model response converts those exact arrays to `left/top/right/bottom`.
It does not invent real-product identities, procedures or screen coordinates.

## Private-network bootstrap without a local VPN

If Cosmos and Blob public networking is disabled, an otherwise authorized workstation
cannot seed them. Do not enable public networking to work around the firewall.
Use a manual job in the VNet-integrated Container Apps environment with a dedicated setup
managed identity. The job reuses `pipeline\provision_cloud.py` registration/activation
helpers with `ManagedIdentityCredential`, not Azure CLI credentials. The existing owner
CLI remains useful from an authorized VNet/VPN environment.

Before the parent builds the Linux image, generate the curated context locally:

```powershell
.\server\.venv\Scripts\python.exe .\pipeline\prepare_bootstrap_context.py
```

This copies exactly the canonical owned `assets\demo-target.png`, `assets\panel_map.json`
and `pipeline\provision_cloud.py` into ignored `server\runtime_bootstrap`.
It performs no Azure calls, dependency installation or model downloads. The Docker
allowlist admits only those three generated files, copied to `/app/assets` and `/app/pipeline`.
Do not place private output files in this generated context.

Override the job command, not the API's default startup command:

```text
command: /opt/venv/bin/python
arguments: -m guide_api.bootstrap
```

Every operation requires the following existing resource settings. The four endpoints
are mandatory because the common `Settings` validates them even when an operation does
not directly use all four services:

```text
AZURE_CLIENT_ID=<dedicated setup managed identity client ID, not the API identity>
COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
COSMOS_DATABASE=visualguide
AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net
BLOB_CONTAINER=assets
AZURE_SEARCH_ENDPOINT=https://<service>.search.windows.net
AZURE_SEARCH_INDEX=product-images
AZURE_OPENAI_ENDPOINT=https://<account>.openai.azure.com/
BOOTSTRAP_OPERATION=prepare
```

The setup identity needs AcrPull, Blob Data Contributor, Search Service Contributor,
Search Index Data Contributor and Cosmos native Data Contributor. These assignments,
private endpoints, DNS and VNet-integrated application/job deployment are separate parent
infrastructure operations; the bootstrap code does not provision or weaken networking.

Run `prepare` first. It registers the synthetic assets and exact Search schema with no
API URL, token or device invite. Leave invitation variables unset for this operation.
Then deploy the application and wait for real readiness. Run the same job image with:

```text
BOOTSTRAP_OPERATION=activate
BOOTSTRAP_API_URL=https://<actual-api-origin>
```

Activation creates a short-lived admin invitation internally, pairs with the actual API,
calls real `/v1/admin/reindex`, verifies positive indexing and revokes its temporary admin
token. It does not load Torch or compute embeddings in the bootstrap process.

To prepare a phone invitation, first create a private ignored directory and restrict its
Windows ACL to the operator. Generate a new local file:

```powershell
.\server\.venv\Scripts\python.exe .\pipeline\prepare_bootstrap_context.py --issue-device-code --api-url https://<actual-api-origin> --code-valid-hours 168 --output .\server\data\private\private-device-pair.json
```

Omit `--api-url` if the origin is not known yet; the private file then has `api_url=""`,
which the operator can update locally afterward. The file retains exactly
`api_url`, `code`, `scope=device`, `expires_at`. It is created exclusively, never overwritten.
The command prints **only** JSON containing `BOOTSTRAP_DEVICE_INVITE_HASH` (SHA-256 hex)
and `BOOTSTRAP_INVITE_EXPIRES_AT` (Unix epoch seconds). Plaintext code never goes to the
control plane or Azure logs. The default validity is 24 hours; the maximum is 168.

Pass those two printed values to the job, either together with `activate` or later with:

```text
BOOTSTRAP_OPERATION=invite
BOOTSTRAP_DEVICE_INVITE_HASH=<printed lowercase 64-character SHA-256 digest>
BOOTSTRAP_INVITE_EXPIRES_AT=<printed epoch seconds>
```

`invite` checks positive Search document count before writing the normal device invitation;
it needs no API URL and does not reindex. `activate` writes an optional device invitation
only after successful indexing. Both validate remaining expiry and persist only the
canonical hashed invite document. Logs contain operation/status/counts, never phone codes,
hashes, tokens or photos.

Expected Azure/HTTP/domain failures log only bounded status codes, provider error codes,
validated activity/request IDs and numeric Cosmos substatus. Explicit exception causes
preserve an upstream Cosmos 403 even if an adapter maps it to API 503. Exception messages,
response bodies and request headers are not logged. Expected service failures exit 1;
configuration/file errors exit 2. Unexpected programming errors propagate instead of being
hidden by a generic exception handler. Use the activity ID for service-side diagnostics;
do not weaken private networking or switch to keys to investigate a firewall failure.

Prepare/registration is idempotent. Repeating an unconsumed invitation is also idempotent.
A hash-only claim in `catalog` prevents job retries from recreating a consumed/deleted
invitation. If a job fails between reserving its hash and writing its invitation, it fails
closed: generate a fresh local code rather than reminting the old one.

## Linux image and actual-cloud validation

The build context is **server only**. The allowlist `.dockerignore` excludes environments,
tests, caches, databases, credentials and every parent directory. Runtime never reads
`..\assets`: references and maps come from Blob/Cosmos.

`Dockerfile` uses Python 3.11 slim, installs official CPU Torch 2.8.0 first, then declared
cloud/inference extras. It downloads public Apache-2.0
`google/siglip2-base-patch16-224` at revision
`75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`, with no user credentials. Only configuration,
image preprocessing and safetensors files are baked into `/opt/models/siglip2-base-patch16-224`.
Runtime is offline for Hugging Face, disables remote code, uses a nonroot UID 10001,
has writable `/app/runtime`, and runs exactly one Uvicorn worker. No startup installation
or model download occurs. Do not scale worker count within the 2-vCPU/4-GiB container.

Image build, paid deployment and actual cloud smoke tests are separate operator steps.
After deployment: check readiness, seed, identify the actual registered reference and an
unregistered image, verify visible passing/failing/uncertain display crops, consume/expire
proofs, test cross-owner access and exact replay, and inspect the resulting Cosmos/Search
data. Report image compilation, real AI/cloud smoke, Android build, emulator, physical
Galaxy and real-product validation separately. None is implied by unit tests.
