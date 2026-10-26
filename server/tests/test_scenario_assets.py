"""The browser and Android consume the same explicitly synthetic troubleshooting assets."""

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def test_four_synthetic_scenarios_have_distinct_images_and_mapped_controls():
    catalog = json.loads((ROOT / "assets" / "scenarios" / "catalog.json").read_text("utf-8"))
    assert catalog["demo"] is True
    assert {entry["id"] for entry in catalog["scenarios"]} == {
        "aircon", "washer", "refrigerator", "monitor",
    }
    targets, hashes = set(), set()
    for scenario in catalog["scenarios"]:
        assert scenario["target_id"].startswith("synthetic-")
        targets.add(scenario["target_id"])
        path = ROOT / "assets" / scenario["image"]
        hashes.add(hashlib.sha256(path.read_bytes()).hexdigest())
        with Image.open(path) as image:
            assert image.size == (400, 640)
        assert len(scenario["controls"]) == 3
        assert len({control["id"] for control in scenario["controls"]}) == 3
        for rectangle in [scenario["display"], *[c["rect"] for c in scenario["controls"]]]:
            left, top, right, bottom = rectangle
            assert 0 <= left < right <= 1
            assert 0 <= top < bottom <= 1
        for control in scenario["controls"]:
            assert control["initial"] != control["expected"]
            assert control["instruction"] and control["expected"]
    assert len(targets) == len(hashes) == 4
