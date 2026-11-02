"""Generic reviewed manual asset lookup and content verification."""

from pathlib import Path

from visual_guide.manuals import pdf_sha256
from visual_guide.registry import ManualReference


class ManualAssetProvider:
    """Resolve staged manuals by manifest asset name."""

    def __init__(self, root: Path):
        self.root = root

    def resolve(self, manual: ManualReference) -> Path:
        """Return an existing staged manual only when its hash matches."""
        path = self.root / manual.asset_name
        if not path.is_file():
            raise ValueError(f"Reviewed manual is not staged: {manual.asset_name}")
        if pdf_sha256(path) != manual.sha256:
            raise ValueError(f"Reviewed manual hash mismatch: {manual.asset_name}")
        return path
