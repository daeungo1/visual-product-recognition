import pytest
from pydantic import ValidationError

from visual_guide.contracts import (
    GroundedTarget,
    PixelBox,
    PixelPoint,
    RegionStatus,
)
from visual_guide.issue_contracts import (
    ConfidenceBand,
    DynamicTargetSpec,
    GroundedIssueTarget,
    IssueGroundingRequest,
    IssueGroundingResponse,
    IssueResolution,
    IssueResolutionRequest,
    ProductCandidate,
    ProductStatus,
    SupportMode,
    TargetSource,
)


def _candidate(
    confidence: ConfidenceBand = ConfidenceBand.HIGH,
) -> ProductCandidate:
    return ProductCandidate(
        product_id="samsung-wd80h25bhs",
        manufacturer="Samsung",
        display_name="Bespoke AI Combo",
        exact_model_codes=("WD80H25BHS",),
        evidence_source="exact_model_code",
        confidence_band=confidence,
        confirmed_model_code=(
            "WD80H25BHS" if confidence is ConfidenceBand.HIGH else None
        ),
    )


def _target(
    target_id: str,
    canonical_name: str,
    source: TargetSource,
) -> DynamicTargetSpec:
    registered = source is TargetSource.REGISTRY
    return DynamicTargetSpec(
        target_id=target_id,
        display_name=canonical_name,
        canonical_name=canonical_name,
        aliases=(canonical_name,),
        purpose="locate",
        relative_region="full_front",
        source=source,
        registry_component_id=target_id if registered else None,
        manual_evidence="manual:18" if registered else None,
    )


def _registered_resolution() -> IssueResolution:
    return IssueResolution(
        product_status=ProductStatus.REGISTERED,
        support_mode=SupportMode.REVIEWED_GUIDE,
        product_candidates=(_candidate(),),
        issue_intent="detergent_loading",
        targets=(
            _target(
                "detergent_dispenser",
                "세제함 전면 덮개",
                TargetSource.REGISTRY,
            ),
            _target("user-target-1", "알림 표시부", TargetSource.ZERO_SHOT),
        ),
        guide_candidates=(),
        requires_product_confirmation=False,
        requires_target_confirmation=True,
        next_capture_instruction="제품 전면을 촬영하세요.",
        truncation_reason=None,
    )


def test_issue_resolution_accepts_mixed_reviewed_and_zero_shot_targets():
    resolution = _registered_resolution()

    assert resolution.product_status is ProductStatus.REGISTERED
    assert [target.source for target in resolution.targets] == [
        TargetSource.REGISTRY,
        TargetSource.ZERO_SHOT,
    ]


def test_issue_resolution_rejects_more_than_three_targets():
    targets = tuple(
        _target(f"target-{index}", f"target {index}", TargetSource.ZERO_SHOT)
        for index in range(4)
    )

    with pytest.raises(ValidationError, match="targets"):
        IssueResolution(
            product_status=ProductStatus.UNKNOWN,
            support_mode=SupportMode.ZERO_SHOT_LOCATE_ONLY,
            product_candidates=(),
            issue_intent="locate_parts",
            targets=targets,
            guide_candidates=(),
            requires_product_confirmation=False,
            requires_target_confirmation=True,
            next_capture_instruction="제품 전면을 촬영하세요.",
            truncation_reason="Only the first three targets are supported.",
        )


def test_issue_resolution_rejects_duplicate_canonical_targets():
    with pytest.raises(ValidationError, match="canonical"):
        IssueResolution(
            product_status=ProductStatus.UNKNOWN,
            support_mode=SupportMode.ZERO_SHOT_LOCATE_ONLY,
            product_candidates=(),
            issue_intent="locate_parts",
            targets=(
                _target("first", "Control Panel", TargetSource.ZERO_SHOT),
                _target("second", "control panel", TargetSource.ZERO_SHOT),
            ),
            guide_candidates=(),
            requires_product_confirmation=False,
            requires_target_confirmation=True,
            next_capture_instruction="제품 전면을 촬영하세요.",
            truncation_reason=None,
        )


def test_candidate_product_requires_confirmation():
    with pytest.raises(ValidationError, match="confirmation"):
        IssueResolution(
            product_status=ProductStatus.CANDIDATE,
            support_mode=SupportMode.ZERO_SHOT_LOCATE_ONLY,
            product_candidates=(_candidate(ConfidenceBand.MEDIUM),),
            issue_intent="locate_parts",
            targets=(_target("panel", "조작부", TargetSource.ZERO_SHOT),),
            guide_candidates=(),
            requires_product_confirmation=False,
            requires_target_confirmation=True,
            next_capture_instruction="모델 라벨을 촬영하세요.",
            truncation_reason=None,
        )


def test_zero_shot_target_cannot_claim_registry_evidence():
    with pytest.raises(ValidationError, match="registry"):
        DynamicTargetSpec(
            target_id="free-target",
            display_name="필터",
            canonical_name="filter",
            aliases=("필터",),
            purpose="locate",
            relative_region="full_front",
            source=TargetSource.ZERO_SHOT,
            registry_component_id="reviewed-filter",
            manual_evidence="manual:10",
        )


def test_registered_grounding_request_requires_exact_product_confirmation():
    resolution = _registered_resolution()

    with pytest.raises(ValidationError, match="confirmed_model_code"):
        IssueGroundingRequest(
            resolution=resolution,
            confirmed_product_id="samsung-wd80h25bhs",
            confirmed_model_code=None,
            confirmed_targets=resolution.targets,
        )


def test_grounding_response_restricts_instruction_to_registry_target():
    located = GroundedTarget(
        target_id="detergent_dispenser",
        component="세제함 전면 덮개",
        status=RegionStatus.LOCATED,
        point=PixelPoint(x=50, y=60),
        box=PixelBox(x1=10, y1=20, x2=90, y2=100),
        evidence="visible",
        attempts=1,
        retake_instruction=None,
    )

    with pytest.raises(ValidationError, match="instruction"):
        IssueGroundingResponse(
            product_status=ProductStatus.UNKNOWN,
            support_mode=SupportMode.ZERO_SHOT_LOCATE_ONLY,
            product_id=None,
            model_code=None,
            guide_id=None,
            step_id=None,
            image_width=100,
            image_height=120,
            targets=(
                GroundedIssueTarget(
                    target=_target(
                        "detergent_dispenser",
                        "세제함 전면 덮개",
                        TargetSource.ZERO_SHOT,
                    ),
                    grounding=located,
                    instruction="세제함을 여세요.",
                    source_reference="manual:22",
                ),
            ),
            partial_success=False,
        )


def test_issue_request_requires_non_blank_issue():
    with pytest.raises(ValidationError):
        IssueResolutionRequest(
            product_hint=None,
            model_code=None,
            user_issue=" ",
            current_state=None,
        )
