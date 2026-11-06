"""Missing imported/legacy scores stay unavailable rather than crashing the Dashboard."""
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission
from trace_backend.test_utils import ApiTestCase

class DashboardScoreTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username='disposable-dashboard-student')
        ParticipantProfile.objects.create(user=self.user, role='STUDENT')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def summary(self):
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        return response.json()['assessments']['pre']

    def test_all_missing_graded_scores_remain_unavailable(self):
        ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=None)
        summary = self.summary()
        self.assertEqual(summary['attempts'], 1)
        self.assertIsNone(summary['latest_score'])
        self.assertIsNone(summary['best_score'])

    def test_a_missing_latest_score_does_not_erase_a_real_best_score(self):
        ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=85)
        ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=None)
        summary = self.summary()
        self.assertEqual(summary['attempts'], 2)
        self.assertIsNone(summary['latest_score'])
        self.assertEqual(summary['best_score'], 85)

    def test_zero_is_a_real_best_score(self):
        ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=None)
        ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=0)
        summary = self.summary()
        self.assertEqual(summary['latest_score'], 0)
        self.assertEqual(summary['best_score'], 0)
