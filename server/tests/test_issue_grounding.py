from pathlib import Path

import pytest

from visual_guide.contracts import (
    GroundedTarget,
    PixelBox,
    PixelPoint,
    RegionStatus,
)
from visual_guide.images import ImageInput
from visual_guide.issue_contracts import (
    ConfidenceBand,
    DynamicTargetSpec,
    IssueGroundingRequest,
    IssueResolution,
    ProductCandidate,
    ProductStatus,
    SupportMode,
    TargetSource,
)
from visual_guide.issue_grounding import IssueGroundingService
from visual_guide.issue_service import ResolutionSigner
from visual_guide.registry import (
    ComponentSpec,
    GuideStep,
    ManualReference,
    ProductManifest,
    ResolvedGuide,
    ReviewedGuide,
)


def _manual():
    return ManualReference(
        manual_id="manual",
        source_url="https://example.test/manual.pdf",
        sha256="A" * 64,
        language="ko-KR",
        revision="1",
        asset_name="manual.pdf",
        applicable_models=("MODEL-A",),
        reviewed=True,
    )


def _product():
    return ProductManifest(
        product_id="product-a",
        manufacturer="Samsung",
        display_name="Alpha Washer",
        product_family="washer",
        aliases=("Alpha",),
        exact_model_codes=("MODEL-A",),
        reviewed=True,
        manuals=(_manual(),),
    )


def _guide():
    return ReviewedGuide(
        guide_id="detergent-guide",
        title="Detergent guide",
        exact_model_codes=("MODEL-A",),
        reviewed=True,
        steps=(
            GuideStep(
                step_id="locate-parts",
                required_state="front_visible",
                target_ids=("detergent_dispenser",),
                instruction="세제함 위치를 확인하세요.",
                expected_state="confirmed",
                verification="visual",
                source_manual_id="manual",
                source_page=10,
                source_evidence="세제함은 전면 하단에 있습니다.",
            ),
        ),
    )


def _registry_target():
    return DynamicTargetSpec(
        target_id="detergent_dispenser",
        display_name="세제 넣는 곳",
        canonical_name="세제함 전면 덮개",
        aliases=("세제함",),
        purpose="locate",
        relative_region="lower_front",
        source=TargetSource.REGISTRY,
        registry_component_id="detergent_dispenser",
        manual_evidence="manual:page:10",
    )


def _zero_target():
    return DynamicTargetSpec(
        target_id="user-target-2",
        display_name="알림 표시부",
        canonical_name="alert display",
        aliases=("알림 표시부",),
        purpose="locate",
        relative_region="upper_center",
        source=TargetSource.ZERO_SHOT,
        registry_component_id=None,
        manual_evidence=None,
    )


def _candidate():
    return ProductCandidate(
        product_id="product-a",
        manufacturer="Samsung",
        display_name="Alpha Washer",
        exact_model_codes=("MODEL-A",),
        evidence_source="model_code",
        confidence_band=ConfidenceBand.HIGH,
        confirmed_model_code="MODEL-A",
    )


def _registered_resolution():
    resolution = IssueResolution(
        product_status=ProductStatus.REGISTERED,
        support_mode=SupportMode.REVIEWED_GUIDE,
        product_candidates=(_candidate(),),
        issue_intent="detergent_loading",
        normalized_state="front_visible",
        targets=(_registry_target(), _zero_target()),
        guide_candidates=(),
        requires_product_confirmation=False,
        requires_target_confirmation=True,
        next_capture_instruction="제품 전면을 촬영하세요.",
        truncation_reason=None,
        resolution_token=None,
    )
    return ResolutionSigner("test-resolution-secret").attach(resolution)


class FakeRegistry:
    component = ComponentSpec(
        component_id="detergent_dispenser",
        canonical_name="세제함 전면 덮개",
        aliases=("세제함",),
        relative_region="lower_front",
    )

    def resolve_exact_model(self, model_code):
        if model_code != "MODEL-A":
            raise LookupError(model_code)
        return _product()

    def manual_asset(self, product_id, manual_id):
        assert product_id == "product-a"
        assert manual_id == "manual"
        return _manual()

    def guide(self, product_id, guide_id):
        assert product_id == "product-a"
        assert guide_id == "detergent-guide"
        return _guide()

    def resolve_guide(self, **_kwargs):
        return ResolvedGuide(
            product=_product(),
            manual=_manual(),
            guide=_guide(),
            components={"detergent_dispenser": self.component},
        )

    def component_by_id(self, product_id, component_id):
        if product_id == "product-a" and component_id == "detergent_dispenser":
            return self.component
        raise LookupError(component_id)

    def eligible_step(
        self,
        *,
        product_id,
        issue_intent,
        current_state,
        guide_id,
        step_id,
    ):
        if (
            product_id == "product-a"
            and issue_intent == "detergent_loading"
            and current_state == "front_visible"
            and guide_id == "detergent-guide"
            and step_id == "locate-parts"
        ):
            return _guide().steps[0]
        raise LookupError("ineligible step")


class FakeManualProvider:
    def resolve(self, _manual):
        return Path("manual.pdf")


class FakeTargetGrounder:
    def __init__(self):
        self.calls = []

    def ground(self, *, target_id, component, step, image):
        self.calls.append((target_id, component, step, image))
        return GroundedTarget(
            target_id=target_id,
            component=component.canonical_name,
            status=RegionStatus.LOCATED,
            point=PixelPoint(x=50, y=50),
            box=PixelBox(x1=10, y1=10, x2=90, y2=90),
            evidence="visible",
            attempts=1,
            retake_instruction=None,
        )


def _image():
    return ImageInput(data=b"png", mime="image/png", width=100, height=100)


