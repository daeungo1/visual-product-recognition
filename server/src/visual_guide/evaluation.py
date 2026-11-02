"""Run repeatable grounding evaluations on authorized local images."""

import json
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from visual_guide.consensus import aggregate_regions
from visual_guide.contracts import (
    MultiTargetRegionRequest,
    MultiTargetRegionResponse,
    PixelBox,
    RegionStatus,
)
from visual_guide.images import decode_image
from visual_guide.model_gateway import RegionRequest


@dataclass(frozen=True)
class EvaluationCase:
    """One unreviewed visual-grounding experiment."""

    case_id: str
    image_path: Path
    product_hint: str | None
    step_id: str
    component: str
    instruction: str


@dataclass(frozen=True)
class GuideEvaluationCase:
    """One reviewed multi-target evaluation case."""

    case_id: str
    image_path: Path
    request: MultiTargetRegionRequest
    ground_truth: dict[str, PixelBox]


def load_guide_evaluation_cases(
    *,
    cases_path: Path,
    ground_truth_path: Path,
    images: Path,
) -> list[GuideEvaluationCase]:
    """Join reviewed case metadata with target-level root-image boxes."""
    rows = json.loads(cases_path.read_text(encoding="utf-8"))
    truth_rows = json.loads(ground_truth_path.read_text(encoding="utf-8"))["cases"]
    cases = []
    for row in rows:
        if row.get("mode") != "reviewed_guide":
            continue
        case_id = row["case_id"]
        target_boxes = truth_rows[case_id]["targets"]
        request = MultiTargetRegionRequest(
            model_code=row["model_code"],
            guide_id=row["guide_id"],
            step_id=row["step_id"],
            target_ids=tuple(row["target_ids"]),
        )
        ground_truth = {
            target_id: PixelBox(
                x1=coordinates[0],
                y1=coordinates[1],
                x2=coordinates[2],
                y2=coordinates[3],
            )
            for target_id, coordinates in target_boxes.items()
        }
        if set(request.target_ids) != set(ground_truth):
            raise ValueError(f"Ground truth targets do not match case: {case_id}")
        cases.append(
            GuideEvaluationCase(
                case_id=case_id,
                image_path=images / row["image"],
                request=request,
                ground_truth=ground_truth,
            )
        )
    return cases


def _box_iou(left: PixelBox, right: PixelBox) -> float:
    x1 = max(left.x1, right.x1)
    y1 = max(left.y1, right.y1)
    x2 = min(left.x2, right.x2)
    y2 = min(left.y2, right.y2)
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    left_area = (left.x2 - left.x1) * (left.y2 - left.y1)
    right_area = (right.x2 - right.x1) * (right.y2 - right.y1)
    return intersection / (left_area + right_area - intersection)


def score_multi_target_response(
    response: MultiTargetRegionResponse,
    ground_truth: dict[str, PixelBox],
) -> dict:
    """Score independent target outcomes against reviewed root-image boxes."""
    response_ids = {target.target_id for target in response.targets}
    if response_ids != set(ground_truth):
        raise ValueError("Response targets do not match the ground truth.")
    target_metrics = {}
    for target in response.targets:
        truth = ground_truth[target.target_id]
        located = target.status is RegionStatus.LOCATED
        target_metrics[target.target_id] = {
            "status": target.status.value,
            "iou": (
                round(_box_iou(target.box, truth), 6)
                if located and target.box is not None
                else 0.0
            ),
            "point_in_box": (
                truth.x1 <= target.point.x <= truth.x2
                and truth.y1 <= target.point.y <= truth.y2
                if located and target.point is not None
                else False
            ),
            "false_not_visible": target.status is RegionStatus.NOT_VISIBLE,
            "attempts": target.attempts,
        }
    return {
        "partial_success": response.partial_success,
        "crop_retry_count": sum(target.attempts > 1 for target in response.targets),
        "targets": target_metrics,
    }


def _mime(path: Path) -> str:
    if path.suffix.lower() == ".png":
        return "image/png"
    if path.suffix.lower() in {".jpg", ".jpeg", ".jfif"}:
        return "image/jpeg"
    raise ValueError(f"Unsupported image extension: {path.suffix}")


