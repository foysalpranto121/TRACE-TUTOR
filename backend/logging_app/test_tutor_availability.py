"""Dashboard tutor eligibility must mirror the tutor gate, even on a cache hit."""
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from assessment import sittings
from assessment.models import ExamSubmission, PaperSitting
from logging_app.tests import enrol
from trace_backend.test_utils import ApiTestCase


class TutorAvailabilityTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('availability-student')

    def status(self):
        response = self.client_.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        return response.json()['tutor_availability'], response['X-Trace-Cache']

    def test_no_active_paper_allows_tutor_and_does_not_open_a_sitting(self):
        self.assertEqual(self.status()[0], {'available': True, 'reason': None, 'exam_type': None})
        self.assertFalse(PaperSitting.objects.filter(student=self.user).exists())

    def test_unsubmitted_pre_test_is_locked_and_matches_tutor_rejection(self):
        sittings.open_paper(self.user, 'pre')
        status, _ = self.status()
        self.assertEqual(status, {'available': False, 'reason': 'paper_in_progress', 'exam_type': 'pre'})
        response = self.client_.post('/api/tutor/query/', {'prompt': 'Explain loops'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['reason'], status['reason'])
        self.assertEqual(response.json()['exam_type'], status['exam_type'])

    def test_completed_submission_unlocks_before_grading_finishes_on_cache_hit(self):
        sittings.open_paper(self.user, 'pre')
        self.assertFalse(self.status()[0]['available'])
        submission = ExamSubmission.objects.create(student=self.user, exam_type='pre', grading_status='pending')
        self.status()  # Cache progress while the sitting is still open.
        sittings.close_paper(self.user, 'pre', submission)
        status, cache = self.status()
        self.assertEqual(cache, 'hit')
        self.assertTrue(status['available'])

    @override_settings(PAPER_SITTING_TTL_HOURS=4)
    def test_ttl_expiry_is_recomputed_on_cache_hit(self):
        sittings.open_paper(self.user, 'pre')
        self.assertFalse(self.status()[0]['available'])
        PaperSitting.objects.filter(student=self.user).update(last_opened_at=timezone.now() - timedelta(hours=5))
        status, cache = self.status()
        self.assertEqual(cache, 'hit')
        self.assertTrue(status['available'])

    def test_newest_paper_and_withdrawal_use_the_existing_policy(self):
        sittings.open_paper(self.user, 'pre')
        sittings.open_paper(self.user, 'post')
        self.assertTrue(self.status()[0]['available'])
        sittings.open_paper(self.user, 'withdrawal')
        self.assertEqual(self.status()[0]['exam_type'], 'withdrawal')

    def test_status_is_scoped_to_authenticated_caller(self):
        other, _ = enrol('other-availability-student')
        sittings.open_paper(other, 'pre')
        self.assertTrue(self.status()[0]['available'])
