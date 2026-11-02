"""Strict contracts for hybrid product issues and dynamic targets."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from visual_guide.contracts import GroundedTarget, RegionStatus


class ProductStatus(StrEnum):
    """How confidently the request maps to a reviewed product."""

    REGISTERED = "registered"
    CANDIDATE = "candidate"
    UNKNOWN = "unknown"


class SupportMode(StrEnum):
    """Maximum guidance level allowed for the current product evidence."""

    REVIEWED_GUIDE = "reviewed_guide"
    ZERO_SHOT_LOCATE_ONLY = "zero_shot_locate_only"


class ConfidenceBand(StrEnum):
    """Evidence band used for product candidates."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TargetSource(StrEnum):
    """Authority behind one dynamic target."""

    REGISTRY = "registry"
    USER_ISSUE = "user_issue"
    ZERO_SHOT = "zero_shot"


class StrictModel(BaseModel):
    """Immutable strict base model for public hybrid contracts."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        str_strip_whitespace=True,
    )


class IssueResolutionRequest(StrictModel):
    """User-authored product context and desired outcome."""

    product_hint: str | None = Field(default=None, max_length=256)
    model_code: str | None = Field(default=None, max_length=128)
    user_issue: str = Field(min_length=1, max_length=1000)
    current_state: str | None = Field(default=None, max_length=500)


class ProductCandidate(StrictModel):
    """One reviewed product candidate with bounded evidence strength."""

    product_id: str = Field(min_length=1, max_length=128)
    manufacturer: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=256)
    exact_model_codes: tuple[str, ...] = Field(min_length=1)
    evidence_source: str = Field(min_length=1, max_length=128)
    confidence_band: ConfidenceBand
    confirmed_model_code: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def confirmation_matches_band(self) -> "ProductCandidate":
        if self.confidence_band is ConfidenceBand.HIGH:
            if self.confirmed_model_code not in self.exact_model_codes:
                raise ValueError("high candidate requires a confirmed exact model code")
        elif self.confirmed_model_code is not None:
            raise ValueError("only high candidates can contain a confirmed model code")
        return self


class DynamicTargetSpec(StrictModel):
    """One request-scoped target proposed from registry or user evidence."""

    target_id: str = Field(min_length=1, max_length=128)
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
    source: TargetSource
    registry_component_id: str | None = Field(default=None, max_length=128)
    manual_evidence: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def authority_matches_source(self) -> "DynamicTargetSpec":
        if self.source is TargetSource.REGISTRY:
            if not self.registry_component_id or not self.manual_evidence:
                raise ValueError(
                    "registry target requires registry_component_id and manual_evidence"
                )
            return self
        if self.registry_component_id is not None or self.manual_evidence is not None:
            raise ValueError("non-registry target cannot claim registry evidence")
        return self


class GuideCandidate(StrictModel):
    """Non-actionable reviewed guide metadata returned during resolution."""

    guide_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    applicability: Literal["exact", "candidate"]
    source_references: tuple[str, ...] = Field(min_length=1)


class IssueResolution(StrictModel):
    """Product, intent and target proposal awaiting user confirmation."""

    product_status: ProductStatus
    support_mode: SupportMode
    product_candidates: tuple[ProductCandidate, ...] = Field(max_length=5)
    issue_intent: str = Field(min_length=1, max_length=128)
    targets: tuple[DynamicTargetSpec, ...] = Field(min_length=1, max_length=3)
    guide_candidates: tuple[GuideCandidate, ...] = Field(max_length=5)
    requires_product_confirmation: bool
    requires_target_confirmation: bool
    next_capture_instruction: str = Field(min_length=1, max_length=500)
    truncation_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def product_and_targets_are_consistent(self) -> "IssueResolution":
        canonical = [target.canonical_name.casefold() for target in self.targets]
        if len(set(canonical)) != len(canonical):
            raise ValueError("targets must have unique canonical names")
        if self.product_status is ProductStatus.REGISTERED:
            if self.support_mode is not SupportMode.REVIEWED_GUIDE:
                raise ValueError("registered product requires reviewed guide mode")
            if self.requires_product_confirmation:
                raise ValueError("registered exact product cannot require confirmation")
            high = [
                candidate
                for candidate in self.product_candidates
                if candidate.confidence_band is ConfidenceBand.HIGH
            ]
            if len(high) != 1:
                raise ValueError("registered product requires one high candidate")
        elif self.product_status is ProductStatus.CANDIDATE:
            if not self.product_candidates or not self.requires_product_confirmation:
                raise ValueError("candidate product requires confirmation")
            if self.support_mode is not SupportMode.ZERO_SHOT_LOCATE_ONLY:
                raise ValueError("candidate product cannot use reviewed guide mode")
        elif self.support_mode is not SupportMode.ZERO_SHOT_LOCATE_ONLY:
            raise ValueError("unknown product must use zero-shot locate-only mode")
        return self


class IssueGroundingRequest(StrictModel):
    """User-confirmed resolution and targets submitted for visual grounding."""

    resolution: IssueResolution
    confirmed_product_id: str | None = Field(default=None, max_length=128)
    confirmed_model_code: str | None = Field(default=None, max_length=128)
    confirmed_guide_id: str | None = Field(default=None, max_length=128)
    confirmed_step_id: str | None = Field(default=None, max_length=128)
    confirmed_targets: tuple[DynamicTargetSpec, ...] = Field(
        min_length=1,
        max_length=3,
    )

    @model_validator(mode="after")
    def exact_confirmation_is_present(self) -> "IssueGroundingRequest":
        if self.resolution.product_status is ProductStatus.REGISTERED and (
            not self.confirmed_product_id or not self.confirmed_model_code
        ):
            raise ValueError(
                "registered grounding requires confirmed_product_id and "
                "confirmed_model_code"
            )
        return self


class GroundedIssueTarget(StrictModel):
    """Grounding outcome and target-scoped guidance authority."""

    target: DynamicTargetSpec
    grounding: GroundedTarget
    instruction: str | None = Field(default=None, max_length=500)
    source_reference: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def instruction_matches_target_authority(self) -> "GroundedIssueTarget":
        if self.target.source is not TargetSource.REGISTRY and (
            self.instruction is not None or self.source_reference is not None
        ):
            raise ValueError("instruction requires a registry target")
        if self.instruction is not None and self.source_reference is None:
            raise ValueError("instruction requires a source_reference")
        return self


class IssueGroundingResponse(StrictModel):
    """Hybrid grounding results with target-level reviewed authority."""

    product_status: ProductStatus
    support_mode: SupportMode
    product_id: str | None = Field(default=None, max_length=128)
    model_code: str | None = Field(default=None, max_length=128)
    guide_id: str | None = Field(default=None, max_length=128)
    step_id: str | None = Field(default=None, max_length=128)
    image_width: int = Field(gt=0, le=8192)
    image_height: int = Field(gt=0, le=8192)
    targets: tuple[GroundedIssueTarget, ...] = Field(min_length=1, max_length=3)
    partial_success: bool

    @model_validator(mode="after")
    def result_authority_is_consistent(self) -> "IssueGroundingResponse":
        if self.support_mode is SupportMode.REVIEWED_GUIDE and (
            not self.product_id or not self.model_code
        ):
            raise ValueError("reviewed response requires exact product identity")
        located = sum(
            target.grounding.status is RegionStatus.LOCATED
            for target in self.targets
        )
        if self.partial_success is not (0 < located < len(self.targets)):
            raise ValueError("partial_success does not match target outcomes")
        return self
