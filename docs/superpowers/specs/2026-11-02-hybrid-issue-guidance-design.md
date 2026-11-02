---
title: Hybrid Issue-Driven Visual Guidance Design
description: Dynamic user issues and targets across registered and unregistered products
---

## Intent

Replace the fixed WD80H25BHS target checkboxes with an issue-driven flow. A
user describes the product, current state and desired help in natural language,
then confirms Agent-proposed targets before the app grounds each target in the
photo.

The system supports multiple product models without weakening the reviewed
manual gate:

* Registered exact products can receive source-supported location and guide
  steps.
* Product candidates must be confirmed before guide use.
* Unregistered products can use experimental zero-shot location only.
* Unregistered products never receive instructions presented as official
  procedures.

## Goals

* Accept free-form Korean product notes, issues and target names.
* Extract at most three independent targets from one issue.
* Allow the user to add, remove or rename proposed targets.
* Resolve exact products when a model code or reviewed registry match exists.
* Represent candidate and unknown products explicitly.
* Preserve the WD80H25BHS reviewed path as the first registered product.
* Reuse independent target consensus, partial success and adaptive crop.
* Keep issue planning separate from coordinate generation.
* Scale registry loading to multiple manufacturers and model folders.
* Evaluate product resolution, target extraction and grounding independently.

## Non-goals

* Claiming official procedures for an unregistered product.
* Automatically trusting manuals found through unrestricted web search.
* Inferring an exact model from visual similarity alone.
* Generating more than three targets from one issue.
* Adding SAM, GPU inference, video tracking or AR in this phase.
* Persisting request images on the server.
* Replacing human review for product-manual applicability.

## Approaches

### Open-world one-shot

One model identifies the product, invents targets, selects instructions and
returns all coordinates. This is the smallest implementation but recreates the
VELA wrong-document failure mode and makes each failure difficult to evaluate.
It is rejected.

### Registry-only dynamic targets

Users can enter arbitrary issues, but every product must already be registered.
This provides the highest procedural accuracy but blocks exploration with new
products. It remains the reviewed path inside the selected architecture.

### Hybrid registered and zero-shot

The selected approach separates product status from visual grounding. Registered
products use reviewed component and guide evidence. Candidate products require
confirmation. Unknown products receive visible-part location only and a request
for a model-label photo or official manual.

## User flow

```text
Product note or model code
  + user issue or requested target
  + optional current state
  + photo
    -> issue resolution
    -> product status and candidates
    -> proposed target chips
    -> user confirms product and targets
    -> reviewed or zero-shot grounding
    -> target overlays
    -> source-supported guide or onboarding request
```

The browser keeps the selected image locally between resolution and grounding.
It resubmits the image after confirmation. The server does not retain it.

Target renaming changes display text only. It cannot change canonical aliases,
relative regions, registry IDs or manual evidence. Adding a new target sends
the user's phrase back through bounded target planning; the client cannot
author a trusted `DynamicTargetSpec`.

## Product modes

### Registered

An exact model maps to one reviewed `ProductManifest` and an applicable manual.
Targets first resolve to reviewed `ComponentSpec` entries. Related reviewed
guide steps can be returned with page evidence.

A registered product may contain a mixture of reviewed and zero-shot targets.
Reviewed targets can participate in guide steps. Zero-shot targets remain
location-only even when another target in the same request is reviewed. Every
target carries its own support source so mixed results cannot inherit reviewed
status from one target.

### Candidate

Product notes, OCR or visual category evidence match more than one exact
product. The response contains candidates and requires explicit user selection.
No product-specific instruction is returned before confirmation.

Confirmation requires both the selected stable `product_id` and one exact model
code from that product. Product-family confirmation alone cannot approve a
manual or guide.

### Unknown

No exact reviewed product is resolved. The issue planner can propose visible
target descriptions, aliases and broad relative regions. The response is
clearly marked `zero_shot_locate_only`. The app requests a model-label photo or
official manual for full onboarding.

## Two-stage API

### Resolve issue

`POST /v1/issues/resolve`

The request contains:

* `product_hint`
* optional `model_code`
* `user_issue`
* optional `current_state`
* optional image input

The response contains:

* `product_status`: `registered`, `candidate` or `unknown`
* product candidates with evidence
* normalized issue intent
* `DynamicTargetSpec[]`
* guide candidates for registered products
* confirmation requirements
* support mode: `reviewed_guide` or `zero_shot_locate_only`

GPT-6.1 Terra performs issue and target planning with strict structured output.
It does not return pixel geometry in this stage.

`guide_candidates` contains identifiers, titles, applicability state and source
references only. It does not expose an actionable instruction.

### Ground confirmed targets

`POST /v1/issues/ground`

The request contains the confirmed product selection, issue intent, target
specifications and the image. The server revalidates registered IDs against the
registry. Each target runs independently through whole-image consensus and one
uncertain-only adaptive crop.

The response contains target grounding results plus reviewed current-step
instructions only after exact product, manual, guide, state and target
applicability pass. Zero-shot targets never receive reviewed instructions.

## Domain contracts

### IssueResolutionRequest

```text
product_hint: string | null
model_code: string | null
user_issue: string
current_state: string | null
image: optional validated image
```

### DynamicTargetSpec

```text
target_id
display_name
canonical_name
aliases
purpose
relative_region
source: registry | user_issue | zero_shot
registry_component_id: string | null
manual_evidence: source reference | null
```

Target IDs are request-scoped. Registered component IDs remain stable across
requests. Duplicate canonical targets are rejected.

### ProductCandidate

