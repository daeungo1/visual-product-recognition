import json
from pathlib import Path

from PIL import Image

from visual_guide.contracts import PixelBox, PixelPoint, RegionProposal, RegionStatus
from visual_guide.evaluation import EvaluationCase, evaluate_cases


class FakeGateway:
    def propose(self, request, image):
        return RegionProposal(
            status=RegionStatus.LOCATED,
            step_id=request.step_id,
            component=request.component,
            image_width=image.width,
            image_height=image.height,
            point=PixelPoint(x=image.width // 2, y=image.height // 2),
            box=PixelBox(x1=10, y1=10, x2=image.width - 10, y2=image.height - 10),
            evidence="visible",
        )


def test_evaluation_writes_report_and_overlay(tmp_path: Path):
    image_path = tmp_path / "aircon.jpg"
    Image.new("RGB", (100, 80), "white").save(image_path)
    output = tmp_path / "results"

    report = evaluate_cases(
        [
            EvaluationCase(
                case_id="aircon",
                image_path=image_path,
                product_hint="AR07B9350HZS",
                step_id="open-filter-cover",
                component="top-filter-cover",
                instruction="Locate only; guide applicability is not yet reviewed.",
            )
        ],
        gateway=FakeGateway(),
        output=output,
        repeats=3,
    )

    assert report["cases"][0]["proposals"][0]["status"] == "located"
    assert report["cases"][0]["consensus"]["status"] == "located"
    assert (output / "aircon-1-overlay.png").is_file()
    assert json.loads((output / "report.json").read_text(encoding="utf-8")) == report


def test_evaluation_does_not_claim_a_reviewed_guide(tmp_path: Path):
    image_path = tmp_path / "washer.png"
    Image.new("RGB", (100, 80), "white").save(image_path)

    report = evaluate_cases(
        [
            EvaluationCase(
                case_id="washer",
                image_path=image_path,
                product_hint=None,
                step_id="locate-service-cover",
                component="lower-service-cover",
                instruction="Visual grounding experiment only.",
            )
        ],
        gateway=FakeGateway(),
        output=tmp_path / "results",
        repeats=1,
    )

    assert report["cases"][0]["reviewed_guide"] is False
    assert report["cases"][0]["product_hint"] is None
