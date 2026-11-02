---
title: Hybrid Issue-Driven Visual Guidance Implementation Plan
description: TDD plan for free-form issues, dynamic targets, and multi-product guidance
---

## Hybrid Issue-Driven Visual Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed WD80H25BHS target form with a free-form issue flow
that supports registered products, candidate confirmation and unknown-product
zero-shot location.

**Architecture:** A strict issue planner produces at most three dynamic targets
without geometry. A deterministic product resolver and reviewed registry select
the support mode, then the existing independent consensus and adaptive-crop
pipeline grounds only user-confirmed targets.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, Pillow, Azure OpenAI
GPT-6.1 Terra, pytest, Ruff, mobile HTML/JavaScript and Azure Container Apps.

**Spec:** `docs/superpowers/specs/2026-11-02-hybrid-issue-guidance-design.md`

## Global Constraints

* Keep the current WD80H25BHS reviewed path working throughout migration.
* Accept at most three unique atomic targets per issue.
* Do not allow the client to author trusted aliases, relative regions,
  registry IDs or manual evidence.
* Require exact model-code confirmation before returning reviewed instructions.
* Treat family, product-name and visual matches as candidates only.
* Keep unknown-product results in `zero_shot_locate_only` mode.
* Return reviewed instructions only after product, manual, guide, state and
  target applicability pass.
* Reuse three proposals, two-of-three consensus and uncertain-only crop retry.
* Keep request images in memory and out of application persistence.
* Defer SAM, GPU inference, video tracking and AR.

## Review Focus

* A compound Korean issue with four apparent targets must produce no more than
  three atomic targets and explain the truncation.
* Renaming a target must not change canonical aliases, registry IDs, evidence
  or relative-region priors.
* A medium-confidence product-family match must not expose reviewed
  instructions before exact-model confirmation.
* A registered product with one reviewed and one zero-shot target must preserve
  target-level support sources and restrict instructions to the reviewed target.
* An unavailable planner or model must return a service error without
  converting it into visual uncertainty or discarding independent target
  results.

---

### Task 1: Issue and product resolution contracts

**Files:**

* Create: `server/src/visual_guide/issue_contracts.py`
* Create: `server/tests/test_issue_contracts.py`

**Interfaces:**

* Consumes: existing `RegionStatus`, pixel geometry and reviewed IDs.
* Produces: `ProductStatus`, `SupportMode`, `ConfidenceBand`,
  `TargetSource`, `IssueResolutionRequest`, `ProductCandidate`,
  `DynamicTargetSpec`, `GuideCandidate`, `IssueResolution`,
  `IssueGroundingRequest`, `IssueGroundingResponse`.

- [ ] **Step 1: Write failing contract tests**

Cover registered, candidate and unknown product states; mixed reviewed and
zero-shot targets; maximum three targets; duplicate canonical targets; exact
model confirmation and target-level support sources.

- [ ] **Step 2: Run the focused tests**

Run: `uv run --directory server pytest tests/test_issue_contracts.py -q`

Expected: FAIL because `visual_guide.issue_contracts` does not exist.

- [ ] **Step 3: Implement strict immutable Pydantic contracts**

Use `extra="forbid"` and model validators. Instructions and source evidence
must be absent unless support mode and target source permit them.

- [ ] **Step 4: Run focused tests and Ruff**

Run: `uv run --directory server pytest tests/test_issue_contracts.py -q`

Run: `uv run --directory server ruff check src tests`