def _draw_overlay(source: Path, destination: Path, proposal) -> None:
    with Image.open(source) as original:
        image = original.convert("RGB")
    draw = ImageDraw.Draw(image)
    if proposal.box is not None and proposal.point is not None:
        draw.rectangle(
            (proposal.box.x1, proposal.box.y1, proposal.box.x2, proposal.box.y2),
            outline="yellow",
            width=max(2, image.width // 250),
        )
        radius = max(4, image.width // 100)
        draw.ellipse(
            (
                proposal.point.x - radius,
                proposal.point.y - radius,
                proposal.point.x + radius,
                proposal.point.y + radius,
            ),
            fill="red",
        )
    image.save(destination, format="PNG")


def _draw_guide_overlay(
    source: Path,
    destination: Path,
    response: MultiTargetRegionResponse,
) -> None:
    with Image.open(source) as original:
        image = original.convert("RGB")
    draw = ImageDraw.Draw(image)
    colors = ("yellow", "cyan", "lime", "magenta")
    for index, target in enumerate(response.targets):
        if target.box is None or target.point is None:
            continue
        color = colors[index % len(colors)]
        draw.rectangle(
            (target.box.x1, target.box.y1, target.box.x2, target.box.y2),
            outline=color,
            width=max(2, image.width // 250),
        )
        radius = max(4, image.width // 100)
        draw.ellipse(
            (
                target.point.x - radius,
                target.point.y - radius,
                target.point.x + radius,
                target.point.y + radius,
            ),
            fill=color,
        )
        draw.text((target.box.x1, max(0, target.box.y1 - 14)), target.target_id, fill=color)
    image.save(destination, format="PNG")


def evaluate_cases(
    cases: list[EvaluationCase],
    *,
    gateway,
    output: Path,
    repeats: int = 3,
) -> dict:
    """Evaluate region proposals and write local-only reports and overlays."""
    if repeats < 1 or repeats > 5:
        raise ValueError("repeats must be between one and five")
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for case in cases:
        image = decode_image(case.image_path.read_bytes(), _mime(case.image_path))
        request = RegionRequest(
            step_id=case.step_id,
            component=case.component,
            instruction=case.instruction,
        )
        proposals = []
        region_proposals = []
        for repeat in range(1, repeats + 1):
            proposal = gateway.propose(request, image)
            region_proposals.append(proposal)
            proposals.append(proposal.model_dump(mode="json"))
            _draw_overlay(
                case.image_path,
                output / f"{case.case_id}-{repeat}-overlay.png",
                proposal,
            )
        reports.append(
            {
                "case_id": case.case_id,
                "image": case.image_path.name,
                "product_hint": case.product_hint,
                "reviewed_guide": False,
                "proposals": proposals,
                "consensus": aggregate_regions(region_proposals).model_dump(mode="json"),
            }
        )
    report = {
        "status": "experimental_unreviewed",
        "warning": "Region proposals are not reviewed product guides.",
        "cases": reports,
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def evaluate_guide_cases(
    cases: list[GuideEvaluationCase],
    *,
    service,
    output: Path,
    deployment: str,
    repeats: int = 3,
) -> dict:
    """Evaluate reviewed multi-target grounding and write local-only evidence."""
    if not cases:
        raise ValueError("at least one guide evaluation case is required")
    if repeats < 1 or repeats > 5:
        raise ValueError("repeats must be between one and five")
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    product_id = None
    for case in cases:
        image = decode_image(case.image_path.read_bytes(), _mime(case.image_path))
        runs = []
        for repeat in range(1, repeats + 1):
            started = time.perf_counter()
            response = service.ground(case.request, image)
            latency_seconds = time.perf_counter() - started
            product_id = product_id or response.product_id
            _draw_guide_overlay(
                case.image_path,
                output / f"{case.case_id}-{repeat}-overlay.png",
                response,
            )
            runs.append(
                {
                    "response": response.model_dump(mode="json"),
                    "metrics": score_multi_target_response(response, case.ground_truth),
                    "latency_seconds": round(latency_seconds, 3),
                }
            )
        reports.append(
            {
                "case_id": case.case_id,
                "image": case.image_path.name,
                "runs": runs,
            }
        )
    report = {
        "status": "reviewed_product_evaluation",
        "product_id": product_id,
        "deployment": deployment,
        "repeats": repeats,
        "cases": reports,
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report
