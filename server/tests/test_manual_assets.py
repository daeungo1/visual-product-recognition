import hashlib
from pathlib import Path

import pytest

from visual_guide.manual_assets import ManualAssetProvider
from visual_guide.registry import ManualReference


def _manual(content: bytes) -> ManualReference:
    return ManualReference(
        manual_id="manual",
        source_url="https://example.test/manual.pdf",
        sha256=hashlib.sha256(content).hexdigest().upper(),
        language="ko-KR",
        revision="2026-09-16",
        asset_name="manual.pdf",
        applicable_models=("MODEL123",),
        reviewed=True,
    )


def test_manual_asset_provider_returns_hash_verified_path(tmp_path: Path):
    content = b"%PDF-reviewed"
    path = tmp_path / "manual.pdf"
    path.write_bytes(content)

    resolved = ManualAssetProvider(tmp_path).resolve(_manual(content))

    assert resolved == path


def test_manual_asset_provider_rejects_missing_or_wrong_content(tmp_path: Path):
    manual = _manual(b"%PDF-reviewed")
    provider = ManualAssetProvider(tmp_path)

    with pytest.raises(ValueError, match="not staged"):
        provider.resolve(manual)

    (tmp_path / "manual.pdf").write_bytes(b"%PDF-wrong")
    with pytest.raises(ValueError, match="hash"):
        provider.resolve(manual)
