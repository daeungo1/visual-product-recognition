"""Offline region proposal via an Azure Foundry vision model (Entra auth, no keys).

Mock-up scope: the model only proposes a labelled point and box for named components.
Output is a draft for human review, never an Overlay by itself.
"""

import base64
import json
from dataclasses import dataclass

SYSTEM = (
    "You locate named product components in one image. Reply with JSON only: "
    '{"regions":[{"component":str,"point":[x,y],"box":[x1,y1,x2,y2],"visible":bool}]}. '
    "Coordinates are normalized 0..1 in the sent image. Use visible=false if not seen."
)


@dataclass(frozen=True)
class Region:
    component: str
    point: tuple[float, float]
    box: tuple[float, float, float, float]


def _unit(values, count):
    if not isinstance(values, list) or len(values) != count:
        return None
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in values):
        return None
    if not all(0.0 <= v <= 1.0 for v in values):
        return None
    return tuple(float(v) for v in values)


def parse_regions(text: str, components: list[str]) -> list[Region]:
    """Keep only requested, visible, well-formed regions with the point inside the box."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    items = data.get("regions") if isinstance(data, dict) else None
    out: dict[str, Region] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("visible") is not True:
            continue
        name = item.get("component")
        point, box = _unit(item.get("point"), 2), _unit(item.get("box"), 4)
        if name not in components or name in out or point is None or box is None:
            continue
        if not (box[0] < box[2] and box[1] < box[3]):
            continue
        if not (box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]):
            continue
        out[name] = Region(name, point, box)
    return list(out.values())


def propose(png, components, endpoint, deployment, token_provider=None):
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_version="2025-04-01-preview",
        azure_ad_token_provider=token_provider
        or get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        ),
        timeout=60,
    )
    url = "data:image/png;base64," + base64.b64encode(png).decode()
    reply = client.chat.completions.create(
        model=deployment,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Components: " + ", ".join(components)},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            },
        ],
    )
    return parse_regions(reply.choices[0].message.content, components)
