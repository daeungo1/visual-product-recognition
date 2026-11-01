import pytest
from pydantic import ValidationError

from visual_guide.contracts import PixelBox, PixelPoint, RegionProposal, RegionStatus


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
