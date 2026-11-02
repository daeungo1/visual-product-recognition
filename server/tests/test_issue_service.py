from pathlib import Path

import pytest

from visual_guide.issue_contracts import (
    IssueResolutionRequest,
    ProductStatus,
    SupportMode,
    TargetSource,
)
from visual_guide.issue_planner import PlannedIssue, PlannedTarget
from visual_guide.issue_service import IssueResolutionService
from visual_guide.registry import load_reviewed_registry


def _registry():
    root = Path(__file__).parents[1] / "src" / "visual_guide" / "references"
    return load_reviewed_registry(root)


def _planned(
    *,
    intent="detergent_loading",
    state="front_visible",
    targets=None,
    category="washer_dryer_combo",
):
    return PlannedIssue(
        issue_intent=intent,
        normalized_state=state,
        visual_category=category,
        targets=targets
        or (
            PlannedTarget(
                display_name="세제 넣는 곳",
                canonical_name="detergent input",
                aliases=("세제 넣는 곳", "세제함"),
                purpose="locate",
                relative_region="full_front",
            ),
            PlannedTarget(
                display_name="알림 표시부",
                canonical_name="alert display",
                aliases=("알림 표시부",),
                purpose="locate",
                relative_region="upper_center",
            ),
        ),
        truncation_reason=None,
    )


class QueuePlanner:
    def __init__(self, *plans):
        self.plans = list(plans)
        self.calls = []

    def plan(self, request, registry_summary, image):
        self.calls.append((request, registry_summary, image))
        plan = self.plans.pop(0)
        if isinstance(plan, Exception):
            raise plan
        return plan


def _request(model_code="WD80H25BHS", hint="삼성 세탁건조기"):
    return IssueResolutionRequest(
        product_hint=hint,
        model_code=model_code,
        user_issue="세제를 어디에 넣고 알림 표시부도 찾아줘",
        current_state="제품 전면",
    )


def test_registered_issue_maps_reviewed_and_zero_shot_targets():
    service = IssueResolutionService(
        planner=QueuePlanner(_planned()),
        registry=_registry(),
    )

    resolution = service.resolve(_request(), image=None)

    assert resolution.product_status is ProductStatus.REGISTERED
    assert resolution.support_mode is SupportMode.REVIEWED_GUIDE
    assert [target.source for target in resolution.targets] == [
        TargetSource.REGISTRY,
        TargetSource.ZERO_SHOT,
    ]
    assert resolution.targets[0].registry_component_id == "detergent_dispenser"
    assert resolution.targets[0].manual_evidence
    assert [guide.guide_id for guide in resolution.guide_candidates] == [
        "detergent-and-controls"
    ]


def test_product_hint_candidate_requires_confirmation_and_no_reviewed_target():
    service = IssueResolutionService(
        planner=QueuePlanner(_planned()),
        registry=_registry(),
    )

    resolution = service.resolve(
        _request(model_code=None, hint="비스포크 AI 콤보"),
        image=None,
    )

    assert resolution.product_status is ProductStatus.CANDIDATE
    assert resolution.requires_product_confirmation is True
    assert all(target.source is TargetSource.ZERO_SHOT for target in resolution.targets)
    assert resolution.guide_candidates == ()


def test_unknown_product_stays_zero_shot_locate_only():
    service = IssueResolutionService(
        planner=QueuePlanner(_planned(category=None)),
        registry=_registry(),
    )

    resolution = service.resolve(
        _request(model_code=None, hint="unknown appliance"),
        image=None,
    )

    assert resolution.product_status is ProductStatus.UNKNOWN
    assert resolution.support_mode is SupportMode.ZERO_SHOT_LOCATE_ONLY
    assert resolution.product_candidates == ()
    assert "모델 라벨" in resolution.next_capture_instruction


def test_registered_unknown_state_returns_no_guide_candidate():
    service = IssueResolutionService(
        planner=QueuePlanner(_planned(state="door_open")),
        registry=_registry(),
    )

    resolution = service.resolve(_request(), image=None)

    assert resolution.product_status is ProductStatus.REGISTERED
    assert resolution.guide_candidates == ()
    assert "상태" in resolution.next_capture_instruction


def test_target_rename_changes_display_only():
    service = IssueResolutionService(
        planner=QueuePlanner(_planned()),
        registry=_registry(),
    )
    resolution = service.resolve(_request(), image=None)
    original = resolution.targets[0]

    confirmed = service.confirm_targets(
        resolution,
        display_renames={original.target_id: "세제 넣는 부분"},
    )

    renamed = confirmed[0]
    assert renamed.display_name == "세제 넣는 부분"
    assert renamed.canonical_name == original.canonical_name
    assert renamed.registry_component_id == original.registry_component_id
    assert renamed.manual_evidence == original.manual_evidence


def test_added_target_is_replanned_instead_of_trusted():
    added = PlannedIssue(
        issue_intent="locate_filter",
        normalized_state="front_visible",
        visual_category="washer_dryer_combo",
        targets=(
            PlannedTarget(
                display_name="먼지 필터",
                canonical_name="lint filter",
                aliases=("먼지 필터",),
                purpose="locate",
                relative_region="upper_right",
            ),
        ),
        truncation_reason=None,
    )
    planner = QueuePlanner(_planned(targets=(_planned().targets[0],)), added)
    service = IssueResolutionService(planner=planner, registry=_registry())
    request = _request()
    resolution = service.resolve(request, image=None)

    confirmed = service.confirm_targets(
        resolution,
        display_renames={},
        added_target_phrases=("필터도 찾아줘",),
        original_request=request,
        image=None,
    )

    assert len(planner.calls) == 2
    assert confirmed[-1].canonical_name == "lint filter"
    assert confirmed[-1].source is TargetSource.ZERO_SHOT


def test_planner_failure_is_not_converted_to_unknown_product():
    service = IssueResolutionService(
        planner=QueuePlanner(RuntimeError("planner unavailable")),
        registry=_registry(),
    )

    with pytest.raises(RuntimeError, match="planner unavailable"):
        service.resolve(_request(), image=None)
