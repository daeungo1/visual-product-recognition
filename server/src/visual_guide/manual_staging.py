"""Download the reviewed manual and verify it before a container build."""

import argparse
import hashlib
import shutil
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

MANUAL_URL = (
    "https://org.downloadcenter.samsung.com/downloadfile/ContentsFile.aspx?"
    "CDSite=SVC&CttFileID=11813449&CDCttType=UM&ModelType=N&"
    "ModelName=WD80H25BHS&VPath=UM/202610/20261021130156626/"
    "OID139796_IB_WD80H-AD_28LCD_KO_260916.pdf"
)
MANUAL_SHA256 = "95E72378FAF9E9540D5FC047B8C76CB92C2E908AC0E5538B97A29A50054A1AC5"
DEFAULT_DESTINATION = Path("/app/data/WD80H25BHS_OID139796_KO.pdf")
Opener = Callable[[str], BinaryIO]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def stage_reviewed_manual(
    *,
    destination: Path,
    source_url: str = MANUAL_URL,
    expected_sha256: str = MANUAL_SHA256,
    opener: Opener = urllib.request.urlopen,
) -> Path:
    """Atomically publish only the exact reviewed manual content."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _sha256(destination) != expected_sha256:
            raise ValueError("Existing manual SHA-256 does not match the reviewed source.")
        return destination
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with opener(source_url) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        if _sha256(temporary) != expected_sha256:
            raise ValueError("Downloaded manual SHA-256 does not match the reviewed source.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def create_parser() -> argparse.ArgumentParser:
    """Create the manual staging command parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    return parser


def main() -> int:
    """Stage the reviewed manual for the production image."""
    try:
        destination = stage_reviewed_manual(
            destination=create_parser().parse_args().destination
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Staged reviewed manual: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
