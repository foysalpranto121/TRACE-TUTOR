"""Dedicated grading worker.

    python manage.py grade_submissions              # poll forever
    python manage.py grade_submissions --once       # drain the queue and exit
    python manage.py grade_submissions --retry-failed

The web process grades submissions on its own background threads, so this is optional
on a single lab server. Run it alongside the web server when that server has several
worker processes, or after a restart to pick up anything left pending.
"""
import time

from django.core.management.base import BaseCommand

from assessment import grading
from assessment.models import ExamSubmission


class Command(BaseCommand):
    help = 'Grade pending exam submissions from a separate process.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='drain the queue once and exit')
        parser.add_argument('--interval', type=float, default=2.0, help='seconds between polls')
        parser.add_argument('--retry-failed', action='store_true',
                            help='requeue submissions whose grading failed before starting')

    def handle(self, *args, **options):
        if options['retry_failed']:
            requeued = grading.retry_failed()
            self.stdout.write(f'requeued {requeued} failed submission(s)')

        while True:
            graded = grading.grade_pending(workers=grading._concurrency())
            pending = ExamSubmission.objects.filter(grading_status=ExamSubmission.PENDING).count()
            if graded:
                self.stdout.write(f'graded {graded}; {pending} still pending')
            if options['once']:
                if pending:
                    self.stdout.write(f'{pending} submission(s) still pending (claimed by another grader?)')
                return
            time.sleep(options['interval'])
