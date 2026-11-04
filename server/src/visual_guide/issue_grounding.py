"""Ground confirmed reviewed and zero-shot issue targets."""

from visual_guide.contracts import RegionStatus
from visual_guide.issue_contracts import (
    GroundedIssueTarget,
    IssueGroundingRequest,
    IssueGroundingResponse,
    ProductStatus,
    TargetSource,
)
from visual_guide.issue_service import ResolutionSigner
from visual_guide.orchestrator import PROVIDER_ERRORS, TargetGroundingContext
from visual_guide.registry import ComponentSpec


class IssueGroundingProviderError(RuntimeError):
    """Provider failure with completed hybrid target outcomes."""

    def __init__(
        self,
        *,
        failed_target_id: str,
        completed_targets: tuple[GroundedIssueTarget, ...],
    ):
        super().__init__(f"Issue grounding provider failed: {failed_target_id}")
        self.failed_target_id = failed_target_id
        self.completed_targets = completed_targets


class IssueGroundingService:
    """Revalidate product authority and ground confirmed dynamic targets."""

    def __init__(
        self,
        *,
        registry,
        manual_provider,
        target_grounder,
        signer: ResolutionSigner,
    ):
        self.registry = registry
        self.manual_provider = manual_provider
        self.target_grounder = target_grounder
        self.signer = signer

    def _resolve_registered(self, request: IssueGroundingRequest):
        try:
            product = self.registry.resolve_exact_model(
                request.confirmed_model_code
            )
        except LookupError as error:
            raise ValueError("Confirmed exact model is not registered.") from error
        if product.product_id != request.confirmed_product_id:
            raise ValueError("Confirmed product does not match the exact model.")
        if not request.confirmed_guide_id or not request.confirmed_step_id:
            raise ValueError("Reviewed targets require a confirmed guide and step.")
        guide = self.registry.guide(product.product_id, request.confirmed_guide_id)
        try:
            step = self.registry.eligible_step(
                product_id=product.product_id,
                issue_intent=request.resolution.issue_intent,
                current_state=request.resolution.normalized_state,
                guide_id=guide.guide_id,
                step_id=request.confirmed_step_id,
            )
        except LookupError as error:
            raise ValueError(
                "Confirmed step is not eligible for the issue state."
            ) from error
        manual = self.registry.manual_asset(product.product_id, step.source_manual_id)
        path = self.manual_provider.resolve(manual)
        resolved = self.registry.resolve_guide(
            model_code=request.confirmed_model_code,
            guide_id=guide.guide_id,
            manual_path=path,
        )
        return product, resolved.guide, step

    def ground(self, request: IssueGroundingRequest, image) -> IssueGroundingResponse:
        """Ground all confirmed targets while preserving target-level authority."""
        self.signer.verify(request.resolution)
        if request.resolution.product_status is ProductStatus.CANDIDATE:
            raise ValueError("Product confirmation is required before grounding.")
        product = guide = reviewed_step = None
        if request.resolution.product_status is ProductStatus.REGISTERED:
            product, guide, reviewed_step = self._resolve_registered(request)

        trusted_by_id = {
            target.target_id: target for target in request.resolution.targets
        }
        trusted_targets = []
        for submitted in request.confirmed_targets:
            original = trusted_by_id.get(submitted.target_id)
            if original is None:
                raise ValueError("Confirmed target was not part of the resolution.")
            trusted = original.model_copy(
                update={"display_name": submitted.display_name}
            )
            if submitted != trusted:
                raise ValueError("Confirmed target metadata was modified.")
            trusted_targets.append(trusted)

        results: list[GroundedIssueTarget] = []
        for target in trusted_targets:
            if target.source is TargetSource.REGISTRY:
                if product is None or reviewed_step is None:
                    raise ValueError("Registry target requires exact product confirmation.")
                component = self.registry.component_by_id(
                    product.product_id,
                    target.registry_component_id,
                )
                if component.component_id not in reviewed_step.target_ids:
                    raise ValueError("Registry target is not applicable to the confirmed step.")
                context = TargetGroundingContext(
                    step_id=reviewed_step.step_id,
                    instruction=reviewed_step.instruction,
                    source_evidence=reviewed_step.source_evidence,
                )
            else:
                component = ComponentSpec(
                    component_id=target.target_id,
                    canonical_name=target.canonical_name,
                    aliases=target.aliases,
                    relative_region=target.relative_region,
                )
                context = TargetGroundingContext(
                    step_id="zero-shot-target",
                    instruction=f"Locate only the user-requested {target.display_name}.",
                    source_evidence="No reviewed manual evidence.",
                )
            try:
                grounding = self.target_grounder.ground(
                    target_id=target.target_id,
                    component=component,
                    step=context,
                    image=image,
                )
            except PROVIDER_ERRORS as error:
                raise IssueGroundingProviderError(
                    failed_target_id=target.target_id,
                    completed_targets=tuple(results),
                ) from error
            results.append(
                GroundedIssueTarget(
                    target=target,
                    grounding=grounding,
                    instruction=(
                        reviewed_step.instruction
                        if target.source is TargetSource.REGISTRY
                        else None
                    ),
                    source_reference=(
                        f"{reviewed_step.source_manual_id}:page:"
                        f"{reviewed_step.source_page}"
                        if target.source is TargetSource.REGISTRY
                        else None
                    ),
                )
            )
        located = sum(
            item.grounding.status is RegionStatus.LOCATED for item in results
        )
        return IssueGroundingResponse(
            product_status=request.resolution.product_status,
            support_mode=request.resolution.support_mode,
            product_id=product.product_id if product else None,
            model_code=request.confirmed_model_code if product else None,
            guide_id=guide.guide_id if guide else None,
            step_id=reviewed_step.step_id if reviewed_step else None,
            image_width=image.width,
            image_height=image.height,
            targets=tuple(results),
            partial_success=0 < located < len(results),
        )
