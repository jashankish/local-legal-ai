"""Build the DOCX and PDF sample documents from their text sources.

Usage: .venv/bin/python scripts/build_samples.py
Outputs samples/mutual_nda.docx and samples/commercial_lease.pdf so every
supported upload format has an example.
"""

import os

import docx
import pymupdf as fitz

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCES = os.path.join(ROOT, "samples", "sources")


def paragraphs(name):
    with open(os.path.join(SOURCES, name), encoding="utf-8") as f:
        return [p.strip() for p in f.read().split("\n\n") if p.strip()]


def build_docx(source, target):
    document = docx.Document()
    parts = paragraphs(source)
    document.add_heading(parts[0], level=1)
    for paragraph in parts[1:]:
        document.add_paragraph(paragraph)
    document.save(target)


def build_pdf(source, target):
    parts = paragraphs(source)
    pdf = fitz.open()
    page_rect = fitz.paper_rect("letter")
    margin = 72
    box = fitz.Rect(margin, margin, page_rect.width - margin, page_rect.height - margin)
    page = pdf.new_page(width=page_rect.width, height=page_rect.height)
    y = box.y0
    for index, paragraph in enumerate(parts):
        size = 14 if index == 0 else 10.5
        font = "helvetica-bold" if index == 0 else "helvetica"
        height = (len(paragraph) // 95 + 2) * size * 1.35
        if y + height > box.y1:
            page = pdf.new_page(width=page_rect.width, height=page_rect.height)
            y = box.y0
        page.insert_textbox(fitz.Rect(box.x0, y, box.x1, y + height), paragraph,
                            fontsize=size, fontname=font)
        y += height
    pdf.save(target)


def build_scanned_pdf(source, target, dpi=200):
    """Image-only PDF (no text layer), as produced by an office scanner — exercises OCR."""
    tmp = target + ".tmp.pdf"
    build_pdf(source, tmp)
    text_pdf = fitz.open(tmp)
    scan = fitz.open()
    for page in text_pdf:
        pixmap = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        out = scan.new_page(width=page.rect.width, height=page.rect.height)
        out.insert_image(out.rect, stream=pixmap.tobytes("png"))
    text_pdf.close()
    os.remove(tmp)
    scan.save(target, deflate=True)


if __name__ == "__main__":
    build_docx("mutual_nda.txt", os.path.join(ROOT, "samples", "mutual_nda.docx"))
    build_pdf("commercial_lease.txt", os.path.join(ROOT, "samples", "commercial_lease.pdf"))
    build_scanned_pdf("lease_amendment.txt", os.path.join(ROOT, "samples", "inbox", "scanned_lease_amendment.pdf"))
    print("Built samples/mutual_nda.docx, samples/commercial_lease.pdf and "
          "samples/inbox/scanned_lease_amendment.pdf (image-only)")
