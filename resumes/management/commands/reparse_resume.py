"""Re-run AI parsing for resumes.

Usage:
    python manage.py reparse_resume 5
    python manage.py reparse_resume 5 7 9
    python manage.py reparse_resume --pending
    python manage.py reparse_resume --pending --queue   # let the Celery worker do it
"""
from django.core.management.base import BaseCommand, CommandError
from kombu.exceptions import OperationalError

from resumes.models import Resume
from resumes.services.resume_parsing import parse_and_store
from resumes.tasks import parse_resume_task


class Command(BaseCommand):
    help = "Run AI parsing again for the given resume IDs, or for all resumes waiting for AI."

    def add_arguments(self, parser):
        parser.add_argument("resume_ids", nargs="*", type=int, help="IDs of the resumes to parse.")
        parser.add_argument(
            "--pending",
            action="store_true",
            help="Parse every resume that has extracted text but no AI result yet.",
        )
        parser.add_argument(
            "--queue",
            action="store_true",
            help="Send the resumes to the Celery worker instead of parsing them here.",
        )

    def handle(self, *args, resume_ids, pending, queue, **options):
        if pending:
            resumes = list(Resume.objects.filter(status=Resume.Status.EXTRACTED))
        elif resume_ids:
            resumes = list(Resume.objects.filter(pk__in=resume_ids))
            missing = set(resume_ids) - {resume.pk for resume in resumes}
            if missing:
                raise CommandError(f"Resume(s) not found: {sorted(missing)}")
        else:
            raise CommandError("Give one or more resume IDs, or use --pending.")

        if queue:
            self.send_to_worker(resumes)
            return

        for resume in resumes:
            resume = parse_and_store(resume)
            style = self.style.SUCCESS if resume.status == Resume.Status.PARSED else self.style.WARNING
            line = f"Resume {resume.pk}: {resume.get_status_display()}"
            if resume.error_message:
                line += f" ({resume.error_message})"
            self.stdout.write(style(line))

    def send_to_worker(self, resumes):
        sent = 0
        for resume in resumes:
            if resume.status != Resume.Status.EXTRACTED:
                # The task only parses waiting resumes; use the command without --queue
                # to re-parse a resume that already has an AI result.
                self.stdout.write(
                    self.style.WARNING(f"Resume {resume.pk}: skipped ({resume.get_status_display()})")
                )
                continue
            resume.error_message = ""  # the result page shows "Analysing…" again
            resume.save(update_fields=["error_message", "updated_at"])
            try:
                task = parse_resume_task.delay(resume.pk)
            except OperationalError as exc:
                raise CommandError("Redis is not reachable. Is Docker Desktop running?") from exc
            self.stdout.write(self.style.SUCCESS(f"Resume {resume.pk}: queued (task {task.id})"))
            sent += 1
        self.stdout.write(f"{sent} resume(s) sent to the worker.")