"""Keep the published guide and pairing boundary cases aligned with Android tests."""

import pytest
from pydantic import ValidationError

from guide_api.catalog import DEMO_GUIDE
from guide_api.cloud_contracts import CloudGuide, PairRequest


@pytest.mark.parametrize("length", [8, 256])
def test_pairing_accepts_mobile_boundary_lengths(length):
    assert len(PairRequest(code="x" * length).code) == length


@pytest.mark.parametrize("length", [7, 257])
def test_pairing_rejects_lengths_outside_mobile_contract(length):
    with pytest.raises(ValidationError):
        PairRequest(code="x" * length)


def test_published_guide_accepts_mobile_boundary_title_and_step_count():
    payload = DEMO_GUIDE.model_dump()
    payload["title"] = "G" * 500
    payload["steps"] = [
        {**payload["steps"][0], "id": f"step-{index}"} for index in range(128)
    ]
    guide = CloudGuide.model_validate(payload)
    assert len(guide.title) == 500
    assert len(guide.steps) == 128
    with pytest.raises(ValidationError):
        CloudGuide.model_validate({**payload, "title": "G" * 501})
    with pytest.raises(ValidationError):
        CloudGuide.model_validate(
            {**payload, "steps": [*payload["steps"], {**payload["steps"][0], "id": "step-128"}]}
        )
