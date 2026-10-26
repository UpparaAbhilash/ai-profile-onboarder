"""Re-run AI parsing for resumes.

Usage:
    python manage.py reparse_resume 5
    python manage.py reparse_resume 5 7 9
    python manage.py reparse_resume --pending
"""
from django.core.management.base import BaseCommand, CommandError

from resumes.models import Resume
from resumes.services.resume_parsing import parse_and_store


class Command(BaseCommand):
    help = "Run AI parsing again for the given resume IDs, or for all resumes waiting for AI."

    def add_arguments(self, parser):
        parser.add_argument("resume_ids", nargs="*", type=int, help="IDs of the resumes to parse.")
        parser.add_argument(
            "--pending",
            action="store_true",
            help="Parse every resume that has extracted text but no AI result yet.",
        )

    def handle(self, *args, resume_ids, pending, **options):
        if pending:
            resumes = list(Resume.objects.filter(status=Resume.Status.EXTRACTED))
        elif resume_ids:
            resumes = list(Resume.objects.filter(pk__in=resume_ids))
            missing = set(resume_ids) - {resume.pk for resume in resumes}
            if missing:
                raise CommandError(f"Resume(s) not found: {sorted(missing)}")
        else:
            raise CommandError("Give one or more resume IDs, or use --pending.")

        for resume in resumes:
            resume = parse_and_store(resume)
            style = self.style.SUCCESS if resume.status == Resume.Status.PARSED else self.style.WARNING
            line = f"Resume {resume.pk}: {resume.get_status_display()}"
            if resume.error_message:
                line += f" ({resume.error_message})"
            self.stdout.write(style(line))