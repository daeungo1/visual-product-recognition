import hashlib
import json
from pathlib import Path

import pytest

from visual_guide.registry import load_reviewed_registry


def _write_registry(
    root: Path,
    *,
    manual_bytes: bytes = b"%PDF-reviewed",
    reviewed: bool = True,
    source_page: int = 22,
    target_id: str = "detergent_dispenser",
) -> Path:
    product = root / "samsung" / "WD80H25BHS"
    (product / "guides").mkdir(parents=True)
    digest = hashlib.sha256(manual_bytes).hexdigest().upper()
    (product / "manifest.json").write_text(
        json.dumps(
            {
                "product_id": "samsung-wd80h25bhs",
                "manufacturer": "Samsung",
                "display_name": "Bespoke AI Combo 25/18kg",
                "product_family": "washer_dryer_combo",
                "aliases": ["Bespoke AI Combo", "비스포크 AI 콤보"],
                "exact_model_codes": ["WD80H25BHS"],
                "reviewed": reviewed,
                "manuals": [
                    {
                        "manual_id": "wd80h25bhs-ko-20260916",
                        "source_url": "https://example.test/manual.pdf",
                        "sha256": digest,
                        "language": "ko-KR",
                        "revision": "2026-09-16",
                        "asset_name": "WD80H25BHS.pdf",
                        "applicable_models": ["WD80H25BHS"],
                        "reviewed": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (product / "components.json").write_text(
        json.dumps(
            [
                {
                    "component_id": "detergent_dispenser",
                    "canonical_name": "세제함 전면 덮개",
                    "aliases": ["세제 넣는 곳", "세제함", "세제 투입구"],
                    "relative_region": "lower_front",
                },
                {
                    "component_id": "control_panel",
                    "canonical_name": "조작부",
                    "aliases": ["조작 버튼", "컨트롤 패널"],
                    "relative_region": "upper_center",
                },
            ]
        ),
        encoding="utf-8",
    )
    (product / "guides" / "detergent-and-controls.json").write_text(
        json.dumps(
            {
                "guide_id": "detergent-and-controls",
                "title": "세제함과 조작부 찾기",
                "exact_model_codes": ["WD80H25BHS"],
                "reviewed": True,
                "steps": [
                    {
                        "step_id": "locate-detergent-and-controls",
                        "required_state": "front_visible",
                        "target_ids": [target_id, "control_panel"],
                        "instruction": "세제함 전면 덮개와 조작부 위치를 확인하세요.",
                        "expected_state": "targets_confirmed",
                        "verification": "visual_confirmation",
                        "source_manual_id": "wd80h25bhs-ko-20260916",
                        "source_page": source_page,
                        "source_evidence": "제품 전면 하단의 세제함 전면 덮개를 엽니다.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (product / "issues.json").write_text(
        json.dumps(
            [
                {
                    "issue_intent": "detergent_loading",
                    "aliases": ["세제 넣기", "세제를 어디에 넣어"],
                    "required_states": ["front_visible"],
                    "guide_id": "detergent-and-controls",
                    "eligible_step_ids": ["locate-detergent-and-controls"],
                    "required_component_ids": ["detergent_dispenser"],
                    "optional_component_ids": ["control_panel"],
                }
            ]
        ),
        encoding="utf-8",
    )
    manual = root / "misleading-SEW-650DW.pdf"
    manual.write_bytes(manual_bytes)
    return manual


def test_registry_resolves_exact_model_and_accepts_matching_hash(tmp_path: Path):
    manual = _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    resolved = registry.resolve_guide(
        model_code="WD80H25BHS",
        guide_id="detergent-and-controls",
        manual_path=manual,
    )

    assert resolved.product.product_id == "samsung-wd80h25bhs"
    assert resolved.manual.manual_id == "wd80h25bhs-ko-20260916"
    assert resolved.guide.steps[0].target_ids == (
        "detergent_dispenser",
        "control_panel",
    )


def test_registry_rejects_wrong_manual_hash(tmp_path: Path):
    manual = _write_registry(tmp_path)
    manual.write_bytes(b"%PDF-different")
    registry = load_reviewed_registry(tmp_path)

    with pytest.raises(ValueError, match="hash"):
        registry.resolve_guide(
            model_code="WD80H25BHS",
            guide_id="detergent-and-controls",
            manual_path=manual,
        )


def test_registry_rejects_unknown_model(tmp_path: Path):
    manual = _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    with pytest.raises(LookupError, match="model"):
        registry.resolve_guide(
            model_code="WRONG123",
            guide_id="detergent-and-controls",
            manual_path=manual,
        )


def test_registry_rejects_unreviewed_product(tmp_path: Path):
    _write_registry(tmp_path, reviewed=False)

    with pytest.raises(ValueError, match="reviewed"):
        load_reviewed_registry(tmp_path)


def test_registry_rejects_missing_source_page(tmp_path: Path):
    _write_registry(tmp_path, source_page=0)

    with pytest.raises(ValueError, match="source_page"):
        load_reviewed_registry(tmp_path)


def test_registry_rejects_unknown_component(tmp_path: Path):
    _write_registry(tmp_path, target_id="unknown_part")

    with pytest.raises(ValueError, match="unknown component"):
        load_reviewed_registry(tmp_path)


def test_registry_resolves_normalized_exact_model(tmp_path: Path):
    _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    product = registry.resolve_exact_model(" wd80-h25bhs ")

    assert product.product_id == "samsung-wd80h25bhs"


def test_registry_searches_reviewed_product_aliases(tmp_path: Path):
    _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    matches = registry.search_product_candidates("비스포크 ai 콤보")

    assert [product.product_id for product in matches] == ["samsung-wd80h25bhs"]
    assert registry.search_product_candidates("generic washer photo") == ()


def test_registry_maps_issue_and_state_to_reviewed_guide(tmp_path: Path):
    _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    matches = registry.find_guide_candidates(
        product_id="samsung-wd80h25bhs",
        issue_intent="detergent_loading",
        current_state="front_visible",
    )

    assert [guide.guide_id for guide in matches] == ["detergent-and-controls"]
    assert (
        registry.find_guide_candidates(
            product_id="samsung-wd80h25bhs",
            issue_intent="detergent_loading",
            current_state="door_open",
        )
        == ()
    )


def test_registry_resolves_component_alias_without_cross_product_leakage(
    tmp_path: Path,
):
    _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    component = registry.resolve_component_alias(
        "samsung-wd80h25bhs",
        "세제 넣는 곳",
    )

    assert component.component_id == "detergent_dispenser"
    assert registry.resolve_component_alias("samsung-wd80h25bhs", "먼지망") is None


def test_registry_exposes_reviewed_manual_asset_metadata(tmp_path: Path):
    _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    manual = registry.manual_asset(
        "samsung-wd80h25bhs",
        "wd80h25bhs-ko-20260916",
    )

    assert manual.asset_name == "WD80H25BHS.pdf"


def test_registry_builds_legacy_manual_paths_without_product_hardcoding(
    tmp_path: Path,
):
    _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    class Provider:
        def resolve(self, manual):
            return Path("/manuals") / manual.asset_name

    paths = registry.model_manual_paths(Provider())

    assert paths == {"WD80H25BHS": Path("/manuals/WD80H25BHS.pdf")}


def test_registry_summary_includes_reviewed_intents_and_components(tmp_path: Path):
    _write_registry(tmp_path)
    registry = load_reviewed_registry(tmp_path)

    summary = registry.product_summaries()[0]

    assert summary["issue_mappings"][0]["issue_intent"] == "detergent_loading"
    assert summary["components"][0]["component_id"] == "control_panel"
    assert "조작 버튼" in summary["components"][0]["aliases"]
