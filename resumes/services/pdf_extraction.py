"""Extract plain text from a validated PDF using PyMuPDF."""
import re
from dataclasses import dataclass

import pymupdf
from django.conf import settings


class ExtractionError(Exception):
    """Text could not be extracted from the PDF."""


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    page_count: int
    char_count: int     # visible characters, whitespace not counted
    has_images: bool
    needs_ocr: bool     # True when the PDF looks scanned / has almost no text


def clean_text(raw: str) -> str:
    """Normalise extracted text: remove NUL bytes, trailing spaces and extra blank lines."""
    text = raw.replace("\x00", "")
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text)  # at most one empty line in a row
    return text.strip()


def extract_text(data: bytes) -> ExtractionResult:
    """Extract text from every page and decide whether the PDF needs OCR."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError("The PDF could not be opened.") from exc

    pages_text = []
    has_images = False
    with doc:
        page_count = doc.page_count
        for page in doc:
            # sort=True orders text blocks top-to-bottom, left-to-right,
            # which keeps multi-column resumes readable.
            pages_text.append(page.get_text("text", sort=True))
            if page.get_images():
                has_images = True

    text = clean_text("\n\n".join(pages_text))
    char_count = len(re.sub(r"\s", "", text))
    min_chars = settings.RESUME_MIN_TEXT_CHARS_PER_PAGE * max(page_count, 1)

    return ExtractionResult(
        text=text,
        page_count=page_count,
        char_count=char_count,
        has_images=has_images,
        needs_ocr=char_count < min_chars,
    )