def test_registered_grounding_preserves_mixed_target_authority():
    grounder = FakeTargetGrounder()
    service = IssueGroundingService(
        registry=FakeRegistry(),
        manual_provider=FakeManualProvider(),
        target_grounder=grounder,
        signer=ResolutionSigner("test-resolution-secret"),
    )
    resolution = _registered_resolution()
    request = IssueGroundingRequest(
        resolution=resolution,
        confirmed_product_id="product-a",
        confirmed_model_code="MODEL-A",
        confirmed_guide_id="detergent-guide",
        confirmed_step_id="locate-parts",
        confirmed_targets=resolution.targets,
    )

    response = service.ground(request, _image())

    assert [target.target.source for target in response.targets] == [
        TargetSource.REGISTRY,
        TargetSource.ZERO_SHOT,
    ]
    assert response.targets[0].instruction == "세제함 위치를 확인하세요."
    assert response.targets[0].source_reference == "manual:page:10"
    assert response.targets[1].instruction is None
    assert grounder.calls[0][1].relative_region == "lower_front"
    assert grounder.calls[1][1].relative_region == "upper_center"


def test_candidate_product_cannot_enter_grounding_before_confirmation():
    resolution = ResolutionSigner("test-resolution-secret").attach(
        _registered_resolution().model_copy(
            update={
                "product_status": ProductStatus.CANDIDATE,
                "support_mode": SupportMode.ZERO_SHOT_LOCATE_ONLY,
                "requires_product_confirmation": True,
                "resolution_token": None,
            }
        )
    )
    service = IssueGroundingService(
        registry=FakeRegistry(),
        manual_provider=FakeManualProvider(),
        target_grounder=FakeTargetGrounder(),
        signer=ResolutionSigner("test-resolution-secret"),
    )
    request = IssueGroundingRequest(
        resolution=resolution,
        confirmed_product_id=None,
        confirmed_model_code=None,
        confirmed_guide_id=None,
        confirmed_step_id=None,
        confirmed_targets=resolution.targets,
    )

    with pytest.raises(ValueError, match="confirmation"):
        service.ground(request, _image())


def test_registered_grounding_revalidates_exact_model():
    resolution = _registered_resolution()
    service = IssueGroundingService(
        registry=FakeRegistry(),
        manual_provider=FakeManualProvider(),
        target_grounder=FakeTargetGrounder(),
        signer=ResolutionSigner("test-resolution-secret"),
    )
    request = IssueGroundingRequest(
        resolution=resolution,
        confirmed_product_id="product-a",
        confirmed_model_code="MODEL-B",
        confirmed_guide_id="detergent-guide",
        confirmed_step_id="locate-parts",
        confirmed_targets=resolution.targets,
    )

    with pytest.raises(ValueError, match="exact model"):
        service.ground(request, _image())


def test_unknown_product_grounds_zero_shot_without_instruction():
    target = _zero_target()
    resolution = IssueResolution(
        product_status=ProductStatus.UNKNOWN,
        support_mode=SupportMode.ZERO_SHOT_LOCATE_ONLY,
        product_candidates=(),
        issue_intent="locate_display",
        normalized_state=None,
        targets=(target,),
        guide_candidates=(),
        requires_product_confirmation=False,
        requires_target_confirmation=True,
        next_capture_instruction="모델 라벨을 촬영하세요.",
        truncation_reason=None,
        resolution_token=None,
    )
    resolution = ResolutionSigner("test-resolution-secret").attach(resolution)
    service = IssueGroundingService(
        registry=FakeRegistry(),
        manual_provider=FakeManualProvider(),
        target_grounder=FakeTargetGrounder(),
        signer=ResolutionSigner("test-resolution-secret"),
    )
    request = IssueGroundingRequest(
        resolution=resolution,
        confirmed_product_id=None,
        confirmed_model_code=None,
        confirmed_guide_id=None,
        confirmed_step_id=None,
        confirmed_targets=(target,),
    )

    response = service.ground(request, _image())

    assert response.support_mode is SupportMode.ZERO_SHOT_LOCATE_ONLY
    assert response.targets[0].instruction is None
    assert response.product_id is None


def test_grounding_rejects_tampered_zero_shot_metadata():
    resolution = _registered_resolution()
    tampered = resolution.targets[1].model_copy(
        update={
            "canonical_name": "tampered target",
            "aliases": ("evil",),
            "relative_region": "lower_front",
        }
    )
    service = IssueGroundingService(
        registry=FakeRegistry(),
        manual_provider=FakeManualProvider(),
        target_grounder=FakeTargetGrounder(),
        signer=ResolutionSigner("test-resolution-secret"),
    )
    request = IssueGroundingRequest(
        resolution=resolution,
        confirmed_product_id="product-a",
        confirmed_model_code="MODEL-A",
        confirmed_guide_id="detergent-guide",
        confirmed_step_id="locate-parts",
        confirmed_targets=(resolution.targets[0], tampered),
    )

    with pytest.raises(ValueError, match="metadata"):
        service.ground(request, _image())


def test_grounding_rejects_step_outside_issue_state_mapping():
    resolution = _registered_resolution()
    service = IssueGroundingService(
        registry=FakeRegistry(),
        manual_provider=FakeManualProvider(),
        target_grounder=FakeTargetGrounder(),
        signer=ResolutionSigner("test-resolution-secret"),
    )
    request = IssueGroundingRequest(
        resolution=resolution,
        confirmed_product_id="product-a",
        confirmed_model_code="MODEL-A",
        confirmed_guide_id="detergent-guide",
        confirmed_step_id="open-detergent-dispenser",
        confirmed_targets=(resolution.targets[0],),
    )

    with pytest.raises(ValueError, match="eligible"):
        service.ground(request, _image())
