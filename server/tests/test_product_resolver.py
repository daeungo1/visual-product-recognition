from visual_guide.issue_contracts import ConfidenceBand, ProductStatus
from visual_guide.product_resolver import resolve_product
from visual_guide.registry import ManualReference, ProductManifest


def _product(product_id: str, model: str, alias: str) -> ProductManifest:
    return ProductManifest(
        product_id=product_id,
        manufacturer="Samsung",
        display_name=alias,
        product_family="washer",
        aliases=(alias,),
        exact_model_codes=(model,),
        reviewed=True,
        manuals=(
            ManualReference(
                manual_id=f"{product_id}-manual",
                source_url="https://example.test/manual.pdf",
                sha256="A" * 64,
                language="en",
                revision="1",
                asset_name="manual.pdf",
                applicable_models=(model,),
                reviewed=True,
            ),
        ),
    )


class FakeRegistry:
    def __init__(self):
        self.first = _product("product-a", "MODEL-A", "Alpha Washer")
        self.second = _product("product-b", "MODEL-B", "Beta Washer")

    def resolve_exact_model(self, model_code):
        normalized = model_code.strip().upper()
        for product in (self.first, self.second):
            if normalized in product.exact_model_codes:
                return product
        raise LookupError(model_code)

    def search_product_candidates(self, hint):
        normalized = hint.casefold()
        if "alpha" in normalized:
            return (self.first,)
        if "beta" in normalized:
            return (self.second,)
        if "washer" in normalized:
            return (self.second, self.first)
        return ()


def test_exact_model_resolves_registered_high_candidate():
    result = resolve_product(
        model_code=" model-a ",
        product_hint=None,
        visual_category=None,
        registry=FakeRegistry(),
    )

    assert result.status is ProductStatus.REGISTERED
    assert result.candidates[0].confidence_band is ConfidenceBand.HIGH
    assert result.confirmed_product_id == "product-a"
    assert result.confirmed_model_code == "MODEL-A"
    assert result.requires_confirmation is False


def test_conflicting_exact_model_evidence_requires_confirmation():
    result = resolve_product(
        model_code="MODEL-A",
        product_hint="MODEL-B",
        visual_category=None,
        registry=FakeRegistry(),
    )

    assert result.status is ProductStatus.CANDIDATE
    assert {candidate.product_id for candidate in result.candidates} == {
        "product-a",
        "product-b",
    }
    assert result.requires_confirmation is True


def test_medium_candidates_are_ordered_deterministically():
    result = resolve_product(
        model_code=None,
        product_hint="washer",
        visual_category=None,
        registry=FakeRegistry(),
    )

    assert result.status is ProductStatus.CANDIDATE
    assert [candidate.product_id for candidate in result.candidates] == [
        "product-a",
        "product-b",
    ]
    assert all(
        candidate.confidence_band is ConfidenceBand.MEDIUM
        for candidate in result.candidates
    )


def test_visual_category_candidates_remain_low_confidence():
    result = resolve_product(
        model_code=None,
        product_hint=None,
        visual_category="washer",
        registry=FakeRegistry(),
    )

    assert result.status is ProductStatus.CANDIDATE
    assert all(
        candidate.confidence_band is ConfidenceBand.LOW
        for candidate in result.candidates
    )
    assert result.requires_confirmation is True


def test_no_product_evidence_remains_unknown():
    result = resolve_product(
        model_code=None,
        product_hint="unlisted appliance",
        visual_category=None,
        registry=FakeRegistry(),
    )

    assert result.status is ProductStatus.UNKNOWN
    assert result.candidates == ()
    assert result.confirmed_product_id is None


def test_exact_model_outranks_nonconflicting_wrong_hint():
    result = resolve_product(
        model_code="MODEL-A",
        product_hint="unknown marketing phrase",
        visual_category="washer",
        registry=FakeRegistry(),
    )

    assert result.status is ProductStatus.REGISTERED
    assert result.confirmed_product_id == "product-a"


def test_unknown_model_with_hint_requires_candidate_confirmation():
    result = resolve_product(
        model_code="UNKNOWN-1",
        product_hint="Alpha Washer",
        visual_category=None,
        registry=FakeRegistry(),
    )

    assert result.status is ProductStatus.CANDIDATE
    assert result.candidates[0].product_id == "product-a"
    assert result.requires_confirmation is True
