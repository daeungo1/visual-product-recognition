"""Deterministic reviewed product candidate resolution."""

import re

from pydantic import Field, model_validator

from visual_guide.issue_contracts import (
    ConfidenceBand,
    ProductCandidate,
    ProductStatus,
    StrictModel,
)
from visual_guide.registry import ProductManifest


class ProductResolution(StrictModel):
    """Bounded product resolution before issue planning."""

    status: ProductStatus
    candidates: tuple[ProductCandidate, ...] = Field(max_length=5)
    confirmed_product_id: str | None = None
    confirmed_model_code: str | None = None
    requires_confirmation: bool

    @model_validator(mode="after")
    def state_is_consistent(self) -> "ProductResolution":
        if self.status is ProductStatus.REGISTERED:
            if (
                len(self.candidates) != 1
                or not self.confirmed_product_id
                or not self.confirmed_model_code
                or self.requires_confirmation
            ):
                raise ValueError("registered product resolution must be exact")
        elif self.status is ProductStatus.CANDIDATE:
            if not self.candidates or not self.requires_confirmation:
                raise ValueError("candidate resolution requires confirmation")
            if self.confirmed_product_id or self.confirmed_model_code:
                raise ValueError("candidate resolution cannot be pre-confirmed")
        elif (
            self.candidates
            or self.confirmed_product_id
            or self.confirmed_model_code
            or self.requires_confirmation
        ):
            raise ValueError("unknown product resolution cannot contain candidates")
        return self


def _candidate(
    product: ProductManifest,
    *,
    band: ConfidenceBand,
    evidence: str,
) -> ProductCandidate:
    return ProductCandidate(
        product_id=product.product_id,
        manufacturer=product.manufacturer,
        display_name=product.display_name,
        exact_model_codes=product.exact_model_codes,
        evidence_source=evidence,
        confidence_band=band,
        confirmed_model_code=(
            product.exact_model_codes[0] if band is ConfidenceBand.HIGH else None
        ),
    )


def _try_exact(value: str | None, registry) -> ProductManifest | None:
    if not value:
        return None
    try:
        return registry.resolve_exact_model(value)
    except LookupError:
        return None


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]+", "", value.casefold())


def resolve_product(
    *,
    model_code: str | None,
    product_hint: str | None,
    visual_category: str | None,
    registry,
) -> ProductResolution:
    """Resolve exact, candidate or unknown product evidence deterministically."""
    exact = _try_exact(model_code, registry)
    hint_exact = _try_exact(product_hint, registry)
    if exact is not None and hint_exact is not None and exact.product_id != hint_exact.product_id:
        candidates = tuple(
            sorted(
                (
                    _candidate(
                        exact,
                        band=ConfidenceBand.HIGH,
                        evidence="model_code",
                    ),
                    _candidate(
                        hint_exact,
                        band=ConfidenceBand.HIGH,
                        evidence="product_hint_exact_model",
                    ),
                ),
                key=lambda item: item.product_id,
            )
        )
        return ProductResolution(
            status=ProductStatus.CANDIDATE,
            candidates=candidates,
            confirmed_product_id=None,
            confirmed_model_code=None,
            requires_confirmation=True,
        )
    if exact is not None:
        model = next(
            code
            for code in exact.exact_model_codes
            if _normalize(code) == _normalize(model_code or "")
        )
        candidate = _candidate(
            exact,
            band=ConfidenceBand.HIGH,
            evidence="model_code",
        ).model_copy(update={"confirmed_model_code": model})
        return ProductResolution(
            status=ProductStatus.REGISTERED,
            candidates=(candidate,),
            confirmed_product_id=exact.product_id,
            confirmed_model_code=model,
            requires_confirmation=False,
        )

    ranked: dict[str, ProductCandidate] = {}
    if product_hint:
        for product in registry.search_product_candidates(product_hint):
            ranked[product.product_id] = _candidate(
                product,
                band=ConfidenceBand.MEDIUM,
                evidence="product_hint",
            )
    if visual_category:
        for product in registry.search_product_candidates(visual_category):
            ranked.setdefault(
                product.product_id,
                _candidate(
                    product,
                    band=ConfidenceBand.LOW,
                    evidence="visual_category",
                ),
            )
    if ranked:
        return ProductResolution(
            status=ProductStatus.CANDIDATE,
            candidates=tuple(ranked[key] for key in sorted(ranked)),
            confirmed_product_id=None,
            confirmed_model_code=None,
            requires_confirmation=True,
        )
    return ProductResolution(
        status=ProductStatus.UNKNOWN,
        candidates=(),
        confirmed_product_id=None,
        confirmed_model_code=None,
        requires_confirmation=False,
    )
