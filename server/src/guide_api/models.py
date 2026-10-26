"""Validated demo contracts. Client OCR claims are not trusted server-side."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Identifier = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]
EventId = Annotated[str, Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Step(Contract):
    id: Identifier
    button_id: Identifier
    instruction: str
    expected_display: str


class Guide(Contract):
    id: Identifier
    target_id: Identifier
    title: str
    demo: Literal[True] = True
    steps: list[Step]


class Catalog(Contract):
    demo: Literal[True] = True
    real_product_assets_registered: Literal[False] = False
    guides: list[Guide]
    notice: str


class StartSession(Contract):
    guide_id: Identifier


class AdvanceEvent(Contract):
    event_id: EventId
    step_id: Identifier
    source: Literal["manual"]


class SessionState(Contract):
    id: str
    guide_id: Identifier
    step_index: int = Field(ge=0)
    current_step_id: str | None
    finished: bool
    demo: Literal[True] = True
    last_source: Literal["manual"] | None = None


class AiRequest(Contract):
    model_id: Identifier | None = None
