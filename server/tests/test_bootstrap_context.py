"""Only curated canonical bootstrap files enter the server image context."""

import importlib.util
import json
from pathlib import Path

import pytest

from guide_api.cloud import token_hash

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "prepare_bootstrap_context",
    ROOT / "pipeline" / "prepare_bootstrap_context.py",
)
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)


def test_packaging_copies_exact_canonical_files_and_no_private_siblings(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "pipeline").mkdir()
    expected = {
        Path("assets") / "demo-target.png": b"canonical-demo-png",
        Path("assets") / "panel_map.json": b'{"demo":true}',
        Path("pipeline") / "provision_cloud.py": b"# canonical owner helper\n",
    }
    for path, content in expected.items():
        (tmp_path / path).write_bytes(content)
    (tmp_path / "assets" / ".env").write_text("must-not-be-copied")
    (tmp_path / "pipeline" / "private.json").write_text("must-not-be-copied")
    destinations = PACKAGER.prepare_context(tmp_path)
    context = tmp_path / "server" / "runtime_bootstrap"
    assert {path.relative_to(context) for path in destinations} == set(expected)
    for path, content in expected.items():
        assert (context / path).read_bytes() == content
    assert not (context / "assets" / ".env").exists()
    assert not (context / "pipeline" / "private.json").exists()
    assert PACKAGER.prepare_context(tmp_path) == destinations


def test_local_invite_file_is_private_new_and_stdout_contains_only_hash_expiry(tmp_path, capsys):
    output = tmp_path / "device-pair.json"
    result = PACKAGER.issue_local_invite(
        output,
        api_url="",
        valid_hours=168,
        now=1_790_000_000.0,
    )
    private = json.loads(output.read_text(encoding="utf-8"))
    assert set(private) == {"api_url", "code", "scope", "expires_at"}
    assert private["api_url"] == "" and private["scope"] == "device"
    assert private["expires_at"] == 1_790_000_000.0 + 168 * 3600
    assert result == {
        "BOOTSTRAP_DEVICE_INVITE_HASH": token_hash(private["code"]),
        "BOOTSTRAP_INVITE_EXPIRES_AT": private["expires_at"],
    }
    assert private["code"] not in capsys.readouterr().out
    with pytest.raises(ValueError):
        PACKAGER.issue_local_invite(output, api_url="", valid_hours=24)


def test_image_context_only_allows_exact_curated_bootstrap_paths():
    dockerignore = (ROOT / "server" / ".dockerignore").read_text()
    assert "!runtime_bootstrap/assets/demo-target.png" in dockerignore
    assert "!runtime_bootstrap/assets/panel_map.json" in dockerignore
    assert "!runtime_bootstrap/pipeline/provision_cloud.py" in dockerignore
    assert "!runtime_bootstrap/**" not in dockerignore
    assert "runtime_bootstrap/" in (ROOT / "server" / ".gitignore").read_text()


def test_local_cli_prints_only_the_control_plane_hash_and_expiry(tmp_path, capsys):
    output = tmp_path / "fresh-device-pair.json"
    assert (
        PACKAGER.main(
            [
                "--issue-device-code",
                "--output",
                str(output),
                "--api-url",
                "https://api.example.org",
                "--code-valid-hours",
                "24",
            ]
        )
        == 0
    )
    printed = capsys.readouterr().out
    private = json.loads(output.read_text(encoding="utf-8"))
    assert private["code"] not in printed
    assert set(json.loads(printed)) == {
        "BOOTSTRAP_DEVICE_INVITE_HASH",
        "BOOTSTRAP_INVITE_EXPIRES_AT",
    }
