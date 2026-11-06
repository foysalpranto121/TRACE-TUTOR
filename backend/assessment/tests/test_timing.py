from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import ParticipantProfile
from assessment import timing
from assessment.models import AssessmentTimeline, ExamSubmission
from trace_backend.test_utils import ApiTestCase


class TimingProtocolTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('timing-student')
        ParticipantProfile.objects.create(user=self.user, consent_given=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.start = timezone.now() - timedelta(days=40)

    def open_at(self, exam, at):
        with patch('django.utils.timezone.now', return_value=at):
            return self.client.get(f'/api/assessment/items/?type={exam}')

    def submit_at(self, exam, at):
        with patch('django.utils.timezone.now', return_value=at):
            return self.client.post('/api/assessment/submit/', {'exam_type': exam}, format='json')

    def begin_post(self):
        self.assertEqual(self.open_at('pre', self.start - timedelta(hours=1)).status_code, 200)
        self.assertEqual(self.submit_at('pre', self.start - timedelta(minutes=1)).status_code, 200)
        self.assertEqual(self.open_at('post', self.start).status_code, 200)

    def test_pre_and_post_are_immediately_available_in_order(self):
        self.begin_post()
        body = self.client.get('/api/assessment/schedule/').json()
        self.assertTrue(body['late_submission_allowed'])
        self.assertEqual(body['phases']['post']['wait_days'], 7)
        self.assertNotIn('withdrawal', body['available'])

    def test_early_submission_waits_until_exactly_seven_days_after_opening(self):
        self.begin_post()
        self.submit_at('post', self.start + timedelta(hours=3))
        before = self.start + timedelta(days=7) - timedelta(microseconds=1)
        self.assertEqual(self.open_at('transfer', before).status_code, 403)
        self.assertEqual(self.submit_at('transfer', before).status_code, 403)
        with patch('django.utils.timezone.now', return_value=before):
            self.assertEqual(self.client.post('/api/assessment/retake/', {'exam_type': 'transfer'}, format='json').status_code, 403)
            self.assertEqual(self.client.get('/api/assessment/items/?type=transfer&retake=1').status_code, 403)
        self.assertEqual(self.open_at('transfer', self.start + timedelta(days=7)).status_code, 200)

    def test_waiting_without_submitting_does_not_unlock_transfer(self):
        self.begin_post()
        self.assertEqual(self.open_at('transfer', self.start + timedelta(days=10)).status_code, 403)

    def test_late_submission_is_accepted_and_next_stage_opens_immediately(self):
        self.begin_post()
        late = self.start + timedelta(days=11)
        self.assertEqual(self.submit_at('post', late).status_code, 200)
        self.assertEqual(self.open_at('transfer', late).status_code, 200)

    def test_withdrawal_requires_fourteen_days_from_transfer_opening_and_submission(self):
        self.begin_post()
        self.submit_at('post', self.start + timedelta(days=1))
        transfer = self.start + timedelta(days=7)
        self.open_at('transfer', transfer)
        self.submit_at('transfer', transfer + timedelta(days=2))
        self.assertEqual(self.open_at('withdrawal', transfer + timedelta(days=14) - timedelta(seconds=1)).status_code, 403)
        self.assertEqual(self.open_at('withdrawal', transfer + timedelta(days=14)).status_code, 200)
        self.assertEqual(self.submit_at('withdrawal', transfer + timedelta(days=25)).status_code, 200)

    def test_retake_and_refetch_do_not_reset_first_open_anchor(self):
        self.begin_post()
        self.submit_at('post', self.start + timedelta(days=1))
        with patch('django.utils.timezone.now', return_value=self.start + timedelta(days=6)):
            self.assertEqual(self.client.post('/api/assessment/retake/', {'exam_type': 'post'}, format='json').status_code, 200)
        self.assertEqual(AssessmentTimeline.objects.get(student=self.user).post_started_at, self.start)
        self.assertEqual(self.open_at('transfer', self.start + timedelta(days=7)).status_code, 200)

    def test_teacher_can_review_all_forms_without_a_timeline(self):
        self.user.profile.role = 'EXPERT_TEACHER'
        self.user.profile.save()
        for exam in timing.ORDER:
            self.assertEqual(self.open_at(exam, self.start).status_code, 200)
        self.assertFalse(AssessmentTimeline.objects.exists())

    def test_teacher_receives_dates_paper_duration_and_complete_study_duration(self):
        self.begin_post()
        self.submit_at('post', self.start + timedelta(days=1))
        self.open_at('transfer', self.start + timedelta(days=7))
        self.submit_at('transfer', self.start + timedelta(days=8))
        self.open_at('withdrawal', self.start + timedelta(days=21))
        self.submit_at('withdrawal', self.start + timedelta(days=22))
        self.user.profile.role = 'EXPERT_TEACHER'
        self.user.profile.save()
        rows = self.client.get('/api/expert/submissions/').json()['submissions']
        row = next(r for r in rows if r['exam_type'] == 'post')
        self.assertEqual(row['timing']['paper_elapsed_days'], 1)
        self.assertAlmostEqual(row['timing']['study_elapsed_days'], 22 + 1/24, places=3)
        self.assertEqual(len(rows), 4)

    def test_legacy_scores_have_no_invented_opening_or_duration(self):
        sub = ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=20)
        report = timing.report(self.user, 'pre', sub.submitted_at)
        self.assertIsNone(report['opened_at'])
        self.assertIsNone(report['paper_elapsed_days'])

    def test_one_students_wait_does_not_change_anothers(self):
        self.begin_post()
        other = User.objects.create_user('another-student')
        ParticipantProfile.objects.create(user=other, consent_given=True)
        self.assertEqual(timing.status(other)['available'], ['pre'])

    def test_legacy_retake_cannot_restart_an_already_elapsed_wait(self):
        for exam in ('pre', 'post', 'transfer'):
            row = ExamSubmission.objects.create(student=self.user, exam_type=exam, score_pct=0)
            ExamSubmission.objects.filter(pk=row.pk).update(submitted_at=self.start)
        with patch('django.utils.timezone.now', return_value=self.start + timedelta(days=20)):
            self.client.post('/api/assessment/retake/', {'exam_type': 'transfer'}, format='json')
            self.assertIn('withdrawal', timing.status(self.user)['available'])

    def test_leaving_the_study_erases_the_new_timeline_too(self):
        from accounts.withdrawal import withdraw
        self.begin_post()
        self.assertTrue(AssessmentTimeline.objects.filter(student=self.user).exists())
        withdraw(self.user)
        self.assertFalse(AssessmentTimeline.objects.filter(student=self.user).exists())
