# Visual Guide Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reviewed-product Android filter-replacement guide that uses GPT-6.1 Terra for bounded reasoning and ARCore for local Overlay tracking.

**Architecture:** A pure Kotlin core owns guide and evidence state. FastAPI owns product registration, guide applicability, structured region proposals and server session authority. Android owns consent, camera access, user confirmation and current-frame tracking.

**Tech Stack:** Kotlin Multiplatform, Android Compose, ARCore, ML Kit OCR, Python 3.11, FastAPI, Pydantic, OpenAI Responses API, Azure Identity, pytest and Ruff.

**Spec:** `docs/superpowers/specs/2026-11-01-visual-guide-rebuild-design.md`

## Global Constraints

* Keep `core/src/commonMain` free of Android, ARCore, ML Kit, HTTP and Azure SDK dependencies.
* Use GPT-6.1 Terra as the default inference model and GPT-6.1 Sol only for selected adjudication.
* Use strict JSON Schema outputs and absolute pixel `XYXY` coordinates.
* Never upload continuous camera frames or log image, token or pairing-code bodies.
* Hide Overlay on tracking loss, pause, product change, state change and step change.
* Publish real-product assets only with exact model codes, official sources and human review.
* Keep VELA customer assets outside the root Git repository and use them only as prior evidence.

## Review Focus

* Reject a guide whose official source is relevant but does not list the exact applicable model.
* Reject located regions with out-of-bounds coordinates or a point outside the box.
* Reject stale, duplicate, wrong-step and wrong-product evidence.
* Hide Overlay immediately when tracking is paused, stale or attached to another generation.
* Return `uncertain` rather than select a candidate when independent proposals do not agree.

---

### Task 1: Fresh project scaffold and core guide contracts

**Files:**

* Create: `settings.gradle.kts`
* Create: `build.gradle.kts`
* Create: `gradle.properties`
* Create: `core/build.gradle.kts`
* Create: `core/src/commonMain/kotlin/guide/Contracts.kt`
* Create: `core/src/commonMain/kotlin/guide/GuideEngine.kt`
* Test: `core/src/commonTest/kotlin/guide/GuideEngineTest.kt`

**Interfaces:**

* Consumes: no earlier task interfaces.
* Produces: `Guide`, `GuideStep`, `CaptureScope`, `EvidenceSource`, `GuideEngine`, `GuideEngine.observe`, `GuideEngine.advanceManual`, `GuideEngine.setTracking`.

- [ ] **Step 1: Write failing state-machine tests**

Cover current-step-only advance, duplicate evidence, stale scope, tracking loss,
product change and distinct evidence sources.

- [ ] **Step 2: Run the focused core tests**

Run: `.\gradlew.bat :core:jvmTest`

Expected: FAIL because the core contracts do not exist.

- [ ] **Step 3: Implement the minimal pure Kotlin contracts and reducer**

Use immutable input values and a single-owner reducer. Tracking or scope changes
must increment an evidence generation.

- [ ] **Step 4: Run the focused core tests**

Run: `.\gradlew.bat :core:jvmTest`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat(build): add visual guide core contracts`

### Task 2: Reviewed product and guide registry

**Files:**

* Create: `server/pyproject.toml`
* Create: `server/src/visual_guide/contracts.py`
* Create: `server/src/visual_guide/registry.py`
* Create: `server/src/visual_guide/asset_validation.py`
* Test: `server/tests/test_registry.py`
* Test: `server/tests/test_asset_validation.py`

**Interfaces:**

* Consumes: the guide field names defined in Task 1.
* Produces: `ProductManifest`, `ReviewedGuide`, `GuideStep`, `load_reviewed_registry(path: Path) -> ReviewedRegistry`.

- [ ] **Step 1: Write failing registry validation tests**

Cover exact model matching, official HTTPS source, review metadata, unique step
IDs, state transitions, bounded pixel dimensions and refusal of unreviewed data.

- [ ] **Step 2: Run the registry tests**

Run: `uv run --project server pytest server/tests/test_registry.py server/tests/test_asset_validation.py -q`

Expected: FAIL because the registry modules do not exist.

- [ ] **Step 3: Implement Pydantic contracts and fail-closed loading**

Do not invent defaults for model codes, sources, coordinates or review state.

- [ ] **Step 4: Run the registry tests and Ruff**

Run: `uv run --project server pytest server/tests/test_registry.py server/tests/test_asset_validation.py -q`

Run: `uv run --project server ruff check server/src server/tests`

Expected: both commands pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add reviewed product registry`

### Task 3: Foundry model gateway and structured region proposals

**Files:**

* Create: `server/src/visual_guide/model_gateway.py`
* Create: `server/src/visual_guide/region_proposal.py`
* Create: `server/src/visual_guide/images.py`
* Test: `server/tests/test_model_gateway.py`
* Test: `server/tests/test_region_proposal.py`

**Interfaces:**

* Consumes: `ReviewedGuide`, `GuideStep` from Task 2.
* Produces: `ModelGateway.propose_region(request: RegionRequest) -> RegionProposal`, `RegionStatus`, `PixelPoint`, `PixelBox`.