Expected: both pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add hybrid issue contracts`

### Task 2: Multi-product registry and issue mappings

**Files:**

* Modify: `server/src/visual_guide/registry.py`
* Create: `server/src/visual_guide/manual_assets.py`
* Modify: `server/src/visual_guide/references/samsung/WD80H25BHS/manifest.json`
* Create: `server/src/visual_guide/references/samsung/WD80H25BHS/issues.json`
* Create: `server/tests/test_manual_assets.py`
* Modify: `server/tests/test_registry.py`

**Interfaces:**

* Consumes: existing product, manual, component and guide records.
* Produces: `IssueMapping`, `ManualAssetProvider`,
  `ReviewedRegistry.resolve_exact_model(model_code)`,
  `ReviewedRegistry.search_product_candidates(product_hint)`,
  `ReviewedRegistry.resolve_component_alias(product_id, user_target)`,
  `ReviewedRegistry.find_guide_candidates(...)`,
  `ReviewedRegistry.manual_asset(product_id, manual_id)`.

- [ ] **Step 1: Write failing registry-generalization tests**

Cover multiple manufacturer/product folders, normalized exact models, high,
medium and low evidence bands, deterministic intent/state mapping, manual asset
lookup, family-only candidates and zero cross-product component leakage.

- [ ] **Step 2: Run focused registry tests**

Run: `uv run --directory server pytest tests/test_registry.py tests/test_manual_assets.py -q`

Expected: FAIL because generalized APIs and issue mappings do not exist.

- [ ] **Step 3: Implement generalized registry APIs**

Remove single-model runtime assumptions. Use exact normalized model codes for
high confidence and reviewed aliases for medium candidates. Keep visual-only
evidence outside the registry's approval path.

- [ ] **Step 4: Implement generic manual asset provider**

Replace the WD80H25BHS-specific runtime dictionary with a provider keyed by
`product_id` and `manual_id`. Preserve content-hash verification.

- [ ] **Step 5: Run registry tests, full suite and Ruff**

Run: `uv run --directory server pytest -q`

Run: `uv run --directory server ruff check src tests`

Expected: all pass.

- [ ] **Step 6: Commit**

Commit message: `feat: generalize reviewed product registry`

### Task 3: Deterministic product resolver

**Files:**

* Create: `server/src/visual_guide/product_resolver.py`
* Create: `server/tests/test_product_resolver.py`

**Interfaces:**

* Consumes: `ReviewedRegistry`, optional model code, product hint and planner
  category evidence.
* Produces:
  `resolve_product(model_code, product_hint, visual_category, registry) ->
  ProductResolution`.

- [ ] **Step 1: Write failing resolution tests**

Cover one exact high match, conflicting exact evidence, ordered medium
candidates, low visual-category candidates, no candidates, exact model plus
wrong product hint and mandatory confirmation rules.

- [ ] **Step 2: Run resolver tests**

Run: `uv run --directory server pytest tests/test_product_resolver.py -q`

Expected: FAIL because the resolver does not exist.

- [ ] **Step 3: Implement deterministic ranking**

Exact model evidence outranks all hints. Conflicting evidence produces
candidate or unknown state, never silent exact-product approval.

- [ ] **Step 4: Run resolver tests and Ruff**

Run: `uv run --directory server pytest tests/test_product_resolver.py -q`

Run: `uv run --directory server ruff check src tests`

Expected: both pass.

- [ ] **Step 5: Commit**

Commit message: `feat: resolve registered product candidates`

### Task 4: Terra issue planner

**Files:**

* Create: `server/src/visual_guide/issue_planner.py`
* Create: `server/tests/test_issue_planner.py`
* Modify: `server/src/visual_guide/model_gateway.py`

**Interfaces:**

* Consumes: `IssueResolutionRequest`, registry summary and optional image.
* Produces:
  `IssuePlanner.plan(request, registry_summary, image) -> PlannedIssue` and a
  deterministic `FakeIssuePlanner`.

- [ ] **Step 1: Write failing planner adapter tests**

Cover strict JSON Schema, Korean compound target splitting, three-target cap,
duplicate removal, no geometry fields, visual-category evidence, explicit
truncation reason and provider errors.

- [ ] **Step 2: Run planner tests**

Run: `uv run --directory server pytest tests/test_issue_planner.py -q`

Expected: FAIL because the planner does not exist.

- [ ] **Step 3: Implement fake planner and Foundry adapter**

The prompt may produce display names, canonical descriptions and broad regions.
It cannot emit trusted registry IDs, reviewed evidence or instructions.

- [ ] **Step 4: Run planner tests and all gateway tests**

Run: `uv run --directory server pytest tests/test_issue_planner.py tests/test_model_gateway.py -q`

Run: `uv run --directory server ruff check src tests`

Expected: all pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add structured issue planner`

