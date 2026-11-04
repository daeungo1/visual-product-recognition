"""Registry-gated multi-target grounding with one bounded crop retry."""

from dataclasses import dataclass
from pathlib import Path

from openai import OpenAIError

from visual_guide.consensus import aggregate_regions
from visual_guide.contracts import (
    GroundedTarget,
    MultiTargetRegionRequest,
    MultiTargetRegionResponse,
    RegionProposal,
    RegionStatus,
)
from visual_guide.crops import crop_image, remap_proposal
from visual_guide.images import ImageInput
from visual_guide.model_gateway import RegionRequest

RETAKE_INSTRUCTIONS = {
    "upper_left": "제품 전면 상단 왼쪽을 화면에 크게 담아 다시 촬영하세요.",
    "upper_center": "제품 전면 상단 가운데를 정면에서 가까이 촬영하세요.",
    "upper_right": "제품 전면 상단 오른쪽을 화면에 크게 담아 다시 촬영하세요.",
    "lower_front": "제품 전면 하단 전체를 정면에서 가까이 촬영하세요.",
    "full_front": "제품 전면 전체가 잘리지 않도록 정면에서 다시 촬영하세요.",
}
PROVIDER_ERRORS = (OpenAIError, TimeoutError, ConnectionError)
VISUAL_PROPOSAL_ERRORS = (ValueError,)


class GroundingProviderError(RuntimeError):
    """Provider failure with completed independent target outcomes."""

    def __init__(
        self,
        *,
        failed_target_id: str,
        completed_targets: tuple[GroundedTarget, ...],
    ):
        super().__init__(f"Grounding provider failed for target: {failed_target_id}")
        self.failed_target_id = failed_target_id
        self.completed_targets = completed_targets


@dataclass(frozen=True)
class TargetGroundingContext:
    """Prompt context for one target without product authority."""

    step_id: str
    instruction: str
    source_evidence: str


class TargetGrounder:
    """Ground one reviewed or zero-shot component with bounded retries."""

    def __init__(self, gateway):
        self.gateway = gateway

    def _proposals(
        self,
        *,
        step,
        component,
        image: ImageInput,
        crop_retry: bool,
    ) -> list[RegionProposal]:
        aliases = ", ".join(component.aliases)
        scope = "This is an original-pixel reviewed crop." if crop_retry else "Use the full image."
        instruction = (
            f"{step.instruction}\n"
            f"Locate only {component.canonical_name}. "
            f"Aliases: {aliases}. Reviewed relative region: {component.relative_region}. "
            f"Manual evidence: {step.source_evidence} {scope}"
        )
        request = RegionRequest(
            step_id=step.step_id,
            component=component.canonical_name,
            instruction=instruction,
        )
        return [self.gateway.propose(request, image) for _ in range(3)]

    @staticmethod
    def _target(
        *,
        target_id: str,
        component,
        decision: RegionProposal,
        attempts: int,
    ) -> GroundedTarget:
        return GroundedTarget(
            target_id=target_id,
            component=component.canonical_name,
            status=decision.status,
            point=decision.point,
            box=decision.box,
            evidence=decision.evidence,
            attempts=attempts,
            retake_instruction=(
                None
                if decision.status is RegionStatus.LOCATED
                else RETAKE_INSTRUCTIONS[component.relative_region]
            ),
        )

    def ground(
        self,
        *,
        target_id: str,
        component,
        step,
        image: ImageInput,
    ) -> GroundedTarget:
        """Ground one target and convert provider failures to uncertainty."""
        try:
            decision = aggregate_regions(
                self._proposals(
                    step=step,
                    component=component,
                    image=image,
                    crop_retry=False,
                )
            )
        except VISUAL_PROPOSAL_ERRORS as error:
            decision = RegionProposal(
                status=RegionStatus.UNCERTAIN,
                step_id=step.step_id,
                component=component.canonical_name,
                image_width=image.width,
                image_height=image.height,
                point=None,
                box=None,
                evidence=f"Model proposal failed: {type(error).__name__}.",
            )
            return self._target(
                target_id=target_id,
                component=component,
                decision=decision,
                attempts=1,
            )
        attempts = 1
        if decision.status is RegionStatus.UNCERTAIN:
            cropped = crop_image(image, component)
            try:
                crop_decision = aggregate_regions(
                    self._proposals(
                        step=step,
                        component=component,
                        image=cropped.image,
                        crop_retry=True,
                    )
                )
                decision = remap_proposal(crop_decision, cropped)
            except VISUAL_PROPOSAL_ERRORS:
                pass
            attempts = 2
        return self._target(
            target_id=target_id,
            component=component,
            decision=decision,
            attempts=attempts,
        )


class GuideGroundingService:
    """Ground reviewed targets independently with bounded model calls."""

    def __init__(self, *, registry, gateway, manual_paths: dict[str, Path]):
        self.registry = registry
        self.target_grounder = TargetGrounder(gateway)
        self.manual_paths = {
            model_code.strip().upper(): path
            for model_code, path in manual_paths.items()
        }

    def ground(
        self,
        request: MultiTargetRegionRequest,
        image: ImageInput,
    ) -> MultiTargetRegionResponse:
        """Ground each reviewed target and preserve partial success."""
        model_code = request.model_code.strip().upper()
        manual_path = self.manual_paths.get(model_code)
        if manual_path is None:
            raise ValueError(f"No reviewed manual is configured for model: {model_code}")
        resolved = self.registry.resolve_guide(
            model_code=model_code,
            guide_id=request.guide_id,
            manual_path=manual_path,
        )
        step = next(
            (item for item in resolved.guide.steps if item.step_id == request.step_id),
            None,
        )
        if step is None:
            raise ValueError(f"Unknown reviewed step: {request.step_id}")
        allowed_targets = set(step.target_ids)
        unknown_targets = [
            target_id
            for target_id in request.target_ids
            if target_id not in allowed_targets or target_id not in resolved.components
        ]
        if unknown_targets:
            raise ValueError(f"Unknown target: {unknown_targets[0]}")

        grounded: list[GroundedTarget] = []
        for target_id in request.target_ids:
            component = resolved.components[target_id]
            try:
                target = self.target_grounder.ground(
                    target_id=target_id,
                    component=component,
                    step=TargetGroundingContext(
                        step_id=step.step_id,
                        instruction=step.instruction,
                        source_evidence=step.source_evidence,
                    ),
                    image=image,
                )
            except PROVIDER_ERRORS as error:
                raise GroundingProviderError(
                    failed_target_id=target_id,
                    completed_targets=tuple(grounded),
                ) from error
            grounded.append(target)
        located = sum(target.status is RegionStatus.LOCATED for target in grounded)
        return MultiTargetRegionResponse(
            product_id=resolved.product.product_id,
            guide_id=resolved.guide.guide_id,
            step_id=step.step_id,
            image_width=image.width,
            image_height=image.height,
            targets=tuple(grounded),
            partial_success=0 < located < len(grounded),
        )
