from io import BytesIO
from pathlib import Path

from PIL import Image

from visual_guide.contracts import (
    MultiTargetRegionRequest,
    PixelBox,
    PixelPoint,
    RegionProposal,
    RegionStatus,
)
from visual_guide.images import decode_image
from visual_guide.orchestrator import GuideGroundingService
from visual_guide.registry import (
    ComponentSpec,
    GuideStep,
    ManualReference,
    ProductManifest,
    ResolvedGuide,
    ReviewedGuide,
)


def _image(width: int = 1000, height: int = 800):
    output = BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return decode_image(output.getvalue(), "image/png")


def _resolved() -> ResolvedGuide:
    manual = ManualReference(
        manual_id="manual",
        source_url="https://example.test/manual.pdf",
        sha256="A" * 64,
        language="ko-KR",
        revision="2026-09-16",
        asset_name="manual.pdf",
        applicable_models=("WD80H25BHS",),
        reviewed=True,
    )
    return ResolvedGuide(
        product=ProductManifest(
            product_id="samsung-wd80h25bhs",
            manufacturer="Samsung",
            display_name="Bespoke AI Combo",
            product_family="washer_dryer_combo",
            aliases=("Bespoke AI Combo",),
            exact_model_codes=("WD80H25BHS",),
            reviewed=True,
            manuals=(manual,),
        ),
        manual=manual,
        guide=ReviewedGuide(
            guide_id="detergent-and-controls",
            title="세제함과 조작부",
            exact_model_codes=("WD80H25BHS",),
            reviewed=True,
            steps=(
                GuideStep(
                    step_id="locate-detergent-and-controls",
                    required_state="front_visible",
                    target_ids=("detergent_dispenser", "control_panel"),
                    instruction="대상 위치를 확인하세요.",
                    expected_state="targets_confirmed",
                    verification="visual_confirmation",
                    source_manual_id="manual",
                    source_page=18,
                    source_evidence="02 조작부, 09 세제함 전면 덮개",
                ),
            ),
        ),
        components={
            "detergent_dispenser": ComponentSpec(
                component_id="detergent_dispenser",
                canonical_name="세제함 전면 덮개",
                aliases=("세제함", "세제 투입구"),
                relative_region="lower_front",
            ),
            "control_panel": ComponentSpec(
                component_id="control_panel",
                canonical_name="조작부",
                aliases=("조작 버튼",),
                relative_region="upper_center",
            ),
        },
    )


class FakeRegistry:
    def resolve_guide(self, **_kwargs):
        return _resolved()


class QueueGateway:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = []

    def propose(self, request, image):
        self.calls.append((request, image))
        status = self.statuses.pop(0)
        if isinstance(status, Exception):
            raise status
        if status is RegionStatus.LOCATED:
            return RegionProposal(
                status=status,
                step_id=request.step_id,
                component=request.component,
                image_width=image.width,
                image_height=image.height,
                point=PixelPoint(x=50, y=40),
                box=PixelBox(x1=10, y1=10, x2=90, y2=70),
                evidence="visible",
            )
        return RegionProposal(
            status=status,
            step_id=request.step_id,
            component=request.component,
            image_width=image.width,
            image_height=image.height,
            point=None,
            box=None,
            evidence="not resolved",
        )


def _request(*target_ids: str) -> MultiTargetRegionRequest:
    return MultiTargetRegionRequest(
        model_code="WD80H25BHS",
        guide_id="detergent-and-controls",
        step_id="locate-detergent-and-controls",
        target_ids=target_ids,
    )


def test_grounding_runs_three_independent_proposals_per_target():
    gateway = QueueGateway([RegionStatus.LOCATED] * 6)
    service = GuideGroundingService(
        registry=FakeRegistry(),
        gateway=gateway,
        manual_paths={"WD80H25BHS": Path("manual.pdf")},
    )

    response = service.ground(
        _request("detergent_dispenser", "control_panel"),
        _image(),
    )

    assert [target.target_id for target in response.targets] == [
        "detergent_dispenser",
        "control_panel",
    ]
    assert all(target.status is RegionStatus.LOCATED for target in response.targets)
    assert all(target.attempts == 1 for target in response.targets)
    assert response.partial_success is False
    assert len(gateway.calls) == 6


def test_grounding_retries_one_target_with_crop_and_remaps_coordinates():
    gateway = QueueGateway(
        [RegionStatus.UNCERTAIN] * 3
        + [RegionStatus.LOCATED, RegionStatus.LOCATED, RegionStatus.UNCERTAIN]
    )
    service = GuideGroundingService(
        registry=FakeRegistry(),
        gateway=gateway,
        manual_paths={"WD80H25BHS": Path("manual.pdf")},
    )

    response = service.ground(_request("detergent_dispenser"), _image())

    target = response.targets[0]
    assert target.status is RegionStatus.LOCATED
    assert target.attempts == 2
    assert target.point == PixelPoint(x=50, y=480)
    assert target.box == PixelBox(x1=10, y1=450, x2=90, y2=510)
    assert len(gateway.calls) == 6


def test_grounding_preserves_partial_success_and_target_retake_guidance():
    gateway = QueueGateway(
        [RegionStatus.UNCERTAIN] * 6
        + [RegionStatus.LOCATED] * 3
    )
    service = GuideGroundingService(
        registry=FakeRegistry(),
        gateway=gateway,
        manual_paths={"WD80H25BHS": Path("manual.pdf")},
    )

    response = service.ground(
        _request("detergent_dispenser", "control_panel"),
        _image(),
    )

    assert response.targets[0].status is RegionStatus.UNCERTAIN
    assert response.targets[0].attempts == 2
    assert "전면 하단" in response.targets[0].retake_instruction
    assert response.targets[1].status is RegionStatus.LOCATED
    assert response.partial_success is True
    assert len(gateway.calls) == 9


def test_not_visible_consensus_is_not_retried():
    gateway = QueueGateway([RegionStatus.NOT_VISIBLE] * 3)
    service = GuideGroundingService(
        registry=FakeRegistry(),
        gateway=gateway,
        manual_paths={"WD80H25BHS": Path("manual.pdf")},
    )

    response = service.ground(_request("detergent_dispenser"), _image())

    target = response.targets[0]
    assert target.status is RegionStatus.NOT_VISIBLE
    assert target.attempts == 1
    assert len(gateway.calls) == 3


def test_failure_in_one_target_preserves_prior_target_success():
    gateway = QueueGateway([RegionStatus.LOCATED] * 3 + [ValueError("bad response")])
    service = GuideGroundingService(
        registry=FakeRegistry(),
        gateway=gateway,
        manual_paths={"WD80H25BHS": Path("manual.pdf")},
    )

    response = service.ground(
        _request("control_panel", "detergent_dispenser"),
        _image(),
    )

    assert response.targets[0].status is RegionStatus.LOCATED
    assert response.targets[1].status is RegionStatus.UNCERTAIN
    assert response.targets[1].attempts == 1
    assert response.partial_success is True
    assert len(gateway.calls) == 4
