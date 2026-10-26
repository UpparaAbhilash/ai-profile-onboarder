"""Tests for resume validation and text extraction."""
import pymupdf
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from .services.pdf_extraction import clean_text, extract_text
from .services.pdf_validation import ResumeValidationError, validate_resume_file

SAMPLE_TEXT = (
    "Asha Rao\n"
    "asha.rao@example.com\n"
    "Python Developer with 3 years of experience in Django and MySQL."
)


# ---------------------------------------------------------------------------
# Helpers that build small PDFs in memory
# ---------------------------------------------------------------------------
def make_text_pdf(text=SAMPLE_TEXT, pages=1) -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    return doc.tobytes()


def make_blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()


def make_image_only_pdf() -> bytes:
    """Simulates a scanned resume: one page containing only an image."""
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), False)
    pix.clear_with(200)  # light grey image
    page.insert_image(pymupdf.Rect(72, 72, 472, 272), pixmap=pix)
    return doc.tobytes()


def make_encrypted_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), SAMPLE_TEXT)
    return doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-secret", user_pw="user-secret"
    )


def upload(data: bytes, name="resume.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data, content_type="application/pdf")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
class ResumeValidationTests(SimpleTestCase):
    def test_valid_pdf_is_accepted(self):
        result = validate_resume_file(upload(make_text_pdf()))
        self.assertEqual(result.page_count, 1)
        self.assertEqual(len(result.sha256), 64)
        self.assertTrue(result.data.startswith(b"%PDF-"))

    def test_wrong_extension_is_rejected(self):
        with self.assertRaisesMessage(ResumeValidationError, "Only PDF files"):
            validate_resume_file(upload(make_text_pdf(), name="resume.docx"))

    def test_renamed_non_pdf_is_rejected(self):
        fake = b"MZ\x90\x00 this is really a Windows program"
        with self.assertRaisesMessage(ResumeValidationError, "not a real PDF"):
            validate_resume_file(upload(fake))

    def test_empty_file_is_rejected(self):
        with self.assertRaisesMessage(ResumeValidationError, "empty"):
            validate_resume_file(upload(b""))

    @override_settings(RESUME_MAX_UPLOAD_MB=0)
    def test_too_large_file_is_rejected(self):
        with self.assertRaisesMessage(ResumeValidationError, "too large"):
            validate_resume_file(upload(make_text_pdf()))

    def test_damaged_pdf_is_rejected(self):
        damaged = b"%PDF-1.7\nthis is not a valid PDF structure at all"
        with self.assertRaises(ResumeValidationError):
            validate_resume_file(upload(damaged))

    def test_password_protected_pdf_is_rejected(self):
        with self.assertRaisesMessage(ResumeValidationError, "password-protected"):
            validate_resume_file(upload(make_encrypted_pdf()))

    @override_settings(RESUME_MAX_PAGES=1)
    def test_too_many_pages_is_rejected(self):
        with self.assertRaisesMessage(ResumeValidationError, "at most 1 pages"):
            validate_resume_file(upload(make_text_pdf(pages=2)))

    def test_same_file_gives_same_hash(self):
        data = make_text_pdf()
        first = validate_resume_file(upload(data))
        second = validate_resume_file(upload(data, name="copy.pdf"))
        self.assertEqual(first.sha256, second.sha256)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
class TextExtractionTests(SimpleTestCase):
    def test_text_is_extracted(self):
        result = extract_text(make_text_pdf())
        self.assertIn("Python Developer", result.text)
        self.assertIn("asha.rao@example.com", result.text)
        self.assertFalse(result.needs_ocr)

    def test_blank_pdf_needs_ocr(self):
        result = extract_text(make_blank_pdf())
        self.assertEqual(result.char_count, 0)
        self.assertTrue(result.needs_ocr)
        self.assertFalse(result.has_images)

    def test_image_only_pdf_is_detected_as_scanned(self):
        result = extract_text(make_image_only_pdf())
        self.assertTrue(result.needs_ocr)
        self.assertTrue(result.has_images)

    def test_clean_text_removes_extra_blank_lines_and_spaces(self):
        raw = "Name   \n\n\n\nSkills\x00\n"
        self.assertEqual(clean_text(raw), "Name\n\nSkills")