"""Real-model references never grant photo redistribution or product guidance approval."""

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]


def test_two_photo_models_have_exact_official_sources_without_invented_controls():
    data = json.loads((ROOT / "assets" / "products" / "catalog.json").read_text("utf-8"))
    assert data["mode"] == "local-photo-reference"
    assert data["bundled_third_party_photos"] is False
    entries = data["products"]
    assert {p["model"] for p in entries} == {"AF90H19D35WN", "LS32HG802SKXKR"}
    assert len(entries) == 2
    for entry in entries:
        assert entry["review_status"] == "reference-only"
        assert entry["model"] in entry["support_url"]
        assert entry["model"] in entry["photo_source_url"]
        for key in ("support_url", "photo_source_url"):
            parsed = urlparse(entry[key])
            assert parsed.scheme == "https" and parsed.hostname == "www.samsung.com"
        assert not ({"controls", "target_id", "steps", "image"} & entry.keys())
        assert entry["issue"]
