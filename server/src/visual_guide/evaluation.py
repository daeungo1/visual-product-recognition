"""Run repeatable grounding evaluations on authorized local images."""

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from visual_guide.consensus import aggregate_regions
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
