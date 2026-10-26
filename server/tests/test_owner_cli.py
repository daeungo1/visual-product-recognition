"""Owner CLI bootstrap sequencing and private-output contract."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "provision_cloud",
    ROOT / "pipeline" / "provision_cloud.py",
)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def test_prepare_only_does_not_require_api_url_output_or_token():
    args = CLI.create_parser().parse_args(["--seed-demo", "--prepare-only"])
    assert args.api_url is None and args.output is None and args.prepare_only


def test_activation_has_an_explicit_separate_mode():
    args = CLI.create_parser().parse_args(
        [
            "--activate-only",
            "--api-url",
            "https://example.org",
            "--output",
            "server\\data\\private\\pair.json",
        ]
    )
    assert args.activate_only


def test_no_device_invitation_is_issued_before_successful_indexing(monkeypatch):
    documents = Mock()
    monkeypatch.setattr(CLI, "reindex", lambda *_: {"indexed": 0})
    with pytest.raises(ValueError):
        CLI.activate("https://example.org", documents)
    documents.create.assert_not_called()


def test_demo_reference_versions_preserve_published_ids_and_geometry():
    panel = {"target_id": CLI.DEMO_GUIDE.target_id, "buttons": {"power": [0.1, 0.2, 0.3, 0.4]}}
    guide, versioned_panel = CLI.versioned_demo_assets(b"first reference", panel)
    assert guide["id"] != CLI.DEMO_GUIDE.id
    assert guide["target_id"] != CLI.DEMO_GUIDE.target_id
    assert versioned_panel["target_id"] == guide["target_id"]
    assert versioned_panel["buttons"] == panel["buttons"]
    assert panel["target_id"] == CLI.DEMO_GUIDE.target_id
    assert guide["demo"] is True
    assert guide["steps"] == CLI.DEMO_GUIDE.model_dump()["steps"]


def test_demo_reference_versions_are_deterministic_and_change_with_pixels():
    first = CLI.versioned_demo_assets(b"first reference", {})
    assert CLI.versioned_demo_assets(b"first reference", {}) == first
    second = CLI.versioned_demo_assets(b"changed reference", {})
    assert first[0]["id"] != second[0]["id"]
    assert first[0]["target_id"] != second[0]["target_id"]