```text
product_id
manufacturer
display_name
exact_model_codes
evidence_source
confidence_band: high | medium | low
```

The API does not expose uncalibrated floating-point model confidence as a
safety decision.

### IssueResolution

```text
product_status
support_mode
product_candidates
issue_intent
targets
guide_candidates
requires_product_confirmation
requires_target_confirmation
next_capture_instruction
```

## Issue planner

The planner receives the user's wording, optional product evidence and a
registry summary. It performs four bounded operations:

1. Normalize the user's desired outcome.
2. Split compound requests into at most three atomic targets.
3. Map targets to reviewed components when evidence exists.
4. Produce zero-shot target descriptions only when no reviewed mapping exists.

The planner may suggest product candidates but cannot approve manual
applicability. The deterministic registry gate owns that decision.

The optional image helps Terra infer product category, visible state and target
phrasing. Image text or visual similarity can create candidates but cannot
establish exact product identity. An OCR or VLM-read model code must be
confirmed by the user before exact-model resolution.

## Registry generalization

The loader already discovers manufacturer and product folders. Runtime
construction must stop hardcoding `WD80H25BHS` and one manual path.

Each product folder provides:

* exact model codes
* manufacturer and product family
* reviewed manuals and asset locators
* component aliases and relative regions
* issue-intent to guide mappings
* optional product exemplar metadata

The registry exposes:

```text
resolve_exact_model(model_code)
search_product_candidates(product_hint)
resolve_component_alias(product_id, user_target)
find_guide_candidates(product_id, issue_intent, current_state)
manual_asset(product_id, manual_id)
```

Issue mappings are reviewed records with:

```text
issue_intent
accepted user aliases
required current states
guide_id
eligible step IDs
required and optional component IDs
```

Terra proposes a normalized intent. The registry performs deterministic
intent-to-guide and state-to-step selection. If no reviewed mapping matches,
the result is `guide_not_found` or `state_unknown`, not a generated procedure.

Product candidate ranking uses evidence bands:

* `high`: exact normalized model-code match in the reviewed registry
* `medium`: reviewed product name, family or alias match
* `low`: image category or visual similarity only

Only one `high` exact-model match can produce registered mode without a
candidate choice. `medium` and `low` matches require confirmation. No candidate
above `low`, or conflicting evidence, produces unknown mode.

Raw manual delivery remains separate from the checked-in reviewed metadata.
The existing hash-verified Samsung staging path becomes one implementation of a
generic `ManualAssetProvider`.

## Dynamic grounding

Registered targets use the reviewed canonical name, aliases, relative region
and source evidence. Zero-shot targets use planner-produced aliases and broad
relative regions, but no manual evidence.

Both modes reuse:

* one target per model proposal
* three proposals per target
* two-of-three spatial agreement
* no retry for agreed `not_visible`
* one crop retry only for `uncertain`
* deterministic root-coordinate remapping
* target-level failure isolation
* partial success

Every result records whether it came from `reviewed` or `zero_shot` grounding.

## Guide behavior

Registered mode can return a reviewed step only when exact product, manual,
guide, state and target applicability all pass.

Candidate mode returns no instruction until the user confirms an exact product.

Unknown mode returns:

* experimental target location
* target-specific uncertainty or retake guidance
* model-label capture request
* official manual upload request

It does not return product-specific manipulation instructions.

## Mobile UI

The fixed product heading and target checkboxes are replaced by:

1. Optional product memo or model code.
2. Required problem or requested target text.
3. Optional current-state text.
4. Camera capture or photo selection.
5. `Analyze problem`.
6. Product candidate selection when needed.
7. Editable target chips.
8. `Find confirmed targets`.
9. Target-colored overlays and mode-specific guidance.

The existing WD80H25BHS guide can prefill issue suggestions but is no longer
hardcoded as the only runtime product.

## Error and abstention states

The public API distinguishes:

* `unsupported_product`
* `product_confirmation_required`
* `manual_not_applicable`
* `guide_not_found`
* `state_unknown`
* `target_not_mapped`
* `target_not_visible`
* `target_ambiguous`
* `model_unavailable`

Expected user or registry failures return client-safe 4xx responses. Service
availability failures return 5xx responses and do not masquerade as visual
uncertainty.

## Evaluation

### Product resolution

* exact-model accuracy
* candidate top-1 and top-3 accuracy
* unknown-product rejection
* wrong-product false acceptance

### Issue planning

* intent accuracy
* target precision and recall
* duplicate-target rate
* atomic-target split accuracy
* registered component mapping accuracy

### Grounding

* status accuracy
* point-in-box
* IoU@0.5 and IoU@0.75
* false `not_visible`
* partial success
* crop retry usage

### End to end

* source-supported guide rate
* wrong-manual guidance rate
* user target corrections
* completion rate
* useful abstention rate

The evaluation matrix includes registered products, alternate user wording,
missing model codes, ambiguous product candidates, unknown products, wrong
manuals and two-to-three-target issues.

## Migration

The existing WD80H25BHS endpoint and reviewed references remain valid during
migration. The new issue endpoints are added first. The mobile demo switches
only after issue planning and target confirmation tests pass. The legacy
single-product fields are removed after the dynamic path is deployed and
verified.

## Rollout

1. Add issue-resolution contracts and a deterministic fake planner.
2. Generalize registry and manual asset lookup.
3. Implement the Terra issue planner with strict outputs.
4. Add dynamic grounding orchestration.
5. Replace the fixed mobile form with target confirmation.
6. Add registered, candidate and unknown evaluation cases.
7. Deploy beside the existing reviewed path and compare results.
8. Make the dynamic path the default after quality gates pass.
