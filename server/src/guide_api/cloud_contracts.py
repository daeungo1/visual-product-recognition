"""Versioned HTTP contracts; local demo contracts deliberately remain unchanged."""

from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from guide_api.models import Contract, EventId, Identifier, Step

Category = Literal["aircon", "tv", "airdresser"]
TargetKind = Literal["body", "remote", "screen"]


class CloudGuide(Contract):
    id: Identifier
    target_id: Identifier
    title: str = Field(min_length=1, max_length=500)
    demo: bool
    steps: list[Step] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_steps(self):
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Step IDs must be unique.")
        return self


class PairRequest(Contract):
    code: str = Field(min_length=8, max_length=256)


class ImageRequest(Contract):
    image_base64: str = Field(min_length=1)


class IdentifyRequest(ImageRequest):
    category: Category
    target_kind: TargetKind
    ocr_text: str = Field(default="", max_length=4000)


class VerifyRequest(ImageRequest):
    step_id: Identifier


class CloudEvent(Contract):
    event_id: EventId
    step_id: Identifier
    source: Literal["manual", "ocr", "vlm"]
    observed_text: str | None = Field(default=None, max_length=4000)
    verification_id: str | None = Field(default=None, min_length=16, max_length=128)

    @model_validator(mode="after")
    def source_evidence(self):
        if self.source == "manual" and (self.observed_text or self.verification_id):
            raise ValueError("Manual completion cannot claim automatic evidence.")
        if self.source == "ocr" and (not self.observed_text or self.verification_id):
            raise ValueError("OCR requires only observed_text.")
        if self.source == "vlm" and (not self.verification_id or self.observed_text):
            raise ValueError("VLM requires only verification_id.")
        return self


class DraftRequest(Contract):
    source_url: HttpUrl
    source_text: str = Field(min_length=1, max_length=20000)
    model: str = Field(min_length=1, max_length=200)
