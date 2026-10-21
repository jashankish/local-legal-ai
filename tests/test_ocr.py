"""Scanned (image-only) PDFs: OCR when Tesseract is available, a clear message when not."""

import os

import pymupdf
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def scanned_pdf_bytes(dpi: int = 150) -> bytes:
    """Rasterise the sample lease into an image-only PDF, like an office scanner would."""
    source = pymupdf.open(os.path.join(REPO_ROOT, "samples", "commercial_lease.pdf"))
    scan = pymupdf.open()
    for page in source:
        pixmap = page.get_pixmap(dpi=dpi)
        out = scan.new_page(width=page.rect.width, height=page.rect.height)
        out.insert_image(out.rect, stream=pixmap.tobytes("png"))
    assert not scan[0].get_text().strip(), "fixture must have no text layer"
    return scan.tobytes()


def upload_scan(client, headers, name):
    return client.post(
        "/documents/upload", headers=headers,
        files={"file": (name, scanned_pdf_bytes(), "application/pdf")},
        data={"title": name, "category": "real_estate"},
    ).json()


def test_scan_without_ocr_explains_how_to_enable_it(client, admin_headers, monkeypatch):
    import rag.ocr as ocr

    monkeypatch.setattr(ocr, "tessdata_path", lambda: None)
    result = upload_scan(client, admin_headers, "scanned-lease-no-ocr.pdf")
    assert result["success"] is False
    assert "appears to be a scan" in result["message"]
    assert "Install Tesseract" in result["message"]


@pytest.mark.skipif(not __import__("rag.ocr", fromlist=["ocr_available"]).ocr_available(),
                    reason="Tesseract OCR is not installed (runs in CI and in the Docker image)")
def test_scanned_pdf_is_ocred_indexed_and_answerable(client, admin_headers):
    result = upload_scan(client, admin_headers, "scanned-lease.pdf")
    assert result["success"], result["message"]
    assert result["chunks_processed"] >= 3

    answer = client.post("/query", headers=admin_headers,
                         json={"question": "What is the monthly base rent for the premises?"}).json()
    top = answer["sources"][0]
    assert top["document_id"] == result["document_id"]
    assert top["metadata"]["extraction_method"] == "pymupdf+ocr"
    assert top["metadata"]["ocr_pages"] == 1
    assert "18,900" in " ".join(s["content"] for s in answer["sources"])
    client.delete(f"/documents/{result['document_id']}", headers=admin_headers)
