"""Wipe every participant and everything they generated. Keeps staff accounts, the item
bank, expert ratings and the curriculum index.

    python manage.py reset_study_data          # shows what would go
    python manage.py reset_study_data --yes    # does it

For clearing development and pilot data before the real cohort enrols. There is no
undo: this deletes participants' accounts, profiles, submissions, expert grades of those
submissions, paper sittings, tokens and telemetry.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from assessment.models import ExamSubmission, ExpertGrade, PaperSitting
from logging_app.models import InteractionLog


class Command(BaseCommand):
    help = 'Delete all participant data (accounts, submissions, telemetry). Staff, item bank and ratings survive.'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='actually delete; without it, only report')

    def handle(self, *args, **options):
        participants = User.objects.filter(profile__role='STUDENT')
        counts = {
            'participants': participants.count(),
            'submissions': ExamSubmission.objects.filter(student__in=participants).count(),
            'expert grades on them': ExpertGrade.objects.filter(submission__student__in=participants).count(),
            'paper sittings': PaperSitting.objects.filter(student__in=participants).count(),
            'telemetry events': InteractionLog.objects.filter(user__in=participants).count(),
            'orphan telemetry (no user)': InteractionLog.objects.filter(user__isnull=True).count(),
        }
        for label, n in counts.items():
            self.stdout.write(f'  {label:28} {n}')
        staff = User.objects.exclude(profile__role='STUDENT').count()
        self.stdout.write(f'  {"staff accounts (kept)":28} {staff}')

        if not options['yes']:
            self.stdout.write(self.style.WARNING('Nothing deleted. Re-run with --yes to wipe the above.'))
            return

        with transaction.atomic():
            InteractionLog.objects.filter(user__isnull=True).delete()
            InteractionLog.objects.filter(user__in=participants).delete()
            deleted, _ = participants.delete()   # cascades profile, submissions, grades, sittings, tokens
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {counts["participants"]} participant(s) and everything they generated '
            f'({deleted} rows). Staff accounts, item bank, ratings and index untouched.'))
