"""Background grading: nothing is lost, exactly one grader wins, failures are visible.

Most API tests run with GRADING_INLINE=True (trace_backend/test_utils.py) so a submit
returns its score in the same response. The asynchronous path - the one a real cohort
uses - is exercised here on TransactionTestCase, because a background thread grades on
its own database connection and cannot see rows inside an uncommitted test transaction.
"""
import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile
from assessment import grading, scoring
from assessment.models import ExamSubmission


def enrol(username, role='STUDENT'):
    user = User.objects.create_user(username=username, password='Testpass!2345')
    ParticipantProfile.objects.create(user=user, role=role, consent_given=True)
    return user, APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)


def mcq_answers(exam_type='pre'):
    """Answer every MCQ with option 'a' and leave code items blank: grading then needs no
    compiler, which keeps these tests fast and toolchain-independent."""
    return {i['id']: 'a' for i in scoring.items_for(exam_type) if i.get('type') == 'concept_mcq'}


def pending_row(user, exam_type='pre'):
    return ExamSubmission.objects.create(
        student=user, exam_type=exam_type, score_pct=None,
        grading_status=ExamSubmission.PENDING,
        answers={'answers': mcq_answers(exam_type), 'code_answers': {}, 'chapter': None})


def wait_until(predicate, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


class ClaimTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, _ = enrol('stu')

    def test_exactly_one_grader_wins_a_pending_row(self):
        row = pending_row(self.user)
        self.assertTrue(grading.claim(row.pk))
        self.assertFalse(grading.claim(row.pk), 'a second claim must lose')
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.GRADING)

    def test_a_graded_row_cannot_be_claimed_again(self):
        row = ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=40,
                                            answers={})
        self.assertFalse(grading.claim(row.pk))

    def test_grade_now_grades_a_pending_row_and_declines_a_taken_one(self):
        row = pending_row(self.user)
        self.assertTrue(grading.grade_now(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.GRADED)
        self.assertIsNotNone(row.score_pct)
        self.assertIsNotNone(row.graded_at)
        self.assertFalse(grading.grade_now(row.pk), 'already graded: nothing to do')


class GradeOutcomeTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, _ = enrol('stu')

    def test_grading_fills_in_score_and_per_item_results(self):
        row = pending_row(self.user)
        grading.grade_now(row.pk)
        row.refresh_from_db()
        results = row.answers['results']
        self.assertEqual(len(results), len(scoring.items_for('pre')))
        self.assertEqual(row.score_pct, round(sum(r['correct'] for r in results) * 100 / len(results)))

    def test_a_grading_crash_is_recorded_on_the_row_not_raised(self):
        row = pending_row(self.user)
        with patch('assessment.grading.scoring.grade_submission', side_effect=RuntimeError('compiler exploded')):
            self.assertFalse(grading.grade_now(row.pk))   # must not raise
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.FAILED)
        self.assertIn('compiler exploded', row.grading_error)
        self.assertIsNone(row.score_pct)
        self.assertEqual(row.answers['answers'], mcq_answers(), 'the answers must survive the failure')

    def test_failed_rows_can_be_requeued_and_then_grade(self):
        row = pending_row(self.user)
        with patch('assessment.grading.scoring.grade_submission', side_effect=RuntimeError('boom')):
            grading.grade_now(row.pk)
        self.assertEqual(grading.retry_failed(), 1)
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.PENDING)
        self.assertEqual(row.grading_error, '')
        self.assertEqual(grading.grade_pending(), 1)
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.GRADED)

    def test_grade_pending_drains_oldest_first_and_reports_the_count(self):
        rows = [pending_row(self.user) for _ in range(3)]
        self.assertEqual(grading.grade_pending(), 3)
        self.assertTrue(all(ExamSubmission.objects.get(pk=r.pk).is_graded for r in rows))
        self.assertEqual(grading.grade_pending(), 0)

class StaleGradingTests(ApiTestCase):
    """A grader that dies between claim and persist leaves its row in 'grading' forever;
    the next sweep must reclaim it so the participant's result is not lost."""

    def setUp(self):
        super().setUp()
        self.user, _ = enrol('stu')

    def test_a_row_stuck_in_grading_is_requeued_and_then_grades(self):
        row = pending_row(self.user)
        self.assertTrue(grading.claim(row.pk))       # -> GRADING, claimed_at = now
        ExamSubmission.objects.filter(pk=row.pk).update(
            claimed_at=timezone.now() - timedelta(minutes=30))
        self.assertEqual(grading.requeue_stale(), 1)
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.PENDING)
        self.assertEqual(grading.grade_pending(), 1)
        self.assertTrue(ExamSubmission.objects.get(pk=row.pk).is_graded)

    def test_a_freshly_claimed_row_is_left_alone(self):
        row = pending_row(self.user)
        grading.claim(row.pk)
        self.assertEqual(grading.requeue_stale(), 0)
        self.assertEqual(ExamSubmission.objects.get(pk=row.pk).grading_status, ExamSubmission.GRADING)

    def test_grade_pending_reclaims_a_stranded_row_on_its_own(self):
        row = pending_row(self.user)
        grading.claim(row.pk)
        ExamSubmission.objects.filter(pk=row.pk).update(
            claimed_at=timezone.now() - timedelta(minutes=30))
        self.assertEqual(grading.grade_pending(), 1, 'the sweep requeues then grades it')
        self.assertTrue(ExamSubmission.objects.get(pk=row.pk).is_graded)

    def test_a_grading_unavailable_error_marks_the_row_failed_and_is_retryable(self):
        row = pending_row(self.user)
        with patch('assessment.grading.scoring.grade_submission',
                   side_effect=scoring.GradingUnavailable('runner down')):
            self.assertFalse(grading.grade_now(row.pk))
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.FAILED)
        self.assertIn('runner down', row.grading_error)
        self.assertEqual(grading.retry_failed(), 1)


class RepresentationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, _ = enrol('stu')

    def test_a_pending_row_exposes_no_score_and_no_results(self):
        rep = grading.representation(pending_row(self.user))
        self.assertEqual(rep['grading_status'], 'pending')
        self.assertIsNone(rep['score_pct'])
        self.assertIsNone(rep['correct'])
        self.assertEqual(rep['results'], [])

    def test_a_graded_row_exposes_everything_the_result_screen_needs(self):
        row = pending_row(self.user)
        grading.grade_now(row.pk)
        row.refresh_from_db()
        rep = grading.representation(row)
        self.assertEqual(rep['grading_status'], 'graded')
        for key in ('submission_id', 'score_pct', 'correct', 'total', 'results', 'graded_at'):
            self.assertIsNotNone(rep[key], key)
        self.assertEqual(rep['total'], len(rep['results']))


class SubmitEndpointTests(ApiTestCase):
    """GRADING_INLINE is on here, so the score comes back in the same response."""

    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu')

    def submit(self):
        return self.client_.post('/api/assessment/submit/',
                                 {'exam_type': 'pre', 'answers': mcq_answers(), 'code_answers': {}},
                                 format='json')

    def test_a_submission_is_saved_and_graded(self):
        response = self.submit()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['grading_status'], 'graded')
        self.assertIsNotNone(body['score_pct'])
        self.assertEqual(ExamSubmission.objects.get().grading_status, ExamSubmission.GRADED)

    def test_the_exam_is_saved_even_when_grading_crashes(self):
        """The single most important property of the new flow."""
        with patch('assessment.grading.scoring.grade_submission', side_effect=RuntimeError('toolchain down')):
            response = self.submit()
        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body['grading_status'], 'failed')
        self.assertIn('toolchain down', body['error'])
        row = ExamSubmission.objects.get()
        self.assertEqual(row.answers['answers'], mcq_answers(), 'answers persisted before grading ran')

    def test_the_body_cannot_smuggle_in_a_score(self):
        response = self.client_.post('/api/assessment/submit/',
                                     {'exam_type': 'pre', 'answers': {}, 'code_answers': {},
                                      'score_pct': 100, 'grading_status': 'graded'},
                                     format='json')
        self.assertEqual(response.json()['score_pct'], 0)


class SubmissionPollTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.owner, self.owner_c = enrol('owner')
        self.other, self.other_c = enrol('other')
        _, self.staff_c = enrol('tea', role='EXPERT_TEACHER')
        self.row = pending_row(self.owner)

    def test_the_owner_can_poll_their_submission(self):
        response = self.owner_c.get(f'/api/assessment/submissions/{self.row.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['grading_status'], 'pending')

    def test_another_participant_cannot_read_it(self):
        """Ids are sequential; without this check any participant could read anyone's marks."""
        self.assertEqual(self.other_c.get(f'/api/assessment/submissions/{self.row.pk}/').status_code, 404)

    def test_staff_can_read_it(self):
        self.assertEqual(self.staff_c.get(f'/api/assessment/submissions/{self.row.pk}/').status_code, 200)

    def test_an_unknown_id_and_an_anonymous_caller_get_nothing(self):
        self.assertEqual(self.owner_c.get('/api/assessment/submissions/999999/').status_code, 404)
        self.assertIn(APIClient().get(f'/api/assessment/submissions/{self.row.pk}/').status_code, (401, 403))


class QueuedRowsAreNotYetObservationsTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu')

    def test_a_pending_submission_still_unlocks_the_next_paper(self):
        """The paper was sat; the participant must not be able to sit it again."""
        pending_row(self.user)
        available = self.client_.get('/api/assessment/items/?type=post').json()['available']
        self.assertEqual(available, ['pre', 'post'])

    def test_a_pending_submission_carries_no_score_into_the_dashboard(self):
        pending_row(self.user)
        body = self.client_.get('/api/dashboard/').json()
        self.assertEqual(body['assessments'], {})

    def test_a_pending_submission_is_not_counted_by_the_analytics(self):
        from assessment import analytics
        pending_row(self.user)
        self.assertIsNone(analytics.participant_rows()[0]['pre'])


@override_settings(GRADING_INLINE=False, GRADING_MODE='worker')
class WorkerModeTests(ApiTestCase):
    """With a dedicated grading process, the web process must only queue."""

    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu')

    def test_enqueue_spawns_no_thread_and_leaves_the_row_pending(self):
        row = pending_row(self.user)
        with patch('assessment.grading.threading.Thread') as thread:
            self.assertFalse(grading.enqueue(row.pk))
        thread.assert_not_called()
        row.refresh_from_db()
        self.assertEqual(row.grading_status, ExamSubmission.PENDING)

    def test_submit_returns_202_pending_for_the_worker_to_pick_up(self):
        response = self.client_.post('/api/assessment/submit/',
                                     {'exam_type': 'pre', 'answers': mcq_answers(), 'code_answers': {}},
                                     format='json')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['grading_status'], 'pending')
        # ...and the worker command then grades it.
        call_command('grade_submissions', '--once', verbosity=0)
        self.assertTrue(ExamSubmission.objects.get().is_graded)