### Task 5: Hybrid issue-resolution service

**Files:**

* Create: `server/src/visual_guide/issue_service.py`
* Create: `server/tests/test_issue_service.py`

**Interfaces:**

* Consumes: issue planner, product resolver, reviewed registry and
  `IssueResolutionRequest`.
* Produces:
  `IssueResolutionService.resolve(request, image) -> IssueResolution` and
  `IssueResolutionService.confirm_targets(...) -> tuple[DynamicTargetSpec, ...]`.

- [ ] **Step 1: Write failing service tests**

Cover registered exact product, candidate confirmation, unknown product,
reviewed alias mapping, mixed reviewed/zero-shot targets, display-only rename,
replanning of added targets, intent-to-guide mapping, state unknown and planner
failure as a service error.

- [ ] **Step 2: Run service tests**

Run: `uv run --directory server pytest tests/test_issue_service.py -q`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement bounded resolution composition**

Use deterministic product and registry decisions after planner output. Never
upgrade target or guide evidence based on the planner's own claims.

- [ ] **Step 4: Run service tests and full suite**

Run: `uv run --directory server pytest -q`

Run: `uv run --directory server ruff check src tests`

Expected: all pass.

- [ ] **Step 5: Commit**

Commit message: `feat: resolve hybrid product issues`

### Task 6: Dynamic target grounding

**Files:**

* Modify: `server/src/visual_guide/orchestrator.py`
* Create: `server/src/visual_guide/issue_grounding.py`
* Create: `server/tests/test_issue_grounding.py`
* Modify: `server/tests/test_orchestrator.py`

**Interfaces:**

* Consumes: confirmed `IssueResolution`, `DynamicTargetSpec[]`, image and
  existing `GuideGroundingService`.
* Produces:
  `IssueGroundingService.ground(request, image) -> IssueGroundingResponse`.

- [ ] **Step 1: Write failing dynamic-grounding tests**

Cover reviewed target conversion, zero-shot temporary components, mixed target
support sources, target independence, exact-model revalidation, candidate
refusal, unknown locate-only behavior, reviewed-instruction restriction and
provider failure isolation.

- [ ] **Step 2: Run focused grounding tests**

Run: `uv run --directory server pytest tests/test_issue_grounding.py tests/test_orchestrator.py -q`

Expected: FAIL because dynamic grounding does not exist.

- [ ] **Step 3: Extract reusable target-grounding primitive**

Refactor the current orchestrator so reviewed and zero-shot targets share one
proposal, consensus, crop and remap path without weakening registry checks.

- [ ] **Step 4: Implement hybrid grounding composition**

Zero-shot targets carry no reviewed instruction or manual evidence. Registered
instructions attach only after the current guide step is applicable.

- [ ] **Step 5: Run focused tests and full suite**

Run: `uv run --directory server pytest -q`

Run: `uv run --directory server ruff check src tests`

Expected: all pass.

- [ ] **Step 6: Commit**

Commit message: `feat: ground dynamic issue targets`

### Task 7: Hybrid issue API and error mapping

**Files:**

* Modify: `server/src/visual_guide/main.py`
* Modify: `server/tests/test_api.py`

**Interfaces:**

* Consumes: issue-resolution and issue-grounding services.
* Produces: `/v1/issues/resolve`, `/v1/issues/ground`,
  `/demo/issues/resolve` and `/demo/issues/ground`.

- [ ] **Step 1: Write failing endpoint tests**

Cover bearer and demo-cookie authentication, registered/candidate/unknown
responses, optional image validation, unsupported exact model as 422,
inapplicable guide as 422, planner unavailable as 503, model unavailable as
503 and no image-body logging.

- [ ] **Step 2: Run API tests**

Run: `uv run --directory server pytest tests/test_api.py -q`

Expected: FAIL because hybrid endpoints do not exist.

