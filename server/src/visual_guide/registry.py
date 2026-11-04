"""Fail-closed reviewed product, manual and guide registry."""

import json
import re
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
    asset_name: str = Field(min_length=1, max_length=256)
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
    product_family: str = Field(min_length=1, max_length=128)
    aliases: tuple[str, ...] = Field(min_length=1)
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


class IssueMapping(BaseModel):
    """Reviewed mapping from user intent and state to guide candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_intent: str = Field(min_length=1, max_length=128)
    aliases: tuple[str, ...] = Field(min_length=1)
    required_states: tuple[str, ...] = Field(min_length=1)
    guide_id: str = Field(min_length=1, max_length=128)
    eligible_step_ids: tuple[str, ...] = Field(min_length=1)
    required_component_ids: tuple[str, ...] = Field(min_length=1)
    optional_component_ids: tuple[str, ...] = ()


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
        issue_mappings: dict[str, tuple[IssueMapping, ...]],
    ):
        self._products = products
        self._components = components
        self._guides = guides
        self._issue_mappings = issue_mappings

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\w]+", "", value.casefold())

    def resolve_exact_model(self, model_code: str) -> ProductManifest:
        """Resolve one exact normalized model without fuzzy fallback."""
        normalized = self._normalize(model_code)
        matches = [
            product
            for product in self._products.values()
            if normalized
            in {self._normalize(code) for code in product.exact_model_codes}
        ]
        if len(matches) != 1:
            raise LookupError(f"Exact model is not supported: {model_code}")
        return matches[0]

    def search_product_candidates(
        self,
        product_hint: str,
    ) -> tuple[ProductManifest, ...]:
        """Search reviewed product names, families and aliases."""
        normalized = self._normalize(product_hint)
        if not normalized:
            return ()
        matches = []
        for product in self._products.values():
            values = (
                product.manufacturer,
                product.display_name,
                product.product_family,
                *product.aliases,
            )
            if any(
                normalized in self._normalize(value)
                or self._normalize(value) in normalized
                for value in values
            ):
                matches.append(product)
        return tuple(sorted(matches, key=lambda item: item.product_id))

    def resolve_component_alias(
        self,
        product_id: str,
        user_target: str,
    ) -> ComponentSpec | None:
        """Resolve an alias only inside the selected reviewed product."""
        component_map = self._components.get(product_id)
        if component_map is None:
            raise LookupError(f"Unknown product: {product_id}")
        normalized = self._normalize(user_target)
        for component in component_map.values():
            values = (component.canonical_name, *component.aliases)
            if normalized in {self._normalize(value) for value in values}:
                return component
        return None

    def find_guide_candidates(
        self,
        *,
        product_id: str,
        issue_intent: str,
        current_state: str | None,
    ) -> tuple[ReviewedGuide, ...]:
        """Return only guides whose reviewed intent and state mapping matches."""
        if product_id not in self._products:
            raise LookupError(f"Unknown product: {product_id}")
        normalized_intent = self._normalize(issue_intent)
        normalized_state = self._normalize(current_state or "")
        guide_ids = []
        for mapping in self._issue_mappings.get(product_id, ()):
            intents = (mapping.issue_intent, *mapping.aliases)
            if normalized_intent not in {self._normalize(value) for value in intents}:
                continue
            states = {self._normalize(value) for value in mapping.required_states}
            if not normalized_state or normalized_state not in states:
                continue
            guide_ids.append(mapping.guide_id)
        return tuple(
            self._guides[(product_id, guide_id)]
            for guide_id in guide_ids
            if (product_id, guide_id) in self._guides
        )

    def eligible_step_ids(
        self,
        *,
        product_id: str,
        issue_intent: str,
        current_state: str | None,
        guide_id: str,
    ) -> tuple[str, ...]:
        """Return state-gated step IDs from the reviewed issue mapping."""
        normalized_intent = self._normalize(issue_intent)
        normalized_state = self._normalize(current_state or "")
        for mapping in self._issue_mappings.get(product_id, ()):
            intents = (mapping.issue_intent, *mapping.aliases)
            if normalized_intent not in {self._normalize(value) for value in intents}:
                continue
            if normalized_state not in {
                self._normalize(value) for value in mapping.required_states
            }:
                continue
            if mapping.guide_id == guide_id:
                return mapping.eligible_step_ids
        return ()

    def eligible_step(
        self,
        *,
        product_id: str,
        issue_intent: str,
        current_state: str | None,
        guide_id: str,
        step_id: str,
    ) -> GuideStep:
        """Return one step only when the reviewed issue-state mapping permits it."""
        eligible = self.eligible_step_ids(
            product_id=product_id,
            issue_intent=issue_intent,
            current_state=current_state,
            guide_id=guide_id,
        )
        if step_id not in eligible:
            raise LookupError("Step is not eligible for the confirmed issue state.")
        guide = self.guide(product_id, guide_id)
        step = next(item for item in guide.steps if item.step_id == step_id)
        if self._normalize(step.required_state) != self._normalize(current_state or ""):
            raise LookupError("Step required state does not match the confirmed state.")
        return step

    def manual_asset(
        self,
        product_id: str,
        manual_id: str,
    ) -> ManualReference:
        """Return reviewed manual metadata for a selected product."""
        product = self._products.get(product_id)
        if product is None:
            raise LookupError(f"Unknown product: {product_id}")
        manual = next(
            (item for item in product.manuals if item.manual_id == manual_id),
            None,
        )
        if manual is None:
            raise LookupError(f"Unknown manual: {manual_id}")
        return manual

    def guide(self, product_id: str, guide_id: str) -> ReviewedGuide:
        """Return one reviewed guide by stable product and guide IDs."""
        guide = self._guides.get((product_id, guide_id))
        if guide is None:
            raise LookupError(f"Unknown guide: {guide_id}")
        return guide

    def component_by_id(
        self,
        product_id: str,
        component_id: str,
    ) -> ComponentSpec:
        """Return one reviewed component inside a selected product."""
        component = self._components.get(product_id, {}).get(component_id)
        if component is None:
            raise LookupError(f"Unknown component: {component_id}")
        return component

    def product_summaries(self) -> tuple[dict, ...]:
        """Return bounded reviewed metadata for issue planning."""
        return tuple(
            {
                "product_id": product.product_id,
                "manufacturer": product.manufacturer,
                "display_name": product.display_name,
                "product_family": product.product_family,
                "aliases": product.aliases,
                "exact_model_codes": product.exact_model_codes,
                "issue_mappings": tuple(
                    {
                        "issue_intent": mapping.issue_intent,
                        "aliases": mapping.aliases,
                        "required_states": mapping.required_states,
                    }
                    for mapping in self._issue_mappings.get(product.product_id, ())
                ),
                "components": tuple(
                    {
                        "component_id": component.component_id,
                        "canonical_name": component.canonical_name,
                        "aliases": component.aliases,
                        "relative_region": component.relative_region,
                    }
                    for component in sorted(
                        self._components[product.product_id].values(),
                        key=lambda item: item.component_id,
                    )
                ),
            }
            for product in sorted(
                self._products.values(),
                key=lambda item: item.product_id,
            )
        )

    def model_manual_paths(self, provider) -> dict[str, Path]:
        """Build exact-model manual paths for the legacy reviewed route."""
        paths: dict[str, Path] = {}
        for product in self._products.values():
            for manual in product.manuals:
                path = provider.resolve(manual)
                for model_code in manual.applicable_models:
                    existing = paths.get(model_code)
                    if existing is not None and existing != path:
                        raise ValueError(
                            f"Multiple reviewed manuals apply to legacy model: {model_code}"
                        )
                    paths[model_code] = path
        return paths

    def component_evidence(
        self,
        product_id: str,
        component_id: str,
    ) -> str:
        """Return one reviewed source citation for a product component."""
        if component_id not in self._components.get(product_id, {}):
            raise LookupError(f"Unknown component: {component_id}")
        for (guide_product_id, _), guide in sorted(self._guides.items()):
            if guide_product_id != product_id:
                continue
            for step in guide.steps:
                if component_id in step.target_ids:
                    return (
                        f"{step.source_manual_id}:page:{step.source_page}:"
                        f"{step.source_evidence}"
                    )
        raise LookupError(f"No reviewed evidence for component: {component_id}")

    def resolve_guide(
        self,
        *,
        model_code: str,
        guide_id: str,
        manual_path: Path,
    ) -> ResolvedGuide:
        normalized = model_code.strip().upper()
        product = self.resolve_exact_model(model_code)
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
    issue_mappings: dict[str, tuple[IssueMapping, ...]] = {}
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
        issues_path = product_dir / "issues.json"
        mappings = (
            tuple(
                IssueMapping.model_validate(item)
                for item in json.loads(issues_path.read_text(encoding="utf-8"))
            )
            if issues_path.is_file()
            else ()
        )
        for mapping in mappings:
            guide = guides.get((product.product_id, mapping.guide_id))
            if guide is None:
                raise ValueError("Issue mapping references an unknown guide.")
            step_ids = {step.step_id for step in guide.steps}
            if not set(mapping.eligible_step_ids).issubset(step_ids):
                raise ValueError("Issue mapping references an unknown guide step.")
            eligible_steps = [
                step
                for step in guide.steps
                if step.step_id in mapping.eligible_step_ids
            ]
            allowed_states = {
                self_state.casefold()
                for self_state in mapping.required_states
            }
            if any(
                step.required_state.casefold() not in allowed_states
                for step in eligible_steps
            ):
                raise ValueError(
                    "Issue mapping includes a step with an ineligible required state."
                )
            component_ids = set(component_map)
            mapped_components = set(mapping.required_component_ids) | set(
                mapping.optional_component_ids
            )
            if not mapped_components.issubset(component_ids):
                raise ValueError("Issue mapping references an unknown component.")
        products[product.product_id] = product
        components[product.product_id] = component_map
        issue_mappings[product.product_id] = mappings
    if not products:
        raise ValueError("No reviewed products found.")
    return ReviewedRegistry(
        products=products,
        components=components,
        guides=guides,
        issue_mappings=issue_mappings,
    )