- [ ] **Step 1: Write failing structured-output and image-boundary tests**

Cover `located`, `not_visible`, `uncertain`, oversized images, unsupported media,
out-of-bounds boxes and points outside boxes.

- [ ] **Step 2: Run the focused server tests**

Run: `uv run --project server pytest server/tests/test_model_gateway.py server/tests/test_region_proposal.py -q`

Expected: FAIL because the gateway and proposal modules do not exist.

- [ ] **Step 3: Implement a gateway interface and deterministic fake**

Tests must use a fake gateway. The production adapter uses Entra authentication,
the Responses API, strict schemas and a configurable deployment defaulting to
`gpt-6.1-terra`.

- [ ] **Step 4: Run focused tests and Ruff**

Run: `uv run --project server pytest server/tests/test_model_gateway.py server/tests/test_region_proposal.py -q`

Run: `uv run --project server ruff check server/src server/tests`

Expected: both commands pass without a live Azure call.

- [ ] **Step 5: Commit**

Commit message: `feat: add structured region proposals`

### Task 4: Guide applicability and sufficiency gate

**Files:**

* Create: `server/src/visual_guide/guide_gate.py`
* Test: `server/tests/test_guide_gate.py`

**Interfaces:**

* Consumes: `ProductManifest`, `ReviewedGuide` and `ModelGateway`.
* Produces: `GateDecision` with `applicable`, `ambiguous`, `inapplicable`; `decide_guide_fit(...) -> GateDecision`.

- [ ] **Step 1: Write failing applicability tests**

Cover exact model, wrong family, absent source quote, ambiguous current state,
missing evidence and an applicable reviewed guide.

- [ ] **Step 2: Run the gate tests**

Run: `uv run --project server pytest server/tests/test_guide_gate.py -q`

Expected: FAIL because `guide_gate` does not exist.

- [ ] **Step 3: Implement deterministic checks before model judgment**

Verify the cited quote against the supplied official document text. Never allow
an ambiguous or inapplicable decision to produce a region request.

- [ ] **Step 4: Run the gate tests**

Run: `uv run --project server pytest server/tests/test_guide_gate.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: gate guides by verified applicability`

### Task 5: Region consensus and conditional crop

**Files:**

* Create: `server/src/visual_guide/consensus.py`
* Test: `server/tests/test_consensus.py`

**Interfaces:**

* Consumes: `RegionProposal` from Task 3.
* Produces: `aggregate_regions(proposals: Sequence[RegionProposal]) -> RegionDecision`, `CropRequest`.

- [ ] **Step 1: Write failing consensus tests**

Cover majority status, median point and box, wrong-component proposals, IoU below
the threshold, missing proposals and a single allowed crop retry.

- [ ] **Step 2: Run the consensus tests**

Run: `uv run --project server pytest server/tests/test_consensus.py -q`

Expected: FAIL because `consensus` does not exist.

- [ ] **Step 3: Implement agreement and refusal logic**

Return `uncertain` when fewer than two of three valid proposals agree or pairwise
IoU is below the configured threshold. Coordinate remapping belongs in code.

- [ ] **Step 4: Run the consensus tests**

Run: `uv run --project server pytest server/tests/test_consensus.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add region consensus gating`

### Task 6: Authenticated API and server-owned sessions

**Files:**

* Create: `server/src/visual_guide/main.py`
* Create: `server/src/visual_guide/routes.py`
* Create: `server/src/visual_guide/sessions.py`
* Test: `server/tests/test_api.py`
* Test: `server/tests/test_sessions.py`

**Interfaces:**

* Consumes: registry, gate, gateway and consensus services.
* Produces: `/v1/catalog`, `/v1/guides/resolve`, `/v1/regions/propose`, `/v1/sessions`, `/v1/sessions/{id}/events`, `/v1/sessions/{id}/verify`.

- [ ] **Step 1: Write failing authentication, ownership and replay tests**

Cover missing token, wrong owner, duplicate event replay, event ID reuse, wrong
step, expired proof and unsupported product refusal.

- [ ] **Step 2: Run focused API tests**

Run: `uv run --project server pytest server/tests/test_api.py server/tests/test_sessions.py -q`

Expected: FAIL because the API does not exist.

- [ ] **Step 3: Implement the minimal authenticated API**

Use repository interfaces for persistence. Do not add local unauthenticated
fallback routes.

- [ ] **Step 4: Run all server tests and Ruff**

Run: `uv run --project server pytest server/tests -q`

Run: `uv run --project server ruff check server/src server/tests`

