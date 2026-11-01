import base64
import json
from types import SimpleNamespace

from visual_guide.contracts import RegionProposal, RegionStatus
from visual_guide.images import ImageInput
from visual_guide.model_gateway import FoundryRegionGateway, RegionRequest


class FakeCompletions:
    def __init__(self, content: str):
        self.content = content
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:
    def __init__(self, content: str):
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


def test_region_schema_is_strict_for_foundry_structured_outputs():
    schema = RegionProposal.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    for definition in schema["$defs"].values():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False
            assert set(definition["required"]) == set(definition["properties"])


def test_gateway_requests_absolute_pixel_structured_output():
    client = FakeClient(
        json.dumps(
            {
                "status": "located",
                "step_id": "open-filter-cover",
                "component": "top-filter-cover",
                "image_width": 500,
                "image_height": 500,
                "point": {"x": 250, "y": 180},
                "box": {"x1": 75, "y1": 130, "x2": 430, "y2": 245},
                "evidence": "The upper inlet cover is visible.",
            }
        )
    )
    gateway = FoundryRegionGateway(client=client, deployment="gpt-6-1-terra")
    image = ImageInput(data=b"jpeg", mime="image/jpeg", width=500, height=500)

    result = gateway.propose(
        RegionRequest(
            step_id="open-filter-cover",
            component="top-filter-cover",
            instruction="Lift the top filter cover.",
        ),
        image,
    )

    assert result.status is RegionStatus.LOCATED
    assert gateway.ready() is True
    request = client.chat.completions.request
    assert request["model"] == "gpt-6-1-terra"
    assert request["response_format"]["type"] == "json_schema"
    user_content = request["messages"][1]["content"]
    assert "500 x 500" in user_content[0]["text"]
    assert user_content[1]["image_url"]["url"] == (
        "data:image/jpeg;base64," + base64.b64encode(b"jpeg").decode()
    )


def test_gateway_preserves_explicit_not_visible_outcome():
    client = FakeClient(
        json.dumps(
            {
                "status": "not_visible",
                "step_id": "remove-filter",
                "component": "air-filter",
                "image_width": 500,
                "image_height": 500,
                "point": None,
                "box": None,
                "evidence": "The filter is behind the closed cover.",
            }
        )
    )
    gateway = FoundryRegionGateway(client=client, deployment="gpt-6-1-terra")

    result = gateway.propose(
        RegionRequest(
            step_id="remove-filter",
            component="air-filter",
            instruction="Remove the air filter.",
        ),
        ImageInput(data=b"jpeg", mime="image/jpeg", width=500, height=500),
    )

    assert result.status is RegionStatus.NOT_VISIBLE
    assert result.point is None
