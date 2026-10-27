"""Majority vote over repeated region proposals (normalised 0..1 boxes).

Rules: a proposal set is accepted only when a strict majority of ALL votes
(failed calls count) agrees it is usable; otherwise the result is "uncertain"
and no region is returned. Boxes are the per-coordinate median; a region whose
votes disagree (min pairwise IoU < UNSTABLE_IOU) is flagged unstable so a
viewer hides it instead of drawing a doubtful box.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from itertools import combinations

UNSTABLE_IOU = 0.3
Box = tuple[float, float, float, float]


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def vote_box(boxes: Sequence[Box]) -> tuple[Box, bool]:
    """Median box and whether all votes agree."""
    if not boxes:
        raise ValueError("no boxes")
    median = tuple(round(statistics.median(b[i] for b in boxes), 4) for i in range(4))
    stable = all(iou(a, b) >= UNSTABLE_IOU for a, b in combinations(boxes, 2))
    return median, stable  # type: ignore[return-value]


def aggregate(votes: Sequence[Sequence[Box] | None]) -> dict:
    """Each vote is a list of region boxes, [] for "not usable", None for a failed call."""
    total = len(votes)
    usable = [v for v in votes if v]
    if total == 0 or len(usable) * 2 <= total:
        return {"status": "uncertain", "regions": [], "votes": total, "usable": len(usable)}
    count = sorted(len(v) for v in usable)[(len(usable) - 1) // 2]
    runs = [v for v in usable if len(v) == count]
    regions = []
    for i in range(count):
        box, stable = vote_box([run[i] for run in runs])
        regions.append({"box": box, "stable": stable})
    return {"status": "ok", "regions": regions, "votes": total, "usable": len(usable)}
