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


class MultiTargetRegionRequest(BaseModel):
    """Exact reviewed guide scope with independent canonical targets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_code: str = Field(min_length=1, max_length=128)
    guide_id: str = Field(min_length=1, max_length=128)
    step_id: str = Field(min_length=1, max_length=128)
    target_ids: tuple[str, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_targets(self) -> "MultiTargetRegionRequest":
        if len(set(self.target_ids)) != len(self.target_ids):
            raise ValueError("target_ids must be unique")
        return self


class GroundedTarget(BaseModel):
    """One independent target outcome in root-image coordinates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_id: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=128)
    status: RegionStatus
    point: PixelPoint | None
    box: PixelBox | None
    evidence: str = Field(min_length=1, max_length=500)
    attempts: int = Field(ge=1, le=2)
    retake_instruction: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def geometry_and_retake_match_status(self) -> "GroundedTarget":
        if self.status is RegionStatus.LOCATED:
            if self.point is None or self.box is None:
                raise ValueError("located target requires point and box")
            if not (
                self.box.x1 <= self.point.x <= self.box.x2
                and self.box.y1 <= self.point.y <= self.box.y2
            ):
                raise ValueError("target point must be inside box")
            if self.retake_instruction is not None:
                raise ValueError("located target cannot request a retake")
            return self
        if self.point is not None or self.box is not None:
            raise ValueError("non-located target cannot include geometry")
        if not self.retake_instruction:
            raise ValueError("non-located target requires retake_instruction")
        return self


class MultiTargetRegionResponse(BaseModel):
    """Independent results for all requested reviewed targets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product_id: str = Field(min_length=1, max_length=128)
    guide_id: str = Field(min_length=1, max_length=128)
    step_id: str = Field(min_length=1, max_length=128)
    image_width: int = Field(gt=0, le=8192)
    image_height: int = Field(gt=0, le=8192)
    targets: tuple[GroundedTarget, ...] = Field(min_length=1, max_length=8)
    partial_success: bool

    @model_validator(mode="after")
    def validate_target_set(self) -> "MultiTargetRegionResponse":
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("response target IDs must be unique")
        for target in self.targets:
            if target.box is not None and (
                target.box.x2 > self.image_width or target.box.y2 > self.image_height
            ):
                raise ValueError("target box exceeds image bounds")
            if target.point is not None and (
                target.point.x >= self.image_width or target.point.y >= self.image_height
            ):
                raise ValueError("target point exceeds image bounds")
        located = sum(target.status is RegionStatus.LOCATED for target in self.targets)
        expected_partial = 0 < located < len(self.targets)
        if self.partial_success is not expected_partial:
            raise ValueError("partial_success does not match target outcomes")
        return self
