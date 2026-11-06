"""Primary allocations balance workload without altering completed reviews."""
from collections import Counter
from io import StringIO
import json

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.management.commands.allocate_teacher_reviews import COHORT_CODES, ROSTER_EMAILS
from assessment.models import (
    ExamSubmission, ExpertGrade, ExpertRating, ItemReviewAssignment,
    SubmissionReviewAssignment, TeacherReviewAssignment,
)
from assessment.review_allocation import balanced_owners
from trace_backend.test_utils import ApiTestCase


class BalancedOwnersTests(SimpleTestCase):
    def test_sixty_items_give_each_teacher_six_without_duplicated_owners(self):
        teachers, items = list(range(10)), list(range(60))
        owners = balanced_owners(teachers, items)
        self.assertEqual(set(owners), set(items))
        self.assertEqual(Counter(owners.values()), Counter(dict.fromkeys(teachers, 6)))
        self.assertEqual(owners, balanced_owners(teachers, items))

    def test_237_submissions_produce_seven_24_and_three_23_queues(self):
        owners = balanced_owners(range(10), range(237), groups={key: key % 4 for key in range(237)})
        self.assertEqual(Counter(Counter(owners.values()).values()), {24: 7, 23: 3})

    def test_existing_unique_completed_submissions_keep_the_same_teacher(self):
        prior = {key: [7] for key in range(18)}
        prior.update({key: [8] for key in range(18, 23)})
        prior[23] = [0]
        owners = balanced_owners(range(10), range(237), prior)
        for key, teachers in prior.items():
            self.assertEqual(owners[key], teachers[0])

    def test_overlapping_item_reviews_and_eight_previous_reviews_do_not_break_six_quota(self):
        prior = {key: [7] for key in range(8)}
        prior[0] = [0, 4, 7]
        owners = balanced_owners(range(10), range(60), prior)
        self.assertEqual(set(Counter(owners.values()).values()), {6})
        self.assertEqual(owners[0], 0)
        self.assertEqual(sum(owners[key] == 7 for key in range(8)), 6)
        # Prior data is input history, including reviews that cannot all be primary.
        self.assertEqual(len([key for key in prior if 7 in prior[key]]), 8)

    def test_invalid_rosters_or_duplicate_tasks_fail_instead_of_silently_dropping_work(self):
        for teachers, tasks in (([], [1]), ([1, 1], [1]), ([1], [1, 1])):
            with self.subTest(teachers=teachers, tasks=tasks), self.assertRaises(ValueError):
                balanced_owners(teachers, tasks)
        self.assertEqual(balanced_owners([1, 2], []), {})


class AllocationCommandTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.teachers = []
        for index, email in enumerate(ROSTER_EMAILS):
            teacher = User.objects.create_user(username=f'roster-{index}', email=email)
            ParticipantProfile.objects.create(user=teacher, role='EXPERT_TEACHER', full_name=f'Teacher {index}')
            self.teachers.append(teacher)
        students = User.objects.bulk_create([User(username=code) for code in COHORT_CODES])
        ParticipantProfile.objects.bulk_create([
            ParticipantProfile(user=student, participant_code=code, role='STUDENT')
            for student, code in zip(students, COHORT_CODES)])
        self.submissions = ExamSubmission.objects.bulk_create([
            ExamSubmission(student=student, exam_type=exam, score_pct=47)
            for student, code in zip(students, COHORT_CODES)
            for exam in ('pre', 'post', 'transfer', 'withdrawal')
            if not (exam == 'withdrawal' and code in ('SIM-007', 'SIM-027', 'SIM-053'))
        ])
        self.bank_keys = [item['id'] for _, item in scoring.all_items()]

    def allocate(self, apply=False):
        output = StringIO()
        call_command('allocate_teacher_reviews', **{'apply': apply, 'stdout': output})
        return json.loads(output.getvalue())

    def test_default_is_dry_run_and_apply_is_balanced_idempotent_and_preserves_grades(self):
        prior = ExpertGrade.objects.bulk_create([
            ExpertGrade(submission=sub, expert_user=self.teachers[7], assigned_marks=65,
                        feedback_comments='Previously completed work')
            for sub in self.submissions[:18]
        ])
        for key in self.bank_keys[:8]:
            ExpertRating.objects.create(expert_user=self.teachers[7], item_key=key,
                                        feedback='Previously completed item comment')
        # A historical submission outside SIM-001..060 is not part of the new workload.
        old_user = User.objects.create_user(username='legacy-student')
        old_submission = ExamSubmission.objects.create(student=old_user, exam_type='pre')
        before_grades = list(ExpertGrade.objects.order_by('pk').values())
        before_ratings = list(ExpertRating.objects.order_by('pk').values())
        preview = self.allocate()
        self.assertEqual(preview['status'], 'dry_run')
        self.assertEqual(preview['submission_count'], 237)
        self.assertEqual(preview['missing_expected_submissions'], 3)
        self.assertFalse(TeacherReviewAssignment.objects.exists())
        self.assertFalse(ItemReviewAssignment.objects.exists())
        self.assertFalse(SubmissionReviewAssignment.objects.exists())

        report = self.allocate(apply=True)
        self.assertEqual(report['status'], 'applied')
        self.assertEqual(TeacherReviewAssignment.objects.count(), 10)
        self.assertEqual(ItemReviewAssignment.objects.count(), 60)
        self.assertEqual(SubmissionReviewAssignment.objects.count(), 237)
        self.assertEqual({row['items_assigned'] for row in report['teachers']}, {6})
        self.assertEqual(Counter(row['submissions_assigned'] for row in report['teachers']), {24: 7, 23: 3})
        self.assertFalse(SubmissionReviewAssignment.objects.filter(submission=old_submission).exists())
        for grade in prior:
            self.assertEqual(SubmissionReviewAssignment.objects.get(
                submission=grade.submission).expert_user_id, grade.expert_user_id)
        before_owners = list(SubmissionReviewAssignment.objects.order_by('pk').values())
        again = self.allocate(apply=True)
        self.assertEqual(again['status'], 'already_configured')
        self.assertEqual(again['teachers'], report['teachers'])
        self.assertEqual(list(SubmissionReviewAssignment.objects.order_by('pk').values()), before_owners)
        self.assertEqual(list(ExpertGrade.objects.order_by('pk').values()), before_grades)
        self.assertEqual(list(ExpertRating.objects.order_by('pk').values()), before_ratings)

    def test_invalid_teacher_role_prevents_all_assignment_writes(self):
        self.teachers[3].profile.role = 'STUDENT'
        self.teachers[3].profile.save(update_fields=['role'])
        with self.assertRaises(CommandError):
            self.allocate(apply=True)
        self.assertFalse(TeacherReviewAssignment.objects.exists())
        self.assertFalse(ItemReviewAssignment.objects.exists())
        self.assertFalse(SubmissionReviewAssignment.objects.exists())

    def test_partial_existing_allocation_is_never_rebalanced_or_overwritten(self):
        row = TeacherReviewAssignment.objects.create(expert_user=self.teachers[0])
        with self.assertRaises(CommandError):
            self.allocate(apply=True)
        self.assertEqual(list(TeacherReviewAssignment.objects.values_list('pk', flat=True)), [row.pk])
        self.assertFalse(ItemReviewAssignment.objects.exists())
        self.assertFalse(SubmissionReviewAssignment.objects.exists())
