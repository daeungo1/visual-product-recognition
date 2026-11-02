"""Microsoft Foundry vision adapter with strict pixel-space output."""

import base64
import os

from pydantic import BaseModel, ConfigDict, Field

from visual_guide.contracts import RegionProposal
from visual_guide.images import ImageInput

SYSTEM_PROMPT = """\
You locate exactly one named component for the current reviewed guide step.
Use only visible image evidence. Return not_visible when the component is not
currently visible and uncertain when multiple candidates remain. Never infer a
hidden component. For located results, return integer absolute XYXY coordinates
and an integer point in the exact sent-image pixel coordinate system.
"""


class RegionRequest(BaseModel):
    """Current reviewed step passed to the vision model."""

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=128)
    instruction: str = Field(min_length=1, max_length=500)


class FoundryRegionGateway:
    """Call an injected OpenAI-compatible client for one snapshot."""

    def __init__(self, *, client, deployment: str):
        self.client = client
        self.deployment = deployment

    def ready(self) -> bool:
        """Report that the adapter is configured for request-time checks."""
        return True

    def propose(self, request: RegionRequest, image: ImageInput) -> RegionProposal:
        """Return a validated structured proposal without fallback geometry."""
        encoded = base64.b64encode(image.data).decode()
        response = self.client.chat.completions.create(
            model=self.deployment,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "region_proposal",
                    "strict": True,
                    "schema": RegionProposal.model_json_schema(),
                },
            },
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Sent image size: {image.width} x {image.height} pixels.\n"
                                f"Step ID: {request.step_id}\n"
                                f"Component: {request.component}\n"
                                f"Reviewed instruction: {request.instruction}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image.mime};base64,{encoded}",
                                "detail": "original",
                            },
                        },
                    ],
                },
            ],
        )
        content = response.choices[0].message.content
        proposal = RegionProposal.model_validate_json(content)
        if proposal.step_id != request.step_id or proposal.component != request.component:
            raise ValueError("Model response scope does not match the request.")
        if proposal.image_width != image.width or proposal.image_height != image.height:
            raise ValueError("Model response dimensions do not match the sent image.")
        return proposal


def build_foundry_gateway(
    endpoint: str,
    deployment: str,
    *,
    azure_ad_token: str | None = None,
) -> FoundryRegionGateway:
    """Build an Entra-authenticated Azure OpenAI adapter."""
    from openai import AzureOpenAI

    azure_ad_token = azure_ad_token or os.getenv("FOUNDRY_AZURE_AD_TOKEN")
    authentication = {}
    if azure_ad_token is not None:
        authentication["azure_ad_token"] = azure_ad_token
    else:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        authentication["azure_ad_token_provider"] = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_version="2025-04-01-preview",
        timeout=90,
        max_retries=1,
        **authentication,
    )
    return FoundryRegionGateway(client=client, deployment=deployment)
