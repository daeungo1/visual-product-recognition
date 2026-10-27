import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("stage_web", ROOT / "pipeline" / "stage_web.py")
assert SPEC and SPEC.loader
web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web)


def test_static_package_is_allowlisted_and_has_mobile_home(tmp_path):
    assets = tmp_path / "assets"
    for name in web.PUBLIC_FILES:
        path = assets / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
    (assets / "private.json").write_text("never publish", encoding="utf-8")
    output = tmp_path / "site"
    web.stage_web(assets, output)
    assert {str(p.relative_to(output).as_posix()) for p in output.rglob("*") if p.is_file()} == {
        *web.PUBLIC_FILES,
        "index.html",
    }
    assert (output / "index.html").read_bytes() == (assets / "photo-demo.html").read_bytes()


def test_staging_preserves_existing_pages_home(tmp_path):
    output = tmp_path / "site"
    web.stage_web(ROOT / "assets", output, entry="product-demo.html")
    assert (output / "index.html").read_bytes() == (ROOT / "assets/product-demo.html").read_bytes()


def test_staging_refuses_stale_directory(tmp_path):
    output = tmp_path / "site"
    output.mkdir()
    (output / "secret.txt").write_text("stale", encoding="utf-8")
    with pytest.raises(FileExistsError):
        web.stage_web(ROOT / "assets", output)
    assert (output / "secret.txt").read_text() == "stale"


def test_staging_missing_source_does_not_create_output(tmp_path):
    with pytest.raises(FileNotFoundError):
        web.stage_web(tmp_path / "missing", tmp_path / "site")
    assert not (tmp_path / "site").exists()


def test_staging_rejects_output_inside_assets_and_unknown_home(tmp_path):
    with pytest.raises(ValueError):
        web.stage_web(ROOT / "assets", ROOT / "assets" / "site")
    with pytest.raises(ValueError):
        web.stage_web(ROOT / "assets", tmp_path / "site", entry="private.json")


def test_static_host_has_no_api_fallback_or_external_photo_connections():
    config = json.loads((ROOT / "assets/staticwebapp.config.json").read_text("utf-8"))
    assert "navigationFallback" not in config
    assert {"route": "/api/*", "statusCode": 404} in config["routes"]
    assert "connect-src 'self'" in config["globalHeaders"]["Content-Security-Policy"]
    assert config["globalHeaders"]["X-Content-Type-Options"] == "nosniff"
