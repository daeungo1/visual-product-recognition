from visual_guide.consensus import aggregate_regions
from visual_guide.contracts import PixelBox, PixelPoint, RegionProposal, RegionStatus


def located(x: int) -> RegionProposal:
    return RegionProposal(
        status=RegionStatus.LOCATED,
        step_id="open-filter-cover",
        component="filter-cover",
        image_width=1200,
        image_height=1600,
        point=PixelPoint(x=x, y=800),
        box=PixelBox(x1=x - 200, y1=600, x2=x + 250, y2=1100),
        evidence="Visible lower service cover.",
    )


def test_consensus_returns_median_region_for_agreeing_proposals():
    decision = aggregate_regions([located(590), located(600), located(610)])

    assert decision.status is RegionStatus.LOCATED
    assert decision.point == PixelPoint(x=600, y=800)


def test_consensus_preserves_majority_not_visible():
    missing = RegionProposal(
        status=RegionStatus.NOT_VISIBLE,
        step_id="open-filter-cover",
        component="filter-cover",
        image_width=1200,
        image_height=1600,
        point=None,
        box=None,
        evidence="Cover is outside the image.",
    )

    decision = aggregate_regions([located(600), missing, missing])

    assert decision.status is RegionStatus.NOT_VISIBLE
    assert decision.point is None
    assert decision.box is None


def test_consensus_returns_uncertain_for_spatial_disagreement():
    decision = aggregate_regions([located(250), located(600), located(950)])

    assert decision.status is RegionStatus.UNCERTAIN


def test_consensus_uses_two_agreeing_proposals_and_ignores_one_outlier():
    decision = aggregate_regions([located(590), located(600), located(950)])

    assert decision.status is RegionStatus.LOCATED
    assert decision.point == PixelPoint(x=595, y=800)
