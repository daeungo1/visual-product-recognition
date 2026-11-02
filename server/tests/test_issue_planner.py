import base64
import json
from types import SimpleNamespace

import pytest

from visual_guide.images import ImageInput
from visual_guide.issue_contracts import IssueResolutionRequest
from visual_guide.issue_planner import (
    FakeIssuePlanner,
    FoundryIssuePlanner,
    PlannedIssue,
    PlannedTarget,
)


class FakeCompletions:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:
    def __init__(self, content=None, error=None):
        self.completions = FakeCompletions(content=content, error=error)
        self.chat = SimpleNamespace(completions=self.completions)


def _request(issue="세제를 어디에 넣고 어떤 버튼을 눌러야 해?"):
    return IssueResolutionRequest(
        product_hint="삼성 세탁건조기",
        model_code=None,
        user_issue=issue,
        current_state="제품 전면을 보고 있음",
    )


def _target(name, region="full_front"):
    return {
        "display_name": name,
        "canonical_name": name.casefold(),
        "aliases": [name],
        "purpose": "locate",
        "relative_region": region,
    }


def test_issue_planner_uses_strict_schema_without_geometry_fields():
    client = FakeClient(
        json.dumps(
            {
                "issue_intent": "detergent_loading_and_start",
                "visual_category": "washer_dryer",
                "targets": [
                    _target("세제 투입부", "lower_front"),
                    _target("시작 조작부", "upper_center"),
                ],
                "truncation_reason": None,
            }
        )
    )
    planner = FoundryIssuePlanner(client=client, deployment="gpt-6-1-terra")

    result = planner.plan(_request(), registry_summary=(), image=None)

    schema = client.completions.request["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "box" not in json.dumps(schema)
    assert "point" not in json.dumps(schema)
    assert [target.display_name for target in result.targets] == [
        "세제 투입부",
        "시작 조작부",
    ]


def test_issue_planner_deduplicates_and_caps_targets_with_reason():
    client = FakeClient(
        json.dumps(
            {
                "issue_intent": "inspect_parts",
                "visual_category": "washer",
                "targets": [
                    _target("조작부"),
                    _target("조작부"),
                    _target("세제함"),
                    _target("도어"),
                    _target("필터"),
                ],
                "truncation_reason": None,
            }
        )
    )
    planner = FoundryIssuePlanner(client=client, deployment="gpt-6-1-terra")

    result = planner.plan(_request("조작부, 세제함, 도어, 필터를 찾아줘"), (), None)

    assert [target.canonical_name for target in result.targets] == [
        "조작부",
        "세제함",
        "도어",
    ]
    assert result.truncation_reason is not None


def test_issue_planner_sends_optional_image_and_visual_category():
    client = FakeClient(
        json.dumps(
            {
                "issue_intent": "locate_panel",
                "visual_category": "monitor",
                "targets": [_target("입력 버튼", "lower_front")],
                "truncation_reason": None,
            }
        )
    )
    planner = FoundryIssuePlanner(client=client, deployment="gpt-6-1-terra")
    image = ImageInput(data=b"png", mime="image/png", width=100, height=80)

    result = planner.plan(_request("입력 버튼을 찾아줘"), (), image)

    content = client.completions.request["messages"][1]["content"]
    assert content[1]["image_url"]["url"] == (
        "data:image/png;base64," + base64.b64encode(b"png").decode()
    )
    assert result.visual_category == "monitor"


def test_issue_planner_propagates_provider_errors():
    planner = FoundryIssuePlanner(
        client=FakeClient(error=RuntimeError("provider unavailable")),
        deployment="gpt-6-1-terra",
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        planner.plan(_request(), (), None)


def test_fake_issue_planner_is_deterministic():
    planned = PlannedIssue(
        issue_intent="locate_panel",
        visual_category=None,
        targets=(
            PlannedTarget(
                display_name="조작부",
                canonical_name="control panel",
                aliases=("조작부",),
                purpose="locate",
                relative_region="upper_center",
            ),
        ),
        truncation_reason=None,
    )
    planner = FakeIssuePlanner(planned)

    assert planner.plan(_request(), (), None) is planned
    assert planner.plan(_request("다른 표현"), (), None) is planned