Expected: all commands pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add authenticated visual guide API`

### Task 7: Android confirmation and secure API client

**Files:**

* Create: `app-android/build.gradle.kts`
* Create: `app-android/src/main/AndroidManifest.xml`
* Create: `app-android/src/main/java/guide/app/MainActivity.kt`
* Create: `app-android/src/main/java/guide/app/GuideCoordinator.kt`
* Create: `app-android/src/main/java/guide/app/ApiClient.kt`
* Create: `app-android/src/main/java/guide/app/SecureDeviceStore.kt`
* Test: `app-android/src/test/java/guide/app/GuideCoordinatorTest.kt`
* Test: `app-android/src/test/java/guide/app/ApiContractTest.kt`

**Interfaces:**

* Consumes: core contracts and the `/v1` API from Task 6.
* Produces: product resolution, explicit snapshot consent, candidate confirmation and server-approved step progression UI.

- [ ] **Step 1: Write failing coordinator and API contract tests**

Cover no-consent snapshot refusal, no silent offline fallback, unknown product,
uncertain region, confirmation reset on new image and token-origin binding.

- [ ] **Step 2: Run Android unit tests**

Run: `.\gradlew.bat :app-android:testDebugUnitTest`

Expected: FAIL because the Android module does not exist.

- [ ] **Step 3: Implement the Compose flow and secure client adapters**

Do not open the camera until the user enters a supported guide flow. Do not
persist photos.

- [ ] **Step 4: Run Android unit tests**

Run: `.\gradlew.bat :app-android:testDebugUnitTest`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add Android guide confirmation flow`

### Task 8: ARCore tracking and Overlay invalidation

**Files:**

* Create: `app-android/src/main/java/guide/app/ArTrackingController.kt`
* Create: `app-android/src/main/java/guide/app/OverlayRenderer.kt`
* Create: `app-android/src/main/java/guide/app/TrackingEvidenceGate.kt`
* Test: `app-android/src/test/java/guide/app/TrackingEvidenceGateTest.kt`

**Interfaces:**

* Consumes: confirmed `RegionDecision`, guide generation and current step.
* Produces: current-frame `OverlayFrame` only for full tracking of the confirmed generation.

- [ ] **Step 1: Write failing tracking-evidence tests**

Cover pause, tracking loss, wrong target, stale frame, state change, step change
and product change.

- [ ] **Step 2: Run the focused tests**

Run: `.\gradlew.bat :app-android:testDebugUnitTest --tests '*TrackingEvidenceGateTest'`

Expected: FAIL because tracking classes do not exist.

- [ ] **Step 3: Implement tracking ownership and invalidation**

ARCore owns the camera. Never replace an invalid pose with fixed screen
coordinates or the last known pose.

- [ ] **Step 4: Run unit tests, lint and APK compilation**

Run: `.\gradlew.bat :core:jvmTest :app-android:testDebugUnitTest :app-android:lintDebug :app-android:assembleDebug`

Expected: tests pass, lint has no errors and a debug APK is produced.

- [ ] **Step 5: Commit**

Commit message: `feat: track confirmed guide regions`

### Task 9: Evaluation harness and CI

**Files:**

* Create: `eval/run_eval.py`
* Create: `eval/tests/test_eval.py`
* Create: `.github/workflows/validate.yml`
* Create: `docs/evaluation.md`

**Interfaces:**

* Consumes: recorded gate, proposal, tracking and verification observations.
* Produces: guide-fit accuracy, point-in-ground-truth, IoU, refusal, stale Overlay, latency and cost reports.

- [ ] **Step 1: Write failing metric tests**

Cover empty datasets, supported and unsupported cases, missing proposals, stale
Overlay frames, state-verification errors and insufficient participant counts.

- [ ] **Step 2: Run evaluation tests**

Run: `uv run --project server pytest eval/tests -q`

Expected: FAIL because the evaluator does not exist.

- [ ] **Step 3: Implement deterministic metrics and CI**

CI uses fake model adapters and synthetic fixtures. Live Foundry calls run only
in an explicitly approved evaluation job.

- [ ] **Step 4: Run the complete local validation**

Run: `uv run --project server pytest server/tests eval/tests -q`

Run: `uv run --project server ruff check server/src server/tests eval`

Run: `.\gradlew.bat :core:jvmTest :app-android:testDebugUnitTest :app-android:lintDebug :app-android:assembleDebug`

Expected: all checks pass.

- [ ] **Step 5: Commit**

Commit message: `test: add visual guide quality gates`

### Task 10: First reviewed product vertical slice

**Files:**

* Create: `assets/products/<product-id>/<version>/manifest.json`
* Create: `assets/products/<product-id>/<version>/guide.json`
* Create: `assets/products/<product-id>/<version>/references/`
* Test: `server/tests/test_first_product.py`

**Interfaces:**

* Consumes: user-provided model code, official source, reviewed state photos and ground-truth regions.
* Produces: one published filter-replacement scenario usable by the API and Android app.

- [ ] **Step 1: Add tests for the reviewed product package**

Assert exact models, official source, image dimensions, state transitions,
component IDs, review metadata and bounded coordinates.

- [ ] **Step 2: Run the product test before adding assets**

Run: `uv run --project server pytest server/tests/test_first_product.py -q`

Expected: FAIL because reviewed product inputs have not been supplied.

- [ ] **Step 3: Add only reviewed, licensed product assets**

Do not use customer-lab photos or invent model IDs, instructions or coordinates.

- [ ] **Step 4: Run full validation and physical-device checks**

Separate APK compilation, emulator behavior, physical Galaxy tracking and actual
product completion results in the report.

- [ ] **Step 5: Commit**

Commit message: `feat: add first reviewed filter guide`
