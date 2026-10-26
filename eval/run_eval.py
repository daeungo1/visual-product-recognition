"""Compute descriptive PoC metrics from independently labeled observations."""

import argparse
import json
import logging
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, TypedDict

LOGGER = logging.getLogger(__name__)
MAX_TIME_MS = 604_800_000


class IdentificationMetrics(TypedDict):
    samples: int
    registered_samples: int
    unsupported_samples: int
    top1_accuracy: float | None
    top3_accuracy: float | None
    unsupported_candidate_rate: float | None
    manual_selections: int
    latency_samples: int
    latency_ms_p95: float | None


class AlignmentMetrics(TypedDict):
    frames: int
    target_visible_frames: int
    evaluated_overlay_frames: int
    missing_overlay_frames: int
    stale_overlay_frames: int
    off_target_overlay_frames: int
    target_observation_ms: float
    correct_overlay_ms: float
    center_error_pixels_p95: float | None
    normalized_center_error_p95: float | None
    overlay_availability: float | None
    tracking_timing_samples: int
    tracking_ms_p95: float | None


class ScenarioMetrics(TypedDict):
    participants: int
    unassisted_completion_rate: float
    meets_80_percent_target: bool | None


class CompletionMetrics(TypedDict):
    trials: int
    novice_trials: int
    unassisted_completion_rate: float | None
    manual_confirmations: int
    elapsed_ms_p50: float | None
    by_scenario: dict[str, ScenarioMetrics]


class EvaluationReport(TypedDict):
    schema_version: Literal[1]
    status: Literal["insufficient_data", "measured"]
    identification: IdentificationMetrics
    alignment: AlignmentMetrics
    completion: CompletionMetrics
    warnings: list[str]


class _Trial(TypedDict):
    completed: bool
    unassisted: bool
    elapsed_ms: float
    manual_confirmations: int


