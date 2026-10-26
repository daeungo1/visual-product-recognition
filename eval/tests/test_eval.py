"""Metrics are computed from labeled observations, not generated success data."""

import runpy
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1] / "run_eval.py"


def evaluate(payload):
    assert RUNNER.is_file(), "The evaluation runner has not been implemented."
    return runpy.run_path(str(RUNNER))["evaluate"](payload)


def empty():
    return {"identification": [], "alignment": [], "sessions": []}


def identity(sample_id, expected, candidates, registered=True, manual=False):
    return {
        "sample_id": sample_id,
        "expected_model_id": expected,
        "candidate_model_ids": candidates,
        "registered": registered,
        "manual_selection": manual,
        "latency_ms": 1000,
    }


def frame(frame_id, *, tracked=True, shown=True, visible=True, center=(5, 5)):
    return {
        "frame_id": frame_id,
        "target_visible": visible,
        "tracking_valid": tracked,
        "overlay_visible": shown,
        "predicted_center": list(center) if shown else None,
        "true_button_rect": [0, 0, 10, 10] if visible else None,
        "observation_ms": 10,
        "tracking_ms": 20,
    }


def test_empty_measurements_are_not_a_success_report():
    result = evaluate(empty())
    assert result["status"] == "insufficient_data"
    assert result["identification"]["top1_accuracy"] is None
    assert result["alignment"]["overlay_availability"] is None
    assert result["completion"]["unassisted_completion_rate"] is None
    assert result["warnings"]


def test_manual_choice_does_not_repair_automatic_identification():
    payload = empty()
    payload["identification"] = [
        identity("a", "model-a", ["model-a"]),
        identity("b", "model-b", ["model-c", "model-b"], manual=True),
        identity("c", "model-b", []),
        identity("d", None, [], registered=False),
    ]
    metrics = evaluate(payload)["identification"]
    assert metrics["registered_samples"] == 3
    assert metrics["top1_accuracy"] == pytest.approx(1 / 3)
    assert metrics["top3_accuracy"] == pytest.approx(2 / 3)
    assert metrics["manual_selections"] == 1
    assert metrics["unsupported_candidate_rate"] == 0


def test_unknown_product_with_candidate_counts_as_unsupported_candidate():
    payload = empty()
    payload["identification"] = [identity("unknown", None, ["wrong"], registered=False)]
    metrics = evaluate(payload)["identification"]
    assert metrics["unsupported_candidate_rate"] == 1
    assert metrics["top1_accuracy"] is None


def test_missing_overlay_is_in_the_time_weighted_availability_denominator():
    payload = empty()
    payload["alignment"] = [frame("a"), frame("b", shown=False)]
    payload["alignment"][1]["observation_ms"] = 30
    metrics = evaluate(payload)["alignment"]
    assert metrics["normalized_center_error_p95"] == 0
    assert metrics["overlay_availability"] == pytest.approx(0.25)
    assert metrics["missing_overlay_frames"] == 1


def test_stale_overlay_and_out_of_view_frame_are_not_alignment_successes():
    payload = empty()
    payload["alignment"] = [frame("a", tracked=False), frame("b", visible=False)]
    metrics = evaluate(payload)["alignment"]
    assert metrics["stale_overlay_frames"] == 1
    assert metrics["overlay_availability"] == 0
    assert metrics["normalized_center_error_p95"] is None


def test_error_is_normalized_by_shorter_button_edge_and_percentile_is_inclusive():
    payload = empty()
    payload["alignment"] = [frame("a", center=(5, 5)), frame("b", center=(7.5, 5))]
    metrics = evaluate(payload)["alignment"]
    assert metrics["normalized_center_error_p95"] == pytest.approx(0.2375)
    assert metrics["center_error_pixels_p95"] == pytest.approx(2.375)


def test_five_novices_four_unassisted_completions_meet_target():
    payload = empty()
    payload["sessions"] = [
        {
            "participant_id": str(i),
            "scenario_id": "cooling",
            "novice": True,
            "completed": i < 4,
            "assisted": False,
            "elapsed_ms": 60_000,
            "manual_confirmations": i,
        }
        for i in range(5)
    ]
    metrics = evaluate(payload)["completion"]
    assert metrics["unassisted_completion_rate"] == 0.8
    scenario = metrics["by_scenario"]["cooling"]
    assert scenario["participants"] == 5
    assert scenario["meets_80_percent_target"] is True
    assert metrics["manual_confirmations"] == 10


def test_small_novice_sample_does_not_pass_minimum_participant_requirement():
    payload = empty()
    payload["sessions"] = [
        {
            "participant_id": "one",
            "scenario_id": "cooling",
            "novice": True,
            "completed": True,
            "assisted": False,
            "elapsed_ms": 1000,
            "manual_confirmations": 0,
        }
    ]
    scenario = evaluate(payload)["completion"]["by_scenario"]["cooling"]
    assert scenario["unassisted_completion_rate"] == 1
    assert scenario["meets_80_percent_target"] is None


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), -1, True])
def test_invalid_latency_is_rejected(bad_value):
    payload = empty()
    payload["identification"] = [identity("a", "model", ["model"])]
    payload["identification"][0]["latency_ms"] = bad_value
    with pytest.raises(ValueError, match="latency_ms"):
        evaluate(payload)


def test_duplicate_participant_scenario_is_rejected():
    payload = empty()
    record = {
        "participant_id": "same",
        "scenario_id": "cooling",
        "novice": True,
        "completed": True,
        "assisted": False,
        "elapsed_ms": 1000,
        "manual_confirmations": 0,
    }
    payload["sessions"] = [record, record.copy()]
    with pytest.raises(ValueError, match="duplicate"):
        evaluate(payload)
