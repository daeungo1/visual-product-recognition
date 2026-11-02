import pytest
from pydantic import ValidationError

from visual_guide.contracts import (
    GroundedTarget,
    MultiTargetRegionRequest,
    MultiTargetRegionResponse,
    PixelBox,
    PixelPoint,
    RegionProposal,
    RegionStatus,
)


def test_located_region_requires_bounded_point_inside_box():
    proposal = RegionProposal(
        status=RegionStatus.LOCATED,
        step_id="open-filter-cover",
        component="filter-cover",
        image_width=1200,
        image_height=1600,
        point=PixelPoint(x=600, y=800),
        box=PixelBox(x1=400, y1=600, x2=900, y2=1100),
        evidence="Visible lower service cover.",
    )

    assert proposal.point.x == 600


@pytest.mark.parametrize(
    ("point", "box"),
    [
        (None, None),
        (PixelPoint(x=950, y=1200), PixelBox(x1=400, y1=600, x2=900, y2=1100)),
        (PixelPoint(x=600, y=800), PixelBox(x1=400, y1=600, x2=1300, y2=1100)),
    ],
)
def test_located_region_rejects_missing_or_invalid_geometry(point, box):
    with pytest.raises(ValidationError):
        RegionProposal(
            status=RegionStatus.LOCATED,
            step_id="open-filter-cover",
            component="filter-cover",
            image_width=1200,
            image_height=1600,
            point=point,
            box=box,
            evidence="candidate",
        )


def test_non_success_region_rejects_geometry():
    with pytest.raises(ValidationError):
        RegionProposal(
            status=RegionStatus.UNCERTAIN,
            step_id="open-filter-cover",
            component="filter-cover",
            image_width=1200,
            image_height=1600,
            point=PixelPoint(x=600, y=800),
            box=PixelBox(x1=400, y1=600, x2=900, y2=1100),
            evidence="Candidates disagree.",
        )


def test_multi_target_response_preserves_partial_success():
    response = MultiTargetRegionResponse(
        product_id="samsung-wd80h25bhs",
        guide_id="detergent-and-controls",
        step_id="locate-detergent-and-controls",
        image_width=1200,
        image_height=1600,
        targets=(
            GroundedTarget(
                target_id="control_panel",
                component="조작부",
                status=RegionStatus.LOCATED,
                point=PixelPoint(x=600, y=180),
                box=PixelBox(x1=420, y1=80, x2=820, y2=300),
                evidence="The LCD and dial are visible.",
                attempts=1,
                retake_instruction=None,
            ),
            GroundedTarget(
                target_id="detergent_dispenser",
                component="세제함 전면 덮개",
                status=RegionStatus.UNCERTAIN,
                point=None,
                box=None,
                evidence="The lower front seam is ambiguous.",
                attempts=2,
                retake_instruction="제품 전면 하단을 가까이 촬영하세요.",
            ),
        ),
        partial_success=True,
    )

    assert [target.target_id for target in response.targets] == [
        "control_panel",
        "detergent_dispenser",
    ]
    assert response.targets[0].box is not None
    assert response.targets[1].box is None


def test_multi_target_request_rejects_duplicate_targets():
    with pytest.raises(ValidationError, match="target_ids"):
        MultiTargetRegionRequest(
            model_code="WD80H25BHS",
            guide_id="detergent-and-controls",
            step_id="locate-detergent-and-controls",
            target_ids=("control_panel", "control_panel"),
        )


def test_non_located_target_requires_retake_instruction():
    with pytest.raises(ValidationError, match="retake_instruction"):
        GroundedTarget(
            target_id="detergent_dispenser",
            component="세제함 전면 덮개",
            status=RegionStatus.NOT_VISIBLE,
            point=None,
            box=None,
            evidence="Not visible.",
            attempts=1,
            retake_instruction=None,
        )