def _records(payload: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{key} must be an array of observation objects")
    return value


def _keys(row: Mapping[str, object], expected: set[str], context: str) -> None:
    if set(row) != expected:
        raise ValueError(f"{context}: expected fields {', '.join(sorted(expected))}")


def _text(row: Mapping[str, object], key: str, context: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a nonempty string")
    return value


def _bool(row: Mapping[str, object], key: str, context: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return value


def _time(row: Mapping[str, object], key: str, context: str) -> float:
    value = row.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or not 0 <= value <= MAX_TIME_MS
    ):
        raise ValueError(f"{context}.{key} must be finite milliseconds in [0, {MAX_TIME_MS}]")
    return float(value)


def _optional_time(row: Mapping[str, object], key: str, context: str) -> float | None:
    return None if row.get(key) is None else _time(row, key, context)


def _coordinates(value: object, size: int, context: str) -> list[float]:
    if not isinstance(value, list) or len(value) != size:
        raise ValueError(f"{context} must contain {size} pixel coordinates")
    result = []
    for coordinate in value:
        if (
            isinstance(coordinate, bool)
            or not isinstance(coordinate, int | float)
            or not math.isfinite(coordinate)
            or abs(coordinate) > 10_000_000
        ):
            raise ValueError(f"{context} contains an invalid coordinate")
        result.append(float(coordinate))
    return result


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _identification(rows: list[Mapping[str, object]]) -> IdentificationMetrics:
    seen = set()
    registered_count = unsupported_count = top1 = top3 = false_candidates = manual = 0
    latencies = []
    for row in rows:
        _keys(
            row,
            {
                "sample_id", "expected_model_id", "candidate_model_ids",
                "registered", "manual_selection", "latency_ms",
            },
            "identification",
        )
        sample_id = _text(row, "sample_id", "identification")
        if sample_id in seen:
            raise ValueError(f"duplicate identification sample_id: {sample_id}")
        seen.add(sample_id)
        registered = _bool(row, "registered", sample_id)
        expected = row["expected_model_id"]
        if registered:
            expected = _text(row, "expected_model_id", sample_id)
        elif expected is not None and (not isinstance(expected, str) or not expected.strip()):
            raise ValueError(f"{sample_id}.expected_model_id must be a string or null")
        candidates = row["candidate_model_ids"]
        if (
            not isinstance(candidates, list)
            or len(candidates) > 100
            or any(not isinstance(item, str) or not item.strip() for item in candidates)
            or len(candidates) != len(set(candidates))
        ):
            raise ValueError(f"{sample_id}.candidate_model_ids must be unique nonempty strings")
        manual += int(_bool(row, "manual_selection", sample_id))
        latency = _optional_time(row, "latency_ms", sample_id)
        if latency is not None:
            latencies.append(latency)
        if registered:
            registered_count += 1
            top1 += int(bool(candidates) and candidates[0] == expected)
            top3 += int(expected in candidates[:3])
        else:
            unsupported_count += 1
            false_candidates += int(bool(candidates))
    return {
        "samples": len(rows),
        "registered_samples": registered_count,
        "unsupported_samples": unsupported_count,
        "top1_accuracy": _ratio(top1, registered_count),
        "top3_accuracy": _ratio(top3, registered_count),
        "unsupported_candidate_rate": _ratio(false_candidates, unsupported_count),
        "manual_selections": manual,
        "latency_samples": len(latencies),
        "latency_ms_p95": _percentile(latencies, 0.95),
    }


def _alignment(rows: list[Mapping[str, object]]) -> AlignmentMetrics:
    seen = set()
    pixel_errors = []
    normalized_errors = []
    timings = []
    visible_frames = missing = stale = off_target = 0
    observation_ms = correct_ms = 0.0
    for row in rows:
        _keys(
            row,
            {
                "frame_id", "target_visible", "tracking_valid", "overlay_visible",
                "predicted_center", "true_button_rect", "observation_ms", "tracking_ms",
            },
            "alignment",
        )
        frame_id = _text(row, "frame_id", "alignment")
        if frame_id in seen:
            raise ValueError(f"duplicate alignment frame_id: {frame_id}")
        seen.add(frame_id)
        visible = _bool(row, "target_visible", frame_id)
        tracked = _bool(row, "tracking_valid", frame_id)
        shown = _bool(row, "overlay_visible", frame_id)
        duration = _time(row, "observation_ms", frame_id)
        if duration <= 0:
            raise ValueError(f"{frame_id}.observation_ms must be positive")
        timing = _optional_time(row, "tracking_ms", frame_id)
        if timing is not None:
            timings.append(timing)
        center = (
            _coordinates(row["predicted_center"], 2, f"{frame_id}.predicted_center")
            if shown else None
        )
        if not shown and row["predicted_center"] is not None:
            raise ValueError(f"{frame_id}: hidden overlay must have null predicted_center")
        rect = (
            _coordinates(row["true_button_rect"], 4, f"{frame_id}.true_button_rect")
            if row["true_button_rect"] is not None else None
        )
        if visible and rect is None:
            raise ValueError(f"{frame_id}: visible target requires true_button_rect")
        if rect is not None and (rect[2] <= rect[0] or rect[3] <= rect[1]):
            raise ValueError(f"{frame_id}.true_button_rect must have positive area")
        stale += int(shown and not tracked)
        off_target += int(shown and not visible)
        if visible:
            visible_frames += 1
            observation_ms += duration
            missing += int(not shown)
        if visible and tracked and shown and rect is not None and center is not None:
            error = math.hypot(
                center[0] - (rect[0] + rect[2]) / 2,
                center[1] - (rect[1] + rect[3]) / 2,
            )
            normalized = error / min(rect[2] - rect[0], rect[3] - rect[1])
            if not math.isfinite(normalized):
                raise ValueError(f"{frame_id}: normalized alignment error is not finite")
            pixel_errors.append(error)
            normalized_errors.append(normalized)
            if normalized <= 0.25:
                correct_ms += duration
    return {
        "frames": len(rows),
        "target_visible_frames": visible_frames,
        "evaluated_overlay_frames": len(pixel_errors),
        "missing_overlay_frames": missing,
        "stale_overlay_frames": stale,
        "off_target_overlay_frames": off_target,
        "target_observation_ms": observation_ms,
        "correct_overlay_ms": correct_ms,
        "center_error_pixels_p95": _percentile(pixel_errors, 0.95),
        "normalized_center_error_p95": _percentile(normalized_errors, 0.95),
        "overlay_availability": _ratio(correct_ms, observation_ms),
        "tracking_timing_samples": len(timings),
        "tracking_ms_p95": _percentile(timings, 0.95),
    }


def _completion(rows: list[Mapping[str, object]]) -> CompletionMetrics:
    seen = set()
    scenarios: dict[str, list[_Trial]] = defaultdict(list)
    novice_rows: list[_Trial] = []
    for row in rows:
        _keys(
            row,
            {
                "participant_id", "scenario_id", "novice", "completed",
                "assisted", "elapsed_ms", "manual_confirmations",
            },
            "sessions",
        )
        participant = _text(row, "participant_id", "session")
        scenario = _text(row, "scenario_id", participant)
        key = (participant, scenario)
        if key in seen:
            raise ValueError(f"duplicate participant/scenario trial: {participant}/{scenario}")
        seen.add(key)
        novice = _bool(row, "novice", participant)
        completed = _bool(row, "completed", participant)
        assisted = _bool(row, "assisted", participant)
        elapsed = _time(row, "elapsed_ms", participant)
        confirmations = row["manual_confirmations"]
        if (
            isinstance(confirmations, bool)
            or not isinstance(confirmations, int)
            or not 0 <= confirmations <= 10_000
        ):
            raise ValueError(f"{participant}.manual_confirmations must be a nonnegative integer")
        if novice:
            trial: _Trial = {
                "completed": completed,
                "unassisted": completed and not assisted,
                "elapsed_ms": elapsed,
                "manual_confirmations": confirmations,
            }
            novice_rows.append(trial)
            scenarios[scenario].append(trial)
    by_scenario: dict[str, ScenarioMetrics] = {}
    for scenario, trials in sorted(scenarios.items()):
        rate = sum(int(trial["unassisted"]) for trial in trials) / len(trials)
        by_scenario[scenario] = {
            "participants": len(trials),
            "unassisted_completion_rate": rate,
            "meets_80_percent_target": rate >= 0.8 if len(trials) >= 5 else None,
        }
    return {
        "trials": len(rows),
        "novice_trials": len(novice_rows),
        "unassisted_completion_rate": _ratio(
            sum(int(trial["unassisted"]) for trial in novice_rows), len(novice_rows)
        ),
        "manual_confirmations": sum(trial["manual_confirmations"] for trial in novice_rows),
        "elapsed_ms_p50": _percentile([trial["elapsed_ms"] for trial in novice_rows], 0.5),
        "by_scenario": by_scenario,
    }


def evaluate(payload: Mapping[str, object]) -> EvaluationReport:
    """Return measured values, denominators and explicit insufficient-data warnings."""
    if not isinstance(payload, dict):
        raise ValueError("dataset must be a JSON object")
    _keys(payload, {"identification", "alignment", "sessions"}, "dataset")
    identification = _identification(_records(payload, "identification"))
    alignment = _alignment(_records(payload, "alignment"))
    completion = _completion(_records(payload, "sessions"))
    warnings = []
    if not identification["registered_samples"]:
        warnings.append("No registered-product identification observations.")
    if not identification["unsupported_samples"]:
        warnings.append("No unsupported-product negative observations.")
    if not alignment["evaluated_overlay_frames"]:
        warnings.append("No valid tracked overlays with independent ground truth.")
    if not completion["novice_trials"] or any(
        scenario["meets_80_percent_target"] is None
        for scenario in completion["by_scenario"].values()
    ):
        warnings.append("At least five distinct novice trials per scenario are required.")
    return {
        "schema_version": 1,
        "status": "insufficient_data" if warnings else "measured",
        "identification": identification,
        "alignment": alignment,
        "completion": completion,
        "warnings": warnings,
    }


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Independently labeled observation JSON")
    parser.add_argument("--output", "-o", type=Path, help="Write a computed JSON report")
    return parser


def main() -> int:
    args = create_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if args.output and args.output.resolve() == args.dataset.resolve():
            raise ValueError("output must not overwrite the input dataset")
        payload = json.loads(args.dataset.read_text(encoding="utf-8"))
        report = evaluate(payload)
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        for warning in report["warnings"]:
            LOGGER.warning(warning)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(encoded, encoding="utf-8")
        else:
            print(encoded, end="")
    except (OSError, ValueError) as error:
        LOGGER.error("Evaluation failed: %s", error)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