- [ ] **Step 3: Implement routes and explicit domain-error mapping**

Map expected user and registry errors to 4xx. Preserve dependency and provider
failures as 5xx without success-shaped fallbacks.

- [ ] **Step 4: Wire environment-configured services**

Build registry, asset provider, issue planner, resolver, resolution service and
grounding service without hardcoded product IDs.

- [ ] **Step 5: Run API tests and full suite**

Run: `uv run --directory server pytest -q`

Run: `uv run --directory server ruff check src tests`

Expected: all pass.

- [ ] **Step 6: Commit**

Commit message: `feat: expose hybrid issue guidance API`

### Task 8: Dynamic mobile issue flow

**Files:**

* Modify: `server/src/visual_guide/demo.py`
* Modify: `server/tests/test_api.py`

**Interfaces:**

* Consumes: demo issue endpoints.
* Produces: free-form product, issue and state fields; product confirmation;
  editable target chips; dynamic overlays and mode-specific guidance.

- [ ] **Step 1: Write failing mobile page tests**

Assert no fixed model or target values, required issue input, optional product
and state inputs, local image reuse, analyze-then-ground sequence, product
confirmation, target-chip editing, maximum-three display, reviewed/zero-shot
labels and source-supported instructions.

- [ ] **Step 2: Run mobile API tests**

Run: `uv run --directory server pytest tests/test_api.py -q`

Expected: FAIL because the page still hardcodes WD80H25BHS targets.

- [ ] **Step 3: Implement the two-stage mobile flow**

Keep the image in browser memory. Renames modify display text only. Additions
call issue resolution again and never fabricate registry metadata in JavaScript.

- [ ] **Step 4: Run API tests, full suite and Ruff**

Run: `uv run --directory server pytest -q`

Run: `uv run --directory server ruff check src tests`

Expected: all pass.

- [ ] **Step 5: Commit**

Commit message: `feat: add dynamic mobile issue flow`

### Task 9: Hybrid evaluation and deployment

**Files:**

* Modify: `server/src/visual_guide/evaluation.py`
* Modify: `server/tests/test_evaluation.py`
* Modify: `eval/cases.json`
* Create: `eval/hybrid-cases.json`
* Modify: `eval/run_eval.py`
* Modify: `README.md`
* Modify: `.azure/deployment-plan.md`

**Interfaces:**

* Consumes: issue-resolution and dynamic-grounding services.
* Produces: target-extraction, product-resolution, support-mode and grounding
  metrics plus a deployed dynamic mobile flow.

- [ ] **Step 1: Write failing evaluation tests**

Cover exact registered, alternate wording, candidate, unknown, wrong-model,
wrong-manual, mixed target and four-target truncation cases. Assert intent,
target precision/recall, product top-k, false registered acceptance, support
mode, IoU, point-in-box and source-supported guide metrics.

- [ ] **Step 2: Implement hybrid evaluation reports**

Keep planner, product resolver, registry gate and grounding metrics separate so
one aggregate score cannot hide the failing layer.

- [ ] **Step 3: Run tests, Ruff and Bicep build**

Run: `uv run --directory server pytest -q`

Run: `uv run --directory server ruff check src tests eval`

Run: `az bicep build --file infra/main.bicep --stdout`

Expected: all pass.

- [ ] **Step 4: Run live registered and unknown smoke cases**

Use GPT-6.1 Terra with user-authorized images. Record the exact deployment,
prompt version, target outputs, support modes and latency.

- [ ] **Step 5: Build and deploy beside the current route**

Use ACR remote build and update the existing Container App. Preserve the
current reviewed endpoints until dynamic-route smoke tests pass.

- [ ] **Step 6: Verify mobile end to end**

Test login, free-form issue analysis, target confirmation, registered guide,
unknown locate-only mode, health and readiness.

- [ ] **Step 7: Update documentation**

Document supported modes, known limits, evaluation evidence and the P3 SAM
quota-region follow-up.

- [ ] **Step 8: Commit**

Commit message: `feat: deploy hybrid issue guidance`
