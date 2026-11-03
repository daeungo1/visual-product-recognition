"""Strict GPT issue planning without trusted registry claims or geometry."""

import base64
import json
from typing import Literal

from pydantic import Field

from visual_guide.images import ImageInput
from visual_guide.issue_contracts import IssueResolutionRequest, StrictModel

SYSTEM_PROMPT = """\
Analyze one appliance help request. Normalize the desired outcome and split it
into at most useful atomic visible targets. Return names, aliases, purpose and
only a broad relative image region. Never return coordinates, boxes, product
IDs, manual claims or manipulation instructions. Product and guide approval are
owned by deterministic server checks. When a reviewed registry entry matches,
use its exact issue_intent token and exact canonical_name values. Otherwise use
short English snake_case intent and canonical target descriptions. When the
registry supplies required_states, use the exact normalized_state token that
best represents the visible current state.
"""


class PlannedTarget(StrictModel):
    """Untrusted request-scoped target proposed by the issue planner."""

    display_name: str = Field(min_length=1, max_length=128)
    canonical_name: str = Field(min_length=1, max_length=128)
    aliases: tuple[str, ...] = Field(min_length=1, max_length=12)
    purpose: str = Field(min_length=1, max_length=256)
    relative_region: Literal[
        "upper_left",
        "upper_center",
        "upper_right",
        "lower_front",
        "full_front",
    ]


class RawPlannedIssue(StrictModel):
    """Provider output before deterministic target bounding."""

    issue_intent: str = Field(min_length=1, max_length=128)
    normalized_state: str | None = Field(max_length=128)
    visual_category: str | None = Field(max_length=128)
    targets: tuple[PlannedTarget, ...] = Field(min_length=1, max_length=8)
    truncation_reason: str | None = Field(max_length=500)


class PlannedIssue(StrictModel):
    """Normalized bounded planner output."""

    issue_intent: str = Field(min_length=1, max_length=128)
    normalized_state: str | None = Field(default=None, max_length=128)
    visual_category: str | None = Field(default=None, max_length=128)
    targets: tuple[PlannedTarget, ...] = Field(min_length=1, max_length=3)
    truncation_reason: str | None = Field(default=None, max_length=500)


def _bounded(raw: RawPlannedIssue) -> PlannedIssue:
    unique: list[PlannedTarget] = []
    seen: set[str] = set()
    for target in raw.targets:
        canonical = target.canonical_name.casefold()
        if canonical in seen:
            continue
        seen.add(canonical)
        unique.append(target)
    dropped = max(0, len(unique) - 3)
    targets = tuple(unique[:3])
    reason = raw.truncation_reason
    if dropped:
        reason = f"{dropped} additional target(s) were omitted by the three-target limit."
    return PlannedIssue(
        issue_intent=raw.issue_intent,
        normalized_state=raw.normalized_state,
        visual_category=raw.visual_category,
        targets=targets,
        truncation_reason=reason,
    )


class FoundryIssuePlanner:
    """Call an injected OpenAI-compatible client for issue planning."""

    def __init__(self, *, client, deployment: str):
        self.client = client
        self.deployment = deployment

    def plan(
        self,
        request: IssueResolutionRequest,
        registry_summary,
        image: ImageInput | None,
    ) -> PlannedIssue:
        """Return bounded untrusted targets with no pixel geometry."""
        text = (
            f"Product hint: {request.product_hint or 'unknown'}\n"
            f"Model code: {request.model_code or 'unknown'}\n"
            f"Current state: {request.current_state or 'unknown'}\n"
            f"User issue: {request.user_issue}\n"
            "Reviewed registry summary: "
            f"{json.dumps(registry_summary, ensure_ascii=False)}"
        )
        content = [{"type": "text", "text": text}]
        if image is not None:
            encoded = base64.b64encode(image.data).decode()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{image.mime};base64,{encoded}",
                        "detail": "original",
                    },
                }
            )
        response = self.client.chat.completions.create(
            model=self.deployment,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "planned_issue",
                    "strict": True,
                    "schema": RawPlannedIssue.model_json_schema(),
                },
            },
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        )
        raw = RawPlannedIssue.model_validate_json(
            response.choices[0].message.content
        )
        return _bounded(raw)


class FakeIssuePlanner:
    """Deterministic issue planner for service tests."""

    def __init__(self, planned: PlannedIssue):
        self.planned = planned

    def plan(
        self,
        request: IssueResolutionRequest,
        registry_summary,
        image: ImageInput | None,
    ) -> PlannedIssue:
        """Return the configured plan."""
        return self.planned
