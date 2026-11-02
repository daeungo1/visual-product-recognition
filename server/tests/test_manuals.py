import hashlib
from pathlib import Path

import pytest

from visual_guide.manuals import extract_manual, pdf_sha256


def _two_page_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>"
        ),
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            b"<< /Length 66 >>\nstream\n"
            b"BT /F1 12 Tf 72 720 Td (MODEL WD80H25BHS FIRST PAGE) Tj ET\n"
            b"endstream"
        ),
        (
            b"<< /Length 52 >>\nstream\n"
            b"BT /F1 12 Tf 72 720 Td (SECOND PAGE GUIDE) Tj ET\n"
            b"endstream"
        ),
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode())
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(result)


def test_pdf_sha256_is_stable(tmp_path: Path):
    source = tmp_path / "manual.pdf"
    source.write_bytes(b"manual-content")

    assert pdf_sha256(source) == hashlib.sha256(b"manual-content").hexdigest().upper()


def test_extract_manual_preserves_page_order_and_detects_model_code(tmp_path: Path):
    source = tmp_path / "manual.pdf"
    source.write_bytes(_two_page_pdf())

    manual = extract_manual(
        source,
        text_extractor=lambda _: "MODEL WD80H25BHS FIRST PAGE\fSECOND PAGE GUIDE",
    )

    assert manual.page_count == 2
    assert [page.number for page in manual.pages] == [1, 2]
    assert "FIRST PAGE" in manual.pages[0].text
    assert "SECOND PAGE" in manual.pages[1].text
    assert manual.model_codes == ("WD80H25BHS",)


def test_extract_manual_rejects_invalid_pdf(tmp_path: Path):
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"not a pdf")

    with pytest.raises(ValueError, match="valid PDF"):
        extract_manual(source, text_extractor=lambda _: "")
