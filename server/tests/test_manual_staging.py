import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from visual_guide.manual_staging import stage_reviewed_manual


class Response(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_stage_reviewed_manual_downloads_and_verifies_before_publish(tmp_path: Path):
    content = b"%PDF-reviewed-manual"
    digest = hashlib.sha256(content).hexdigest().upper()
    destination = tmp_path / "manual.pdf"

    staged = stage_reviewed_manual(
        destination=destination,
        source_url="https://example.test/manual.pdf",
        expected_sha256=digest,
        opener=lambda _url: Response(content),
    )

    assert staged == destination
    assert destination.read_bytes() == content
    assert not destination.with_suffix(".pdf.tmp").exists()


def test_stage_reviewed_manual_rejects_wrong_hash_without_publishing(tmp_path: Path):
    destination = tmp_path / "manual.pdf"

    with pytest.raises(ValueError, match="SHA-256"):
        stage_reviewed_manual(
            destination=destination,
            source_url="https://example.test/manual.pdf",
            expected_sha256="A" * 64,
            opener=lambda _url: Response(b"%PDF-wrong"),
        )

    assert not destination.exists()
