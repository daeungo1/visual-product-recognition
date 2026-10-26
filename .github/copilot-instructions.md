---
description: "Preserve the Visual Guide core, adapter boundaries, demo labeling and evidence-based validation"
---

# Visual Guide development boundaries

## Core and adapters

* Keep `core/src/commonMain` independent of Android, ARCore, ML Kit, HTTP and Azure SDKs.
* After the initial PoC baseline is verified, treat core contracts and state transitions as stable.
  Do not modify them to accommodate a platform integration without explicit user approval.
* Implement platform and network behavior in outer adapters, not the core.
* Keep Kotlin state contracts and Python API payloads consistent through tests.

## Guidance correctness

* Never substitute fixed screen coordinates for valid tracked target coordinates.
* For moving targets, show highlights only during current full image tracking.
* Hide guidance on target loss, paused tracking, last-known-pose tracking and target changes.
* Reject stale, duplicated or wrong-step evidence. Preserve manual versus automatic completion.
* Treat unknown identity and uncertain visual verification as explicit non-success states.

## Assets and privacy

* Keep synthetic demo assets visibly labeled and separate from real Samsung product support.
* Do not invent product model IDs, official instructions, button coordinates or measured accuracy.
* Publish real-product guides only with a source, applicable model and human review.
* Do not embed cloud keys, client secrets or user tokens in the APK, repository or logs.
* Do not upload raw camera frames continuously or retain photos without a defined consent policy.

## Validation and deployment

* Run relevant core tests, API tests, lint and the Android build after behavior changes.
* Report APK compilation, emulator tests, physical Galaxy tests and actual-product tests separately.
* The current SQLite API is local demo infrastructure, not production cloud persistence.
* Do not deploy the unauthenticated local demo API as a production service.
* Obtain separate infrastructure-generation and paid-resource-deployment approvals.
* Do not commit or push into the unrelated parent Git repository automatically.
