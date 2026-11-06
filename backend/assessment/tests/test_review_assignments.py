"""Assigned work is a default queue, while each teacher keeps independent reviews."""
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import (
    ExamSubmission, ExpertGrade, ExpertRating, ItemReviewAssignment,
    SubmissionReviewAssignment, TeacherReviewAssignment,
)
from trace_backend.test_utils import ApiTestCase


CRITERIA = ('alignment', 'accuracy', 'clarity', 'difficulty', 'answerability')


def account(username, role='EXPERT_TEACHER'):
    user = User.objects.create_user(username=username)
    ParticipantProfile.objects.create(user=user, role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


class ReviewAssignmentAPITests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.teacher, self.client = account('assigned-expert')
        self.other, self.other_client = account('other-assigned-expert')
        self.legacy, self.legacy_client = account('unconfigured-expert')
        self.student, self.student_client = account('assignment-student', 'STUDENT')
        TeacherReviewAssignment.objects.create(expert_user=self.teacher)
        TeacherReviewAssignment.objects.create(expert_user=self.other)
        self.item_ids = [item['id'] for _, item in scoring.all_items()[:3]]
        self.assigned_item = ItemReviewAssignment.objects.create(
            expert_user=self.teacher, item_key=self.item_ids[0])
        ItemReviewAssignment.objects.create(expert_user=self.other, item_key=self.item_ids[1])
        self.assigned_submission = ExamSubmission.objects.create(
            student=self.student, exam_type='pre', score_pct=47)
        self.other_submission = ExamSubmission.objects.create(
            student=self.student, exam_type='post', score_pct=67)
        self.unassigned_submission = ExamSubmission.objects.create(
            student=self.student, exam_type='transfer', score_pct=53)
        self.assignment = SubmissionReviewAssignment.objects.create(
            expert_user=self.teacher, submission=self.assigned_submission)
        SubmissionReviewAssignment.objects.create(
            expert_user=self.other, submission=self.other_submission)

    def reviews(self, client=None):
        response = (client or self.client).get('/api/expert/reviews/')
        self.assertEqual(response.status_code, 200)
        return {row['id']: row for row in response.json()['items_to_review']}

    def submissions(self, client=None):
        response = (client or self.client).get('/api/expert/submissions/')
        self.assertEqual(response.status_code, 200)
        return {row['id']: row for row in response.json()['submissions']}

    def grade(self, client=None, submission=None, **overrides):
        body = {'submission_id': (submission or self.assigned_submission).pk,
                'assigned_marks': 70, 'feedback': 'Independent teacher feedback',
                'expected_revision': None, **overrides}
        return (client or self.client).post('/api/expert/grade/', body, format='json')

    def rate(self, client=None, item_id=None, **overrides):
        body = {'item_id': item_id or self.item_ids[0],
                'ratings': dict.fromkeys(CRITERIA, 4),
                'feedback': 'Independent item comment', 'expected_revision': None, **overrides}
        return (client or self.client).post('/api/expert/rating/', body, format='json')

    def test_item_queue_marks_only_the_callers_assignments_but_keeps_more_available(self):
        rows = self.reviews()
        self.assertEqual(set(rows), {item['id'] for _, item in scoring.all_items()})
        self.assertTrue(rows[self.item_ids[0]]['is_assigned'])
        self.assertFalse(rows[self.item_ids[1]]['is_assigned'])
        self.assertFalse(rows[self.item_ids[2]]['is_assigned'])
        other = self.reviews(self.other_client)
        self.assertFalse(other[self.item_ids[0]]['is_assigned'])
        self.assertTrue(other[self.item_ids[1]]['is_assigned'])

    def test_submission_queue_marks_only_own_work_without_hiding_other_submissions(self):
        rows = self.submissions()
        self.assertEqual(set(rows), {self.assigned_submission.pk, self.other_submission.pk,
                                     self.unassigned_submission.pk})
        self.assertTrue(rows[self.assigned_submission.pk]['is_assigned'])
        self.assertFalse(rows[self.other_submission.pk]['is_assigned'])
        self.assertFalse(rows[self.unassigned_submission.pk]['is_assigned'])
        self.assertTrue(self.submissions(self.other_client)[self.other_submission.pk]['is_assigned'])

    def test_unconfigured_expert_retains_the_legacy_complete_queue(self):
        self.assertTrue(all(row['is_assigned'] for row in self.reviews(self.legacy_client).values()))
        self.assertTrue(all(row['is_assigned'] for row in self.submissions(self.legacy_client).values()))

    def test_configured_teacher_without_assignments_has_no_primary_work(self):
        empty, client = account('configured-empty-expert')
        TeacherReviewAssignment.objects.create(expert_user=empty)
        self.assertFalse(any(row['is_assigned'] for row in self.reviews(client).values()))
        self.assertFalse(any(row['is_assigned'] for row in self.submissions(client).values()))

    def test_prior_own_reviews_outside_assignment_remain_available_as_history(self):
        ExpertRating.objects.create(expert_user=self.teacher, item_key=self.item_ids[1],
                                    feedback='Earlier item comment')
        ExpertGrade.objects.create(submission=self.other_submission, expert_user=self.teacher,
                                   assigned_marks=65, feedback_comments='Earlier grade feedback')
        item = self.reviews()[self.item_ids[1]]
        self.assertFalse(item['is_assigned'])
        self.assertEqual(item['my_rating']['feedback'], 'Earlier item comment')
        row = self.submissions()[self.other_submission.pk]
        self.assertFalse(row['is_assigned'])
        self.assertTrue(row['my_grade_completed'])
        self.assertEqual(row['assigned_marks'], 65)
        self.assertEqual(row['feedback'], 'Earlier grade feedback')
        self.assertEqual(row['graded_by'], self.teacher.username)

    def test_other_teachers_grade_does_not_appear_as_my_completed_work_or_draft(self):
        ExpertGrade.objects.create(submission=self.assigned_submission, expert_user=self.other,
                                   assigned_marks=90, feedback_comments='Other teacher private draft')
        row = self.submissions()[self.assigned_submission.pk]
        self.assertFalse(row['my_grade_completed'])
        self.assertEqual(row['status'], 'PENDING_REVIEW')
        self.assertIsNone(row['assigned_marks'])
        self.assertIsNone(row['grade_revision'])
        self.assertIsNone(row['graded_by'])
        self.assertEqual(row['feedback'], '')
        self.assertEqual(row['score_pct'], 47)

    def test_both_experts_can_grade_the_same_submission_with_independent_revisions(self):
        first = self.grade()
        self.assertEqual(first.status_code, 200)
        other = self.grade(self.other_client, assigned_marks=90, feedback='Second expert feedback')
        self.assertEqual(other.status_code, 200)
        mine = self.submissions()[self.assigned_submission.pk]
        theirs = self.submissions(self.other_client)[self.assigned_submission.pk]
        self.assertEqual(mine['assigned_marks'], 70)
        self.assertEqual(mine['feedback'], 'Independent teacher feedback')
        self.assertEqual(mine['grade_revision'], first.json()['grade_revision'])
        self.assertEqual(theirs['assigned_marks'], 90)
        self.assertEqual(theirs['feedback'], 'Second expert feedback')
        self.assertEqual(theirs['grade_revision'], other.json()['grade_revision'])
        changed = self.grade(assigned_marks=75, expected_revision=first.json()['grade_revision'])
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.grade(assigned_marks=10,
                                   expected_revision=first.json()['grade_revision']).status_code, 409)
        self.assertEqual(ExpertGrade.objects.filter(submission=self.assigned_submission).count(), 2)
        self.assertEqual(ExpertGrade.objects.get(submission=self.assigned_submission,
                                                 expert_user=self.other).assigned_marks, 90)
        self.assigned_submission.refresh_from_db()
        self.assertEqual(self.assigned_submission.score_pct, 47)

    def test_more_allows_rating_and_grading_without_reassigning_the_primary_work(self):
        self.assertEqual(self.rate(item_id=self.item_ids[1]).status_code, 200)
        self.assertEqual(self.grade(submission=self.other_submission).status_code, 200)
        self.assertEqual(ItemReviewAssignment.objects.get(item_key=self.item_ids[1]).expert_user_id,
                         self.other.pk)
        self.assertEqual(SubmissionReviewAssignment.objects.get(
            submission=self.other_submission).expert_user_id, self.other.pk)
        self.assertFalse(self.reviews()[self.item_ids[1]]['is_assigned'])
        row = self.submissions()[self.other_submission.pk]
        self.assertFalse(row['is_assigned'])
        self.assertTrue(row['my_grade_completed'])

    def test_assigned_work_is_not_a_student_or_anonymous_permission_bypass(self):
        for client in (self.student_client, APIClient()):
            for endpoint in ('/api/expert/reviews/', '/api/expert/submissions/'):
                self.assertIn(client.get(endpoint).status_code, (401, 403))
            self.assertIn(self.rate(client).status_code, (401, 403))
            self.assertIn(self.grade(client).status_code, (401, 403))
        self.assertFalse(ExpertRating.objects.exists())
        self.assertFalse(ExpertGrade.objects.exists())
