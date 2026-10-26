"""Deterministic texture used by the Windows reference renderer."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "reference_texture", ROOT / "pipeline" / "generate_reference_texture.py",
)
TEXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TEXTURE)


def test_reference_texture_is_deterministic_and_matches_panel_dimensions():
    first = TEXTURE.create_texture()
    second = TEXTURE.create_texture()
    assert first.size == (400, 640) and first.mode == "RGB"
    assert first.tobytes() == second.tobytes()
    assert first.crop((0, 0, 64, 64)).tobytes() != first.crop((64, 0, 128, 64)).tobytes()


@pytest.mark.skipif(
    sys.platform != "win32", reason="The Windows demo renderer uses installed Arial.",
)
def test_complete_reference_preserves_panel_dimensions_and_clear_display():
    panel = json.loads((ROOT / "assets" / "panel_map.json").read_text(encoding="utf-8"))
    image = TEXTURE.create_reference(panel)
    assert image.size == (panel["width_pixels"], panel["height_pixels"])
    assert image.mode == "RGB"
    assert image.getpixel((200, 220)) == (255, 255, 255)
