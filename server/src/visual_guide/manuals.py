"""Deterministic metadata and text extraction for reviewed PDF manuals."""

import hashlib
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

TextExtractor = Callable[[Path], str]
MODEL_CODE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}[A-Z0-9*-]{6,}(?![A-Z0-9])")


@dataclass(frozen=True)
class ExtractedPage:
    """One text page in source order."""

    number: int
    text: str


@dataclass(frozen=True)
class ExtractedManual:
    """Reviewable manual extraction metadata."""

    sha256: str
    page_count: int
    pages: tuple[ExtractedPage, ...]
    model_codes: tuple[str, ...]


def pdf_sha256(path: Path) -> str:
    """Return an uppercase SHA-256 digest for a local PDF."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _pdftotext(path: Path) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as error:
        raise ValueError("pdftotext is required to extract the manual.") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or "pdftotext failed"
        raise ValueError(f"Could not extract the PDF: {message}") from error
    return result.stdout


def extract_manual(
    path: Path,
    text_extractor: TextExtractor = _pdftotext,
) -> ExtractedManual:
    """Extract ordered page text and model-code candidates from a valid PDF."""
    if not path.is_file() or not path.read_bytes().startswith(b"%PDF-"):
        raise ValueError("Source is not a valid PDF.")
    extracted = text_extractor(path)
    page_texts = extracted.split("\f")
    if page_texts and not page_texts[-1].strip():
        page_texts.pop()
    pages = tuple(
        ExtractedPage(number=index, text=text.strip())
        for index, text in enumerate(page_texts, start=1)
    )
    candidates: list[str] = []
    for page in pages:
        for candidate in MODEL_CODE.findall(page.text.upper()):
            if any(character.isdigit() for character in candidate) and candidate not in candidates:
                candidates.append(candidate)
    return ExtractedManual(
        sha256=pdf_sha256(path),
        page_count=len(pages),
        pages=pages,
        model_codes=tuple(candidates),
    )
