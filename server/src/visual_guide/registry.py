"""Fail-closed reviewed product, manual and guide registry."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from visual_guide.manuals import pdf_sha256


class ManualReference(BaseModel):
    """One reviewed official manual revision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manual_id: str = Field(min_length=1, max_length=128)
    source_url: str = Field(pattern=r"^https://")
    sha256: str = Field(pattern=r"^[A-F0-9]{64}$")
    language: str = Field(min_length=2, max_length=16)
    revision: str = Field(min_length=1, max_length=32)
    applicable_models: tuple[str, ...] = Field(min_length=1)
    reviewed: bool

    @model_validator(mode="after")
    def require_review(self) -> "ManualReference":
        if not self.reviewed:
            raise ValueError("manual must be reviewed")
        return self


class ProductManifest(BaseModel):
    """Exact product identity and approved manuals."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product_id: str = Field(min_length=1, max_length=128)
    manufacturer: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=256)
    exact_model_codes: tuple[str, ...] = Field(min_length=1)
    reviewed: bool
    manuals: tuple[ManualReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_reviewed_exact_models(self) -> "ProductManifest":
        if not self.reviewed:
            raise ValueError("product must be reviewed")
        exact_models = set(self.exact_model_codes)
        for manual in self.manuals:
            if not set(manual.applicable_models).issubset(exact_models):
                raise ValueError("manual applicability exceeds exact product models")
        return self


class ComponentSpec(BaseModel):
    """Reviewed visual identity for one component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    component_id: str = Field(min_length=1, max_length=128)
    canonical_name: str = Field(min_length=1, max_length=128)
    aliases: tuple[str, ...] = Field(min_length=1)
    relative_region: Literal[
        "upper_left",
        "upper_center",
        "upper_right",
        "lower_front",
        "full_front",
    ]


class GuideStep(BaseModel):
    """One source-cited reviewed guide step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step_id: str = Field(min_length=1, max_length=128)
    required_state: str = Field(min_length=1, max_length=128)
    target_ids: tuple[str, ...] = Field(min_length=1)
    instruction: str = Field(min_length=1, max_length=500)
    expected_state: str = Field(min_length=1, max_length=128)
    verification: str = Field(min_length=1, max_length=128)
    source_manual_id: str = Field(min_length=1, max_length=128)
    source_page: int = Field(gt=0)
    source_evidence: str = Field(min_length=1, max_length=500)


class ReviewedGuide(BaseModel):
    """Reviewed ordered procedure for exact products."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    guide_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    exact_model_codes: tuple[str, ...] = Field(min_length=1)
    reviewed: bool
    steps: tuple[GuideStep, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_review(self) -> "ReviewedGuide":
        if not self.reviewed:
            raise ValueError("guide must be reviewed")
        return self


@dataclass(frozen=True)
class ResolvedGuide:
    """Applicable reviewed product, manual and guide."""

    product: ProductManifest
    manual: ManualReference
    guide: ReviewedGuide
    components: dict[str, ComponentSpec]


class ReviewedRegistry:
    """Resolve exact models to reviewed guides without fuzzy fallbacks."""

    def __init__(
        self,
        products: dict[str, ProductManifest],
        components: dict[str, dict[str, ComponentSpec]],
        guides: dict[tuple[str, str], ReviewedGuide],
    ):
        self._products = products
        self._components = components
        self._guides = guides

    def resolve_guide(
        self,
        *,
        model_code: str,
        guide_id: str,
        manual_path: Path,
    ) -> ResolvedGuide:
        normalized = model_code.strip().upper()
        matches = [
            product
            for product in self._products.values()
            if normalized in product.exact_model_codes
        ]
        if len(matches) != 1:
            raise LookupError(f"Exact model is not supported: {model_code}")
        product = matches[0]
        guide = self._guides.get((product.product_id, guide_id))
        if guide is None or normalized not in guide.exact_model_codes:
            raise LookupError(f"Guide is not applicable to model: {model_code}")
        manual_ids = {step.source_manual_id for step in guide.steps}
        if len(manual_ids) != 1:
            raise ValueError("A resolved guide must cite exactly one reviewed manual.")
        manual = next(
            (item for item in product.manuals if item.manual_id in manual_ids),
            None,
        )
        if manual is None or normalized not in manual.applicable_models:
            raise ValueError("Guide manual is not applicable to the exact model.")
        if pdf_sha256(manual_path) != manual.sha256:
            raise ValueError("Manual hash does not match the reviewed source.")
        return ResolvedGuide(
            product=product,
            manual=manual,
            guide=guide,
            components=self._components[product.product_id],
        )


def load_reviewed_registry(root: Path) -> ReviewedRegistry:
    """Load reviewed product folders and validate all cross-references."""
    products: dict[str, ProductManifest] = {}
    components: dict[str, dict[str, ComponentSpec]] = {}
    guides: dict[tuple[str, str], ReviewedGuide] = {}
    for manifest_path in sorted(root.glob("*/*/manifest.json")):
        product_dir = manifest_path.parent
        product = ProductManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        if product.product_id in products:
            raise ValueError(f"Duplicate product ID: {product.product_id}")
        component_items = [
            ComponentSpec.model_validate(item)
            for item in json.loads(
                (product_dir / "components.json").read_text(encoding="utf-8")
            )
        ]
        component_map = {item.component_id: item for item in component_items}
        if len(component_map) != len(component_items):
            raise ValueError(f"Duplicate component in product: {product.product_id}")
        for guide_path in sorted((product_dir / "guides").glob("*.json")):
            guide = ReviewedGuide.model_validate_json(
                guide_path.read_text(encoding="utf-8")
            )
            if not set(guide.exact_model_codes).issubset(product.exact_model_codes):
                raise ValueError("Guide model is outside the reviewed product.")
            manual_ids = {manual.manual_id for manual in product.manuals}
            for step in guide.steps:
                if step.source_manual_id not in manual_ids:
                    raise ValueError("Guide references an unknown manual.")
                for target_id in step.target_ids:
                    if target_id not in component_map:
                        raise ValueError(f"Guide references unknown component: {target_id}")
            key = (product.product_id, guide.guide_id)
            if key in guides:
                raise ValueError(f"Duplicate guide ID: {guide.guide_id}")
            guides[key] = guide
        products[product.product_id] = product
        components[product.product_id] = component_map
    if not products:
        raise ValueError("No reviewed products found.")
    return ReviewedRegistry(products=products, components=components, guides=guides)
