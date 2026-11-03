"""Compose untrusted issue plans with deterministic registry authority."""

from visual_guide.issue_contracts import (
    DynamicTargetSpec,
    GuideCandidate,
    IssueResolution,
    IssueResolutionRequest,
    ProductStatus,
    SupportMode,
    TargetSource,
)
from visual_guide.product_resolver import ProductResolution, resolve_product


class IssueResolutionService:
    """Resolve products, intents and targets before visual grounding."""

    def __init__(self, *, planner, registry):
        self.planner = planner
        self.registry = registry

    def _map_target(
        self,
        planned,
        *,
        product_resolution: ProductResolution,
        target_index: int,
    ) -> DynamicTargetSpec:
        if product_resolution.status is ProductStatus.REGISTERED:
            product_id = product_resolution.confirmed_product_id
            phrases = (
                planned.display_name,
                planned.canonical_name,
                *planned.aliases,
            )
            component = next(
                (
                    matched
                    for phrase in phrases
                    if (
                        matched := self.registry.resolve_component_alias(
                            product_id,
                            phrase,
                        )
                    )
                    is not None
                ),
                None,
            )
            if component is not None:
                return DynamicTargetSpec(
                    target_id=component.component_id,
                    display_name=planned.display_name,
                    canonical_name=component.canonical_name,
                    aliases=component.aliases,
                    purpose=planned.purpose,
                    relative_region=component.relative_region,
                    source=TargetSource.REGISTRY,
                    registry_component_id=component.component_id,
                    manual_evidence=self.registry.component_evidence(
                        product_id,
                        component.component_id,
                    ),
                )
        return DynamicTargetSpec(
            target_id=f"user-target-{target_index + 1}",
            display_name=planned.display_name,
            canonical_name=planned.canonical_name,
            aliases=planned.aliases,
            purpose=planned.purpose,
            relative_region=planned.relative_region,
            source=TargetSource.ZERO_SHOT,
            registry_component_id=None,
            manual_evidence=None,
        )

    @staticmethod
    def _guide_candidate(guide) -> GuideCandidate:
        references = tuple(
            f"{step.source_manual_id}:page:{step.source_page}"
            for step in guide.steps
        )
        return GuideCandidate(
            guide_id=guide.guide_id,
            title=guide.title,
            applicability="exact",
            step_ids=tuple(step.step_id for step in guide.steps),
            source_references=references,
        )

    def resolve(self, request: IssueResolutionRequest, image) -> IssueResolution:
        """Resolve a free-form user issue into confirmed candidate data."""
        planned = self.planner.plan(
            request,
            self.registry.product_summaries(),
            image,
        )
        product = resolve_product(
            model_code=request.model_code,
            product_hint=request.product_hint,
            visual_category=planned.visual_category,
            registry=self.registry,
        )
        targets = tuple(
            self._map_target(
                target,
                product_resolution=product,
                target_index=index,
            )
            for index, target in enumerate(planned.targets)
        )
        guides = ()
        if product.status is ProductStatus.REGISTERED:
            reviewed = self.registry.find_guide_candidates(
                product_id=product.confirmed_product_id,
                issue_intent=planned.issue_intent,
                current_state=planned.normalized_state,
            )
            guides = tuple(self._guide_candidate(guide) for guide in reviewed)
        if product.status is ProductStatus.REGISTERED and guides:
            next_capture = "확인한 대상이 보이도록 제품 전면을 촬영하세요."
        elif product.status is ProductStatus.REGISTERED:
            next_capture = "현재 제품 상태를 더 구체적으로 입력하거나 촬영하세요."
        elif product.status is ProductStatus.CANDIDATE:
            next_capture = "정확한 제품 모델을 선택한 뒤 대상을 확인하세요."
        else:
            next_capture = "제품 모델 라벨을 촬영하거나 공식 설명서를 제공하세요."
        return IssueResolution(
            product_status=product.status,
            support_mode=(
                SupportMode.REVIEWED_GUIDE
                if product.status is ProductStatus.REGISTERED
                else SupportMode.ZERO_SHOT_LOCATE_ONLY
            ),
            product_candidates=product.candidates,
            issue_intent=planned.issue_intent,
            targets=targets,
            guide_candidates=guides,
            requires_product_confirmation=product.requires_confirmation,
            requires_target_confirmation=True,
            next_capture_instruction=next_capture,
            truncation_reason=planned.truncation_reason,
        )

    def confirm_targets(
        self,
        resolution: IssueResolution,
        *,
        display_renames: dict[str, str],
        added_target_phrases: tuple[str, ...] = (),
        original_request: IssueResolutionRequest | None = None,
        image=None,
    ) -> tuple[DynamicTargetSpec, ...]:
        """Apply display-only renames and replan any added user targets."""
        target_ids = {target.target_id for target in resolution.targets}
        unknown_renames = set(display_renames) - target_ids
        if unknown_renames:
            raise ValueError(f"Unknown target rename: {sorted(unknown_renames)[0]}")
        confirmed = [
            target.model_copy(
                update={
                    "display_name": display_renames.get(
                        target.target_id,
                        target.display_name,
                    )
                }
            )
            for target in resolution.targets
        ]
        if added_target_phrases and original_request is None:
            raise ValueError("Added targets require the original issue request.")
        product_resolution = ProductResolution(
            status=resolution.product_status,
            candidates=resolution.product_candidates,
            confirmed_product_id=(
                resolution.product_candidates[0].product_id
                if resolution.product_status is ProductStatus.REGISTERED
                else None
            ),
            confirmed_model_code=(
                resolution.product_candidates[0].confirmed_model_code
                if resolution.product_status is ProductStatus.REGISTERED
                else None
            ),
            requires_confirmation=resolution.requires_product_confirmation,
        )
        for phrase in added_target_phrases:
            request = original_request.model_copy(update={"user_issue": phrase})
            planned = self.planner.plan(
                request,
                self.registry.product_summaries(),
                image,
            )
            for target in planned.targets:
                mapped = self._map_target(
                    target,
                    product_resolution=product_resolution,
                    target_index=len(confirmed),
                )
                if mapped.canonical_name.casefold() not in {
                    item.canonical_name.casefold() for item in confirmed
                }:
                    confirmed.append(mapped)
                if len(confirmed) == 3:
                    break
            if len(confirmed) == 3:
                break
        return tuple(confirmed)
