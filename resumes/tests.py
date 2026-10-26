"""Tests for resume validation, extraction, upload views and access control."""
import shutil
import tempfile

import pymupdf
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import Resume
from .services.pdf_extraction import clean_text, extract_text
from .services.pdf_validation import ResumeValidationError, validate_resume_file
from .services.resume_intake import create_resume

User = get_user_model()

# Uploaded files in tests go to a temporary folder, never to the real media/ folder.
TEMP_MEDIA_ROOT = tempfile.mkdtemp()

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
    pix.clear_with(200)
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


def read_and_close(response) -> bytes:
    """Read a file download completely. Reading to the end also closes it."""
    return b"".join(response.streaming_content)


# ---------------------------------------------------------------------------
# Validation (Part A)
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
# Extraction (Part A)
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


# ---------------------------------------------------------------------------
# Upload views (Part B)
# ---------------------------------------------------------------------------
@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ResumeUploadViewTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def post_upload(self, data, name="Asha_Rao_Resume.pdf"):
        return self.client.post(reverse("resumes:upload"), {"file": upload(data, name=name)})

    def test_upload_page_loads_with_multipart_form(self):
        response = self.client.get(reverse("resumes:upload"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_valid_upload_creates_resume_with_extracted_text(self):
        response = self.post_upload(make_text_pdf())
        resume = Resume.objects.get()
        self.assertRedirects(response, reverse("resumes:detail", args=[resume.pk]))
        self.assertEqual(resume.status, Resume.Status.EXTRACTED)
        self.assertIn("Python Developer", resume.extracted_text)
        self.assertEqual(resume.original_filename, "Asha_Rao_Resume.pdf")
        # The file on disk has a random name, never the person's name.
        self.assertTrue(resume.file.name.startswith("resumes/"))
        self.assertNotIn("Asha", resume.file.name)

    def test_invalid_upload_shows_error_and_saves_nothing(self):
        response = self.post_upload(b"MZ this is not a pdf", name="resume.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not a real PDF")
        self.assertEqual(Resume.objects.count(), 0)

    def test_scanned_pdf_is_saved_as_failed_with_message(self):
        self.post_upload(make_image_only_pdf())
        resume = Resume.objects.get()
        self.assertEqual(resume.status, Resume.Status.FAILED)
        self.assertIn("scanned", resume.error_message)

    def test_same_file_twice_in_same_session_is_not_duplicated(self):
        data = make_text_pdf()
        self.post_upload(data)
        self.post_upload(data)
        self.assertEqual(Resume.objects.count(), 1)

    def test_uploader_can_view_and_download_own_upload(self):
        self.post_upload(make_text_pdf())
        resume = Resume.objects.get()
        detail = self.client.get(reverse("resumes:detail", args=[resume.pk]))
        self.assertEqual(detail.status_code, 200)

        response = self.client.get(reverse("resumes:download", args=[resume.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertTrue(read_and_close(response).startswith(b"%PDF-"))

    def test_stranger_gets_404_for_detail_and_download(self):
        self.post_upload(make_text_pdf())
        resume = Resume.objects.get()
        stranger = Client()  # a different browser with no session
        for url_name in ("resumes:detail", "resumes:download"):
            response = stranger.get(reverse(url_name, args=[resume.pk]))
            self.assertEqual(response.status_code, 404)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class ResumeOwnershipTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@example.com", password="S3cure-pass-123")
        self.other = User.objects.create_user(email="other@example.com", password="S3cure-pass-123")
        self.admin = User.objects.create_superuser(email="admin@example.com", password="S3cure-pass-123")
        validated = validate_resume_file(upload(make_text_pdf()))
        self.resume = create_resume(validated, "resume.pdf", owner=self.owner)
        self.url = reverse("resumes:download", args=[self.resume.pk])

    def download_as(self, user):
        self.client.force_login(user)
        response = self.client.get(self.url)
        if response.status_code == 200:
            read_and_close(response)
        return response

    def test_owner_can_download(self):
        self.assertEqual(self.download_as(self.owner).status_code, 200)

    def test_other_logged_in_user_gets_404(self):
        self.assertEqual(self.download_as(self.other).status_code, 404)

    def test_admin_can_download(self):
        self.assertEqual(self.download_as(self.admin).status_code, 200)

    def test_download_is_never_cached(self):
        response = self.download_as(self.owner)
        self.assertIn("no-store", response["Cache-Control"])