@override_settings(GRADING_INLINE=False)
class BackgroundGradingTests(TransactionTestCase):
    """The real path: submit returns at once, a thread grades, the client polls."""

    def setUp(self):
        super().setUp()
        for alias in ('default', 'persistent'):
            caches[alias].clear()
        self.user, self.client_ = enrol('stu')

    def test_submit_returns_immediately_and_grading_completes_in_the_background(self):
        response = self.client_.post('/api/assessment/submit/',
                                     {'exam_type': 'pre', 'answers': mcq_answers(), 'code_answers': {}},
                                     format='json')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['grading_status'], 'pending')
        submission_id = response.json()['submission_id']

        self.assertTrue(wait_until(
            lambda: ExamSubmission.objects.get(pk=submission_id).is_graded),
            'background grading did not complete')

        body = self.client_.get(f'/api/assessment/submissions/{submission_id}/').json()
        self.assertEqual(body['grading_status'], 'graded')
        self.assertIsNotNone(body['score_pct'])
        self.assertEqual(len(body['results']), len(scoring.items_for('pre')))

    def test_a_finished_worker_thread_releases_its_database_connection(self):
        """Each thread opens its own connection. close_old_connections() would keep it
        alive for CONN_MAX_AGE after the thread is gone; a cohort of 60 leaked 52 idle
        Postgres sessions that way. The thread must close unconditionally."""
        row = pending_row(self.user)
        with patch('assessment.grading.connections.close_all') as close_all:
            grading._worker(row.pk)
        close_all.assert_called_once()
        self.assertTrue(ExamSubmission.objects.get(pk=row.pk).is_graded)

    def test_the_connection_is_released_even_when_grading_crashes(self):
        row = pending_row(self.user)
        with patch('assessment.grading.grade_now', side_effect=RuntimeError('boom')), \
             patch('assessment.grading.connections.close_all') as close_all:
            grading._worker(row.pk)   # must not raise
        close_all.assert_called_once()

    @unittest.skipIf(connection.vendor == 'sqlite',
                     "SQLite's in-memory test database raises 'database table is locked' "
                     "under concurrent writers; the pool is exercised on PostgreSQL, which "
                     "is the engine a live cohort must run on anyway")
    def test_the_worker_command_drains_the_queue_in_parallel(self):
        """The command grades several submissions side by side on pool threads, each on
        its own database connection - which is why this lives on TransactionTestCase:
        those threads cannot see rows inside an uncommitted test transaction."""
        for _ in range(4):
            pending_row(self.user)
        call_command('grade_submissions', '--once', verbosity=0)
        self.assertEqual(ExamSubmission.objects.filter(grading_status=ExamSubmission.GRADED).count(), 4)
        self.assertFalse(ExamSubmission.objects.filter(grading_status=ExamSubmission.PENDING).exists())

    @unittest.skipIf(connection.vendor == 'sqlite', 'concurrent writers need PostgreSQL (see above)')
    def test_a_parallel_sweep_grades_every_row_exactly_once(self):
        rows = [pending_row(self.user) for _ in range(6)]
        self.assertEqual(grading.grade_pending(workers=4), 6)
        self.assertTrue(all(ExamSubmission.objects.get(pk=r.pk).is_graded for r in rows))
        self.assertEqual(grading.grade_pending(workers=4), 0, 'nothing left to claim')

    def test_a_row_left_pending_is_picked_up_by_the_next_enqueue(self):
        """Simulates a restart mid-queue: the orphan is drained alongside the new one."""
        orphan = pending_row(self.user)
        fresh = pending_row(self.user)
        grading.enqueue(fresh.pk)
        self.assertTrue(wait_until(
            lambda: all(ExamSubmission.objects.get(pk=pk).is_graded for pk in (orphan.pk, fresh.pk))),
            'the orphaned pending row was not drained')
