import json
from pathlib import Path

from PIL import Image

from visual_guide.contracts import (
    GroundedTarget,
    MultiTargetRegionRequest,
    MultiTargetRegionResponse,
    PixelBox,
    PixelPoint,
    RegionProposal,
    RegionStatus,
)
from visual_guide.evaluation import (
    EvaluationCase,
    GuideEvaluationCase,
    evaluate_cases,
    evaluate_guide_cases,
    load_guide_evaluation_cases,
    score_multi_target_response,
)


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


class FakeGroundingService:
    def ground(self, request, image):
        return MultiTargetRegionResponse(
            product_id="samsung-wd80h25bhs",
            guide_id=request.guide_id,
            step_id=request.step_id,
            image_width=image.width,
            image_height=image.height,
            targets=(
                GroundedTarget(
                    target_id="control_panel",
                    component="조작부",
                    status=RegionStatus.LOCATED,
                    point=PixelPoint(x=30, y=30),
                    box=PixelBox(x1=10, y1=10, x2=50, y2=50),
                    evidence="visible",
                    attempts=1,
                    retake_instruction=None,
                ),
            ),
            partial_success=False,
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


def test_multi_target_metrics_score_geometry_and_false_not_visible():
    response = MultiTargetRegionResponse(
        product_id="samsung-wd80h25bhs",
        guide_id="detergent-and-controls",
        step_id="locate-detergent-and-controls",
        image_width=100,
        image_height=80,
        targets=(
            GroundedTarget(
                target_id="control_panel",
                component="조작부",
                status=RegionStatus.LOCATED,
                point=PixelPoint(x=30, y=30),
                box=PixelBox(x1=10, y1=10, x2=50, y2=50),
                evidence="visible",
                attempts=1,
                retake_instruction=None,
            ),
            GroundedTarget(
                target_id="detergent_dispenser",
                component="세제함 전면 덮개",
                status=RegionStatus.NOT_VISIBLE,
                point=None,
                box=None,
                evidence="not visible",
                attempts=2,
                retake_instruction="전면 하단을 촬영하세요.",
            ),
        ),
        partial_success=True,
    )

    metrics = score_multi_target_response(
        response,
        {
            "control_panel": PixelBox(x1=10, y1=10, x2=50, y2=50),
            "detergent_dispenser": PixelBox(x1=0, y1=55, x2=100, y2=80),
        },
    )

    assert metrics["partial_success"] is True
    assert metrics["crop_retry_count"] == 1
    assert metrics["targets"]["control_panel"]["iou"] == 1.0
    assert metrics["targets"]["control_panel"]["point_in_box"] is True
    assert metrics["targets"]["detergent_dispenser"]["false_not_visible"] is True


def test_uncertain_target_is_not_counted_as_false_not_visible():
    response = MultiTargetRegionResponse(
        product_id="samsung-wd80h25bhs",
        guide_id="detergent-and-controls",
        step_id="locate-detergent-and-controls",
        image_width=100,
        image_height=80,
        targets=(
            GroundedTarget(
                target_id="detergent_dispenser",
                component="세제함 전면 덮개",
                status=RegionStatus.UNCERTAIN,
                point=None,
                box=None,
                evidence="ambiguous",
                attempts=2,
                retake_instruction="전면 하단을 촬영하세요.",
            ),
        ),
        partial_success=False,
    )

    metrics = score_multi_target_response(
        response,
        {"detergent_dispenser": PixelBox(x1=0, y1=55, x2=100, y2=80)},
    )

    assert metrics["targets"]["detergent_dispenser"]["false_not_visible"] is False
    assert metrics["crop_retry_count"] == 1


def test_guide_evaluation_writes_target_metrics_and_overlay(tmp_path: Path):
    image_path = tmp_path / "combo.png"
    Image.new("RGB", (100, 80), "white").save(image_path)
    output = tmp_path / "guide-results"

    report = evaluate_guide_cases(
        [
            GuideEvaluationCase(
                case_id="combo-front",
                image_path=image_path,
                request=MultiTargetRegionRequest(
                    model_code="WD80H25BHS",
                    guide_id="detergent-and-controls",
                    step_id="locate-detergent-and-controls",
                    target_ids=("control_panel",),
                ),
                ground_truth={
                    "control_panel": PixelBox(x1=10, y1=10, x2=50, y2=50)
                },
            )
        ],
        service=FakeGroundingService(),
        output=output,
        repeats=2,
        deployment="gpt-6-1-terra",
    )

    assert report["product_id"] == "samsung-wd80h25bhs"
    assert report["deployment"] == "gpt-6-1-terra"
    assert report["cases"][0]["runs"][0]["metrics"]["targets"]["control_panel"][
        "iou"
    ] == 1.0
    assert (output / "combo-front-1-overlay.png").is_file()


def test_load_guide_evaluation_cases_joins_case_and_ground_truth(tmp_path: Path):
    cases_path = tmp_path / "cases.json"
    truth_path = tmp_path / "truth.json"
    cases_path.write_text(
        json.dumps(
            [
                {
                    "mode": "reviewed_guide",
                    "case_id": "combo-front",
                    "image": "combo.png",
                    "model_code": "WD80H25BHS",
                    "guide_id": "detergent-and-controls",
                    "step_id": "locate-detergent-and-controls",
                    "target_ids": ["detergent_dispenser", "control_panel"],
                }
            ]
        ),
        encoding="utf-8",
    )
    truth_path.write_text(
        json.dumps(
            {
                "cases": {
                    "combo-front": {
                        "targets": {
                            "detergent_dispenser": [0, 55, 100, 80],
                            "control_panel": [10, 10, 50, 50],
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    cases = load_guide_evaluation_cases(
        cases_path=cases_path,
        ground_truth_path=truth_path,
        images=tmp_path,
    )

    assert len(cases) == 1
    assert cases[0].image_path == tmp_path / "combo.png"
    assert cases[0].request.target_ids == (
        "detergent_dispenser",
        "control_panel",
    )
    assert cases[0].ground_truth["control_panel"] == PixelBox(
        x1=10,
        y1=10,
        x2=50,
        y2=50,
    )
