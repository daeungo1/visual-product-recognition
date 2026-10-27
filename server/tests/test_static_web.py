import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("stage_web", ROOT / "pipeline" / "stage_web.py")
assert SPEC and SPEC.loader
web = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(web)

AR_MODULES = sorted((ROOT / "assets" / "ar").glob("*.js"))
AR_PAGE = ROOT / "assets" / "ar-demo.html"
README_URL = "https://github.com/daeungo1/visual-product-recognition#readme"
# Camera frames stay on the device: no network channel, no persistence or recording API.
OFF_DEVICE_APIS = (
    "XMLHttpRequest",
    "WebSocket",
    "sendBeacon",
    "EventSource",
    "importScripts",
    "new Worker",
    "WebAssembly",
    "toDataURL",
    "toBlob",
    "MediaRecorder",
    "captureStream",
    "localStorage",
    "sessionStorage",
    "indexedDB",
)
PERMISSIONS_POLICY = "camera=(self), microphone=(), geolocation=()"


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
    assert (output / "index.html").read_bytes() == (assets / "ar-demo.html").read_bytes()


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


def test_camera_permission_is_limited_to_the_site_itself():
    config = json.loads((ROOT / "assets/staticwebapp.config.json").read_text("utf-8"))
    assert config["globalHeaders"]["Permissions-Policy"] == PERMISSIONS_POLICY


def test_every_ar_module_is_published_and_nothing_else_under_ar():
    published = {name for name in web.PUBLIC_FILES if name.startswith("ar/")}
    assert published == {f"ar/{path.name}" for path in AR_MODULES}
    assert len(published) >= 11


def test_ar_code_has_no_network_or_persistence_channel_for_camera_frames():
    for path in [*AR_MODULES, AR_PAGE]:
        text = path.read_text("utf-8")
        for api in OFF_DEVICE_APIS:
            assert api not in text, f"{path.name} uses {api}"
    app = (ROOT / "assets/ar/app.js").read_text("utf-8")
    assert re.findall(r"fetch\(\s*['\"]([^'\"]+)['\"]", app) == ["scenarios/catalog.json"]
    assert not re.findall(r"\bfetch\(\s*[^'\"\s]", app)


def test_ar_page_loads_only_its_own_module_and_is_labeled_synthetic():
    html = AR_PAGE.read_text("utf-8")
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
    assert len(scripts) == 1
    attributes, body = scripts[0]
    assert body.strip() == ""
    assert 'type="module"' in attributes and 'src="ar/app.js"' in attributes
    for target in re.findall(r"""\b(?:src|href)\s*=\s*["']([^"']+)["']""", html):
        assert target == README_URL or "://" not in target, target
    assert "합성" in re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    assert "삼성 제품·공식 절차·실제 진단이 아닙니다" in html
    assert 'href="product-demo.html?ar=1"' in html


def test_pc_target_page_supports_the_camera_ar_mode():
    page = (ROOT / "assets/product-demo.html").read_text("utf-8")
    assert 'get("ar") === "1"' in page
    assert "html.ar" in page and "ar-only" in page and "full-only" in page


def test_registered_ar_targets_match_the_scenario_catalog():
    catalog = json.loads((ROOT / "assets/scenarios/catalog.json").read_text("utf-8"))
    assert catalog["demo"] is True
    scenarios = catalog["scenarios"]
    assert len({scenario["id"] for scenario in scenarios}) == len(scenarios) >= 4
    for scenario in scenarios:
        assert scenario["target_id"] == f"synthetic-{scenario['id']}-panel-v1"
        assert scenario["image"] == f"scenarios/{scenario['id']}.png"
        assert scenario["image"] in web.PUBLIC_FILES
        assert (ROOT / "assets" / scenario["image"]).is_file()
        rects = [scenario["display"], *(control["rect"] for control in scenario["controls"])]
        for left, top, right, bottom in rects:
            assert 0 <= left < right <= 1 and 0 <= top < bottom <= 1
