"""Aggregate independent region proposals without success-shaped fallbacks."""

from collections.abc import Sequence
from itertools import combinations
from statistics import median

from visual_guide.contracts import PixelBox, PixelPoint, RegionProposal, RegionStatus

MIN_IOU = 0.3


def _iou(left: PixelBox, right: PixelBox) -> float:
    x1 = max(left.x1, right.x1)
    y1 = max(left.y1, right.y1)
    x2 = min(left.x2, right.x2)
    y2 = min(left.y2, right.y2)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    left_area = (left.x2 - left.x1) * (left.y2 - left.y1)
    right_area = (right.x2 - right.x1) * (right.y2 - right.y1)
    return intersection / (left_area + right_area - intersection)


def _without_geometry(
    reference: RegionProposal,
    status: RegionStatus,
    evidence: str,
) -> RegionProposal:
    return RegionProposal(
        status=status,
        step_id=reference.step_id,
        component=reference.component,
        image_width=reference.image_width,
        image_height=reference.image_height,
        point=None,
        box=None,
        evidence=evidence,
    )


def aggregate_regions(proposals: Sequence[RegionProposal]) -> RegionProposal:
    """Return median geometry only when at least two of three proposals agree."""
    if not proposals:
        raise ValueError("at least one proposal is required")
    reference = proposals[0]
    if any(
        proposal.step_id != reference.step_id
        or proposal.component != reference.component
        or proposal.image_width != reference.image_width
        or proposal.image_height != reference.image_height
        for proposal in proposals
    ):
        return _without_geometry(
            reference,
            RegionStatus.UNCERTAIN,
            "Proposal scopes do not match.",
        )
    not_visible = [
        proposal for proposal in proposals if proposal.status is RegionStatus.NOT_VISIBLE
    ]
    if len(not_visible) > len(proposals) // 2:
        return _without_geometry(
            reference,
            RegionStatus.NOT_VISIBLE,
            "Independent proposals agree that the component is not visible.",
        )
    uncertain = [
        proposal for proposal in proposals if proposal.status is RegionStatus.UNCERTAIN
    ]
    if len(uncertain) > len(proposals) // 2:
        return _without_geometry(
            reference,
            RegionStatus.UNCERTAIN,
            "Independent proposals remain uncertain.",
        )
    located = [proposal for proposal in proposals if proposal.status is RegionStatus.LOCATED]
    if len(located) < 2:
        return _without_geometry(
            reference,
            RegionStatus.UNCERTAIN,
            "Fewer than two proposals located the component.",
        )
    agreeing: list[RegionProposal] = []
    for size in range(len(located), 1, -1):
        agreeing = next(
            (
                list(group)
                for group in combinations(located, size)
                if all(
                    _iou(left.box, right.box) >= MIN_IOU
                    for left, right in combinations(group, 2)
                    if left.box is not None and right.box is not None
                )
            ),
            [],
        )
        if agreeing:
            break
    if len(agreeing) < 2:
        return _without_geometry(
            reference,
            RegionStatus.UNCERTAIN,
            "Located regions disagree.",
        )
    boxes = [proposal.box for proposal in agreeing if proposal.box is not None]
    points = [proposal.point for proposal in agreeing if proposal.point is not None]
    box = PixelBox(
        x1=int(median(item.x1 for item in boxes)),
        y1=int(median(item.y1 for item in boxes)),
        x2=int(median(item.x2 for item in boxes)),
        y2=int(median(item.y2 for item in boxes)),
    )
    point = PixelPoint(
        x=int(median(item.x for item in points)),
        y=int(median(item.y for item in points)),
    )
    return RegionProposal(
        status=RegionStatus.LOCATED,
        step_id=reference.step_id,
        component=reference.component,
        image_width=reference.image_width,
        image_height=reference.image_height,
        point=point,
        box=box,
        evidence="Independent proposals agree.",
    )
