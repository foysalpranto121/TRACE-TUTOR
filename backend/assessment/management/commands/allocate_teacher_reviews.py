"""Allocate the named teacher roster without creating grades or rewriting history."""
from collections import Counter, defaultdict
import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import (
    ExamSubmission, ExpertGrade, ExpertRating, ItemReviewAssignment,
    SubmissionReviewAssignment, TeacherReviewAssignment,
)
from assessment.review_allocation import balanced_owners


ROSTER_EMAILS = (
    'aiyesha.cse@gmail.com', 'asique.iqbaldrmc@gmail.com', 'motaleb.fgc@gmail.com',
    'alamgirlm94@gmail.com', 'mdraihaniu@gmail.com', 'rokib.armc@gmail.com',
    'mamun.armc@gmail.com', 'shamim007.akanda@gmail.com', 'anisurict1@gmail.com',
    'kadirmd159@gmail.com',
)
COHORT_CODES = tuple(f'SIM-{number:03d}' for number in range(1, 61))


class Command(BaseCommand):
    help = 'Preview balanced primary reviews for the ten named teachers; --apply persists assignments only.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Save the first allocation atomically.')

    @transaction.atomic
    def handle(self, *args, **options):
        condition = Q(pk__in=[])
        for email in ROSTER_EMAILS:
            condition |= Q(email__iexact=email)
        query = User.objects.filter(condition).select_related('profile').order_by('pk')
        if options['apply']:
            # Serialize concurrent initial allocations without locking unrelated users.
            query = query.select_for_update(of=('self',))
        by_email = defaultdict(list)
        for user in query:
            by_email[user.email.casefold()].append(user)
        roster = []
        for email in ROSTER_EMAILS:
            matches = by_email[email]
            if len(matches) != 1:
                raise CommandError(f'Expected one account for {email}; found {len(matches)}.')
            teacher = matches[0]
            profile = getattr(teacher, 'profile', None)
            if not teacher.is_active or not profile or profile.role != 'EXPERT_TEACHER':
                raise CommandError(f'{email} must be an active EXPERT_TEACHER.')
            roster.append(teacher)
        teacher_ids = [user.pk for user in roster]

        profiles = ParticipantProfile.objects.filter(participant_code__in=COHORT_CODES)
        if set(profiles.values_list('participant_code', flat=True)) != set(COHORT_CODES):
            raise CommandError('All sixty SIM-001 through SIM-060 profiles must exist before allocation.')
        bank = scoring.all_items()
        item_keys = [item['id'] for _, item in bank]
        if len(item_keys) != 60 or len(set(item_keys)) != 60:
            raise CommandError('The reviewed bank must contain exactly sixty distinct items.')
        submissions = list(ExamSubmission.objects.filter(
            student__profile__participant_code__in=COHORT_CODES,
            exam_type__in=('pre', 'post', 'transfer', 'withdrawal'),
        ).order_by('student__profile__participant_code', 'submitted_at', 'pk'))
        submission_ids = [sub.pk for sub in submissions]
        if not submission_ids:
            raise CommandError('No cohort submissions exist to allocate.')

        prior_items, prior_submissions = defaultdict(set), defaultdict(set)
        for key, teacher in ExpertRating.objects.filter(
                expert_user_id__in=teacher_ids, item_key__in=item_keys).values_list('item_key', 'expert_user_id'):
            prior_items[key].add(teacher)
        for key, teacher in ExpertGrade.objects.filter(
                expert_user_id__in=teacher_ids, submission_id__in=submission_ids,
                is_graded=True).values_list('submission_id', 'expert_user_id'):
            prior_submissions[key].add(teacher)

        roster_rows = set(TeacherReviewAssignment.objects.filter(
            expert_user_id__in=teacher_ids).values_list('expert_user_id', flat=True))
        existing_items = dict(ItemReviewAssignment.objects.filter(
            item_key__in=item_keys).values_list('item_key', 'expert_user_id'))
        existing_submissions = dict(SubmissionReviewAssignment.objects.filter(
            submission_id__in=submission_ids).values_list('submission_id', 'expert_user_id'))
        configured = bool(roster_rows or existing_items or existing_submissions)
        if configured:
            if (roster_rows != set(teacher_ids) or set(existing_items) != set(item_keys)
                    or set(existing_submissions) != set(submission_ids)
                    or not set(existing_items.values()) <= set(teacher_ids)
                    or not set(existing_submissions.values()) <= set(teacher_ids)):
                raise CommandError('A partial or different allocation already exists; no assignments were changed.')
            item_owners, submission_owners = existing_items, existing_submissions
        else:
            item_owners = balanced_owners(teacher_ids, item_keys, prior_items,
                                          {item['id']: exam for exam, item in bank})
            submission_owners = balanced_owners(teacher_ids, submission_ids, prior_submissions,
                                                {sub.pk: sub.exam_type for sub in submissions})
            if options['apply']:
                TeacherReviewAssignment.objects.bulk_create([
                    TeacherReviewAssignment(expert_user_id=teacher) for teacher in teacher_ids])
                ItemReviewAssignment.objects.bulk_create([
                    ItemReviewAssignment(item_key=key, expert_user_id=teacher)
                    for key, teacher in item_owners.items()])
                SubmissionReviewAssignment.objects.bulk_create([
                    SubmissionReviewAssignment(submission_id=key, expert_user_id=teacher)
                    for key, teacher in submission_owners.items()])

        item_counts, submission_counts = Counter(item_owners.values()), Counter(submission_owners.values())
        teachers = []
        for teacher in roster:
            completed_items = sum(owner == teacher.pk and teacher.pk in prior_items[key]
                                  for key, owner in item_owners.items())
            completed_submissions = sum(owner == teacher.pk and teacher.pk in prior_submissions[key]
                                        for key, owner in submission_owners.items())
            teachers.append({
                'username': teacher.username, 'name': teacher.profile.full_name or teacher.get_full_name(),
                'items_assigned': item_counts[teacher.pk], 'items_completed': completed_items,
                'items_remaining': item_counts[teacher.pk] - completed_items,
                'submissions_assigned': submission_counts[teacher.pk],
                'submissions_completed': completed_submissions,
                'submissions_remaining': submission_counts[teacher.pk] - completed_submissions,
            })
        self.stdout.write(json.dumps({
            'status': 'already_configured' if configured else ('applied' if options['apply'] else 'dry_run'),
            'item_count': len(item_keys), 'submission_count': len(submission_ids),
            'missing_expected_submissions': 240 - len(submission_ids), 'teachers': teachers,
        }, ensure_ascii=False))
