"""Owner asset validation and safe idempotent registration, without cloud calls."""

import copy
import json
from pathlib import Path

import pytest
from test_cloud import MemoryDocuments

from guide_api.catalog import DEMO_GUIDE
from guide_api.registration import registration_documents, store_registration

ROOT = Path(__file__).resolve().parents[2]


def demo():
    return registration_documents(
        guide=DEMO_GUIDE.model_dump(),
        panel=json.loads((ROOT / "assets" / "panel_map.json").read_text()),
        reference=(ROOT / "assets" / "demo-target.png").read_bytes(),
        product_id="demo-aircon",
        model="Original synthetic demo",
        category="aircon",
        target_kind="remote",
        source_url=None,
        reviewed=True,
    )


def test_original_demo_geometry_is_not_reinvented():
    target, guide, image = demo()
    assert target["panel_map"]["width_pixels"] == image.width == 400
    assert target["panel_map"]["display"] == [0.13, 0.14, 0.87, 0.38]
    assert guide["guide"] == DEMO_GUIDE.model_dump()
    assert target["demo"] is True


@pytest.mark.parametrize("change", ["dimensions", "rectangle", "button", "target", "review"])
def test_rejects_unreviewed_or_misaligned_assets(change):
    guide = copy.deepcopy(DEMO_GUIDE.model_dump())
    panel = json.loads((ROOT / "assets" / "panel_map.json").read_text())
    if change == "dimensions":
        panel["width_pixels"] = 999
    elif change == "rectangle":
        panel["display"] = [0.7, 0.1, 0.2, 0.5]
    elif change == "button":
        panel["buttons"].pop("power")
    elif change == "target":
        panel["target_id"] = "different"
    with pytest.raises(ValueError):
        registration_documents(
            guide=guide,
            panel=panel,
            reference=(ROOT / "assets" / "demo-target.png").read_bytes(),
            product_id="demo-aircon",
            model="Original synthetic demo",
            category="aircon",
            target_kind="remote",
            source_url=None,
            reviewed=change != "review",
        )


def test_real_product_requires_source_model_and_review():
    guide = DEMO_GUIDE.model_dump()
    guide["demo"] = False
    panel = json.loads((ROOT / "assets" / "panel_map.json").read_text())
    with pytest.raises(ValueError):
        registration_documents(
            guide=guide,
            panel=panel,
            reference=(ROOT / "assets" / "demo-target.png").read_bytes(),
            product_id="reviewed-product",
            model="Applicable model",
            category="aircon",
            target_kind="remote",
            source_url=None,
            reviewed=True,
        )


def test_idempotence_never_overwrites_different_registered_product():
    target, guide, _ = demo()
    documents = MemoryDocuments()
    store_registration(documents, target, guide)
    store_registration(documents, target, guide)
    target["model"] = "Do not overwrite the reviewed model"
    with pytest.raises(ValueError):
        store_registration(documents, target, guide)
    assert documents.read("catalog", target["id"])["model"] == "Original synthetic demo"
