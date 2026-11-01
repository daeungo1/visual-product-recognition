"""Strict contracts shared by model adapters and API routes."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RegionStatus(StrEnum):
    """Region proposal outcome."""

    LOCATED = "located"
    NOT_VISIBLE = "not_visible"
    UNCERTAIN = "uncertain"


class PixelPoint(BaseModel):
    """Integer pixel coordinate in the sent image."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)


class PixelBox(BaseModel):
    """XYXY integer pixel box in the sent image."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x1: int = Field(ge=0)
    y1: int = Field(ge=0)
    x2: int = Field(gt=0)
    y2: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> "PixelBox":
        """Require positive box area."""
        if self.x1 >= self.x2 or self.y1 >= self.y2:
            raise ValueError("box coordinates must be ordered")
        return self


class RegionProposal(BaseModel):
    """One bounded proposal for the current guide step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RegionStatus
    step_id: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=128)
    image_width: int = Field(gt=0, le=8192)
    image_height: int = Field(gt=0, le=8192)
    point: PixelPoint | None
    box: PixelBox | None
    evidence: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def geometry_matches_status(self) -> "RegionProposal":
        """Accept geometry only for a valid located outcome."""
        if self.status is not RegionStatus.LOCATED:
            if self.point is not None or self.box is not None:
                raise ValueError("non-located proposals must not include geometry")
            return self
        if self.point is None or self.box is None:
            raise ValueError("located proposals require a point and box")
        if self.box.x2 > self.image_width or self.box.y2 > self.image_height:
            raise ValueError("box exceeds image bounds")
        if self.point.x >= self.image_width or self.point.y >= self.image_height:
            raise ValueError("point exceeds image bounds")
        if not (
            self.box.x1 <= self.point.x <= self.box.x2
            and self.box.y1 <= self.point.y <= self.box.y2
        ):
            raise ValueError("point must be inside box")
        return self
