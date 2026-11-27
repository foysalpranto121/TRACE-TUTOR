"""Server-side protocol enforcement: no tutor during no-AI papers, one sitting per
paper, time-on-paper recorded, a manifest of the configuration, and a clean reset."""
import io
import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile
from assessment import analytics, sittings
from assessment.models import ExamSubmission, ExpertRating, PaperSitting
from logging_app.models import InteractionLog


def enrol(username, role='STUDENT', arm='REASONING_VISIBLE'):
    user = User.objects.create_user(username=username, password='Testpass!2345')
    ParticipantProfile.objects.create(user=user, role=role, assigned_arm=arm, enrolled_arm=arm, consent_given=True)
    return user, APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)


def submit(client, exam_type):
    return client.post('/api/assessment/submit/', {'exam_type': exam_type, 'answers': {}}, format='json')


@override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=False)
class SittingLifecycleTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu', arm='ANSWER_ONLY')

    def test_fetching_a_paper_opens_a_sitting_and_logs_it(self):
        body = self.client_.get('/api/assessment/items/?type=pre').json()
        self.assertEqual(body['sitting']['status'], 'open')
        self.assertTrue(body['sitting']['no_ai'])
        sitting = PaperSitting.objects.get(student=self.user, exam_type='pre')
        self.assertTrue(sitting.is_open)
        self.assertEqual(sitting.arm, 'ANSWER_ONLY')
        event = InteractionLog.objects.get(user=self.user, event_type='PAPER_OPENED')
        self.assertEqual(event.payload['exam_type'], 'pre')

    def test_refetching_is_idempotent_and_refreshes_activity(self):
        self.client_.get('/api/assessment/items/?type=pre')
        first = PaperSitting.objects.get(student=self.user, exam_type='pre')
        PaperSitting.objects.filter(pk=first.pk).update(last_opened_at=timezone.now() - timedelta(hours=9))
        self.client_.get('/api/assessment/items/?type=pre')
        self.assertEqual(PaperSitting.objects.filter(student=self.user).count(), 1)
        self.assertGreater(PaperSitting.objects.get(pk=first.pk).last_opened_at,
                           timezone.now() - timedelta(minutes=1))
        self.assertEqual(InteractionLog.objects.filter(event_type='PAPER_OPENED').count(), 1, 'logged once')

    def test_submitting_closes_the_sitting_and_links_the_submission(self):
        self.client_.get('/api/assessment/items/?type=pre')
        response = submit(self.client_, 'pre')
        sitting = PaperSitting.objects.get(student=self.user, exam_type='pre')
        self.assertFalse(sitting.is_open)
        self.assertEqual(sitting.submission_id, response.json()['submission_id'])

    def test_submitting_without_fetching_still_records_a_closed_sitting(self):
        submit(self.client_, 'pre')
        self.assertFalse(PaperSitting.objects.get(student=self.user, exam_type='pre').is_open)

    def test_a_paper_cannot_be_submitted_twice(self):
        first = submit(self.client_, 'pre')
        again = submit(self.client_, 'pre')
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()['submission_id'], first.json()['submission_id'])
        self.assertEqual(ExamSubmission.objects.count(), 1)

    def test_a_completed_paper_is_served_with_its_result_pointer(self):
        first = submit(self.client_, 'pre')
        body = self.client_.get('/api/assessment/items/?type=pre').json()
        self.assertEqual(body['sitting']['status'], 'completed')
        self.assertEqual(body['sitting']['submission_id'], first.json()['submission_id'])

    def test_retake_reopens_sitting_and_allows_subsequent_submission(self):
        first = submit(self.client_, 'pre')
        body = self.client_.post('/api/assessment/retake/', {'exam_type': 'pre'}, format='json').json()
        self.assertEqual(body['sitting']['status'], 'open')
        sitting = PaperSitting.objects.get(student=self.user, exam_type='pre')
        self.assertTrue(sitting.is_open)
        # Now submission of retake succeeds
        second = submit(self.client_, 'pre')
        self.assertIn(second.status_code, (200, 202))
        self.assertEqual(ExamSubmission.objects.count(), 2)
        # Double submission after retake is still blocked
        again = submit(self.client_, 'pre')
        self.assertEqual(again.status_code, 409)

    def test_get_items_with_retake_query_param_reopens_sitting(self):
        submit(self.client_, 'pre')
        body = self.client_.get('/api/assessment/items/?type=pre&retake=1').json()
        self.assertEqual(body['sitting']['status'], 'open')

    def test_staff_browsing_the_bank_get_no_sittings(self):
        _, teacher = enrol('tea', role='EXPERT_TEACHER')
        body = teacher.get('/api/assessment/items/?type=withdrawal').json()
        self.assertIsNone(body['sitting'])
        self.assertFalse(PaperSitting.objects.exists())

    def test_time_on_paper_reaches_the_export(self):
        self.client_.get('/api/assessment/items/?type=pre')
        PaperSitting.objects.filter(student=self.user).update(first_opened_at=timezone.now() - timedelta(minutes=23))
        submit(self.client_, 'pre')
        row = analytics.participant_rows()[0]
        self.assertAlmostEqual(row['pre_minutes'], 23, delta=0.5)
        self.assertIsNone(row['post_minutes'])


@override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=False)
class TutorGatingTests(ApiTestCase):
    """The pre-test and the withdrawal task are no-AI papers, enforced at the endpoint."""

    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu')
        for exam_type in ('pre', 'post', 'transfer'):
            ExamSubmission.objects.create(student=self.user, exam_type=exam_type, score_pct=50, answers={})
        # These fixtures have completed the new fourteen-day transfer wait.
        ExamSubmission.objects.filter(student=self.user, exam_type='transfer').update(
            submitted_at=timezone.now() - timedelta(days=15))

    def ask(self, client=None):
        return (client or self.client_).post('/api/tutor/query/', {'prompt': 'why?', 'problem_id': 'p1'}, format='json')

    def test_the_tutor_answers_when_no_paper_is_open(self):
        self.assertEqual(self.ask().status_code, 200)

    def test_the_tutor_refuses_while_the_withdrawal_task_is_open(self):
        self.client_.get('/api/assessment/items/?type=withdrawal')
        response = self.ask()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['reason'], 'paper_in_progress')
        self.assertEqual(response.json()['exam_type'], 'withdrawal')
        self.assertIn('withdrawal task', response.json()['error'])

    def test_the_tutor_refuses_while_the_pre_test_is_open(self):
        user, client = enrol('fresh')
        client.get('/api/assessment/items/?type=pre')
        response = self.ask(client)
        self.assertEqual(response.status_code, 403)
        self.assertIn('pre-test', response.json()['error'])

    def test_the_tutor_is_allowed_during_the_ai_papers(self):
        user, client = enrol('fresh')
        ExamSubmission.objects.create(student=user, exam_type='pre', score_pct=50, answers={})
        client.get('/api/assessment/items/?type=post')
        self.assertEqual(self.ask(client).status_code, 200)

    def test_a_newer_transfer_retake_is_not_blocked_by_a_stale_withdrawal_sitting(self):
        self.client_.get('/api/assessment/items/?type=withdrawal')
        response = self.client_.post(
            '/api/assessment/retake/', {'exam_type': 'transfer'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sittings.open_paper_of(self.user), 'transfer')
        self.assertEqual(self.ask().status_code, 200)

    def test_returning_to_withdrawal_restores_the_tutor_block(self):
        self.client_.get('/api/assessment/items/?type=withdrawal')
        self.client_.post('/api/assessment/retake/', {'exam_type': 'transfer'}, format='json')
        self.client_.get('/api/assessment/items/?type=withdrawal')
        response = self.ask()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['exam_type'], 'withdrawal')

        # Going back to the already-open Transfer retake refreshes that sitting even
        # though an older Transfer submission exists, and its tutor becomes available.
        self.client_.get('/api/assessment/items/?type=transfer')
        self.assertEqual(sittings.open_paper_of(self.user), 'transfer')
        self.assertEqual(self.ask().status_code, 200)

    def test_submitting_the_paper_frees_the_tutor(self):
        self.client_.get('/api/assessment/items/?type=withdrawal')
        self.assertEqual(self.ask().status_code, 403)
        submit(self.client_, 'withdrawal')
        self.assertEqual(self.ask().status_code, 200)

    def test_an_abandoned_paper_stops_blocking_after_the_ttl(self):
        self.client_.get('/api/assessment/items/?type=withdrawal')
        PaperSitting.objects.filter(student=self.user).update(last_opened_at=timezone.now() - timedelta(hours=5))
        self.assertEqual(self.ask().status_code, 200)

    def test_reopening_an_abandoned_paper_blocks_again(self):
        self.client_.get('/api/assessment/items/?type=withdrawal')
        PaperSitting.objects.filter(student=self.user).update(last_opened_at=timezone.now() - timedelta(hours=5))
        self.client_.get('/api/assessment/items/?type=withdrawal')
        self.assertEqual(self.ask().status_code, 403)

    def test_staff_are_never_blocked(self):
        _, teacher = enrol('tea', role='EXPERT_TEACHER')
        teacher.get('/api/assessment/items/?type=withdrawal')
        self.assertEqual(self.ask(teacher).status_code, 200)

    @override_settings(NO_AI_PAPERS=('withdrawal',))
    def test_the_set_of_no_ai_papers_is_configurable(self):
        user, client = enrol('fresh')
        client.get('/api/assessment/items/?type=pre')
        self.assertEqual(self.ask(client).status_code, 200)


class EffectiveCompletionTests(ApiTestCase):
    """Submission receipts settle stale sittings without rewriting study history."""

    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('effective-completion')
        self.now = timezone.now()
        for name, options in (
                ('tutor.views.rag_engine_instance.retrieve', {'return_value': []}),
                ('tutor.views.llm.generate_json', {'side_effect': RuntimeError('No provider calls in this test')})):
            mocked = patch(name, **options)
            mocked.start()
            self.addCleanup(mocked.stop)

    def stale_attempt(self, exam_type='pre', grading_status=ExamSubmission.GRADED):
        with patch('django.utils.timezone.now', return_value=self.now - timedelta(hours=1)):
            sitting = sittings.open_paper(self.user, exam_type)
        with patch('django.utils.timezone.now', return_value=self.now - timedelta(minutes=30)):
            receipt = ExamSubmission.objects.create(
                student=self.user, exam_type=exam_type, score_pct=50, grading_status=grading_status)
        return sitting, receipt

    def complete_all_forms(self):
        for exam_type in ('pre', 'post', 'transfer', 'withdrawal'):
            self.stale_attempt(exam_type)

    def tutor_status(self):
        response = self.client_.post('/api/tutor/query/', {'prompt': 'Explain variables'}, format='json')
        return response.status_code

    def availability(self):
        response = self.client_.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        return response.json()['tutor_availability']

    def test_missing_sitting_uses_existing_submission_without_inventing_an_opening(self):
        receipt = ExamSubmission.objects.create(student=self.user, exam_type='pre', score_pct=50)
        body = self.client_.get('/api/assessment/items/?type=pre').json()
        self.assertEqual(body['sitting']['status'], sittings.COMPLETED)
        self.assertEqual(body['sitting']['submission_id'], receipt.pk)
        self.assertEqual(body['sitting']['submitted_at'], receipt.submitted_at.isoformat())
        self.assertIsNone(body['sitting']['first_opened_at'])
        self.assertFalse(PaperSitting.objects.filter(student=self.user).exists())
        self.assertTrue(self.availability()['available'])
        self.assertEqual(self.tutor_status(), 200)

    def test_new_unsubmitted_paper_is_still_locked(self):
        body = self.client_.get('/api/assessment/items/?type=pre').json()
        self.assertEqual(body['sitting']['status'], sittings.OPEN)
        self.assertTrue(sittings.is_paper_open(self.user, 'pre'))
        self.assertEqual(self.availability()['exam_type'], 'pre')
        self.assertEqual(self.tutor_status(), 403)

    def test_stale_open_flag_yields_completed_result_and_never_refreshes_activity(self):
        sitting, receipt = self.stale_attempt()
        before = PaperSitting.objects.filter(pk=sitting.pk).values().get()
        events = InteractionLog.objects.filter(user=self.user, event_type='PAPER_OPENED').count()
        body = self.client_.get('/api/assessment/items/?type=pre').json()
        self.assertEqual(body['sitting']['status'], sittings.COMPLETED)
        self.assertEqual(body['sitting']['submission_id'], receipt.pk)
        self.assertEqual(body['sitting']['submitted_at'], receipt.submitted_at.isoformat())
        self.assertEqual(PaperSitting.objects.filter(pk=sitting.pk).values().get(), before)
        self.assertEqual(InteractionLog.objects.filter(user=self.user, event_type='PAPER_OPENED').count(), events)
        self.assertFalse(sittings.is_paper_open(self.user, 'pre'))
        self.assertIsNone(sittings.blocking_paper(self.user))
        self.assertTrue(self.availability()['available'])
        self.assertEqual(self.tutor_status(), 200)

    def test_pending_grading_already_completes_the_attempt(self):
        sitting, receipt = self.stale_attempt(grading_status=ExamSubmission.PENDING)
        self.assertFalse(sittings.is_paper_open(self.user, 'pre'))
        self.assertEqual(sittings.describe(self.user, 'pre')['submission_id'], receipt.pk)
        self.assertTrue(self.availability()['available'])
        sitting.refresh_from_db()
        self.assertIsNone(sitting.submitted_at)
        self.assertIsNone(sitting.submission_id)

    def test_all_submitted_forms_ignore_stale_open_flags_and_allow_mode_switching(self):
        self.complete_all_forms()
        self.assertTrue(self.client_.get('/api/accounts/me/').json()['arm_self_select'])
        for exam_type in ('pre', 'post', 'transfer', 'withdrawal'):
            body = self.client_.get(f'/api/assessment/items/?type={exam_type}').json()
            self.assertEqual(body['sitting']['status'], sittings.COMPLETED)
            self.assertIsNotNone(body['sitting']['submission_id'])
        self.assertTrue(self.availability()['available'])
        self.assertEqual(self.tutor_status(), 200)
        self.assertEqual(PaperSitting.objects.filter(student=self.user, submitted_at__isnull=True).count(), 4,
                         'Historical sitting flags must not be rewritten by these reads')

    def test_a_completed_sitting_keeps_its_recorded_result(self):
        sitting, receipt = self.stale_attempt()
        sittings.close_paper(self.user, 'pre', receipt)
        before = PaperSitting.objects.filter(pk=sitting.pk).values().get()
        result = sittings.describe(self.user, 'pre')
        self.assertEqual(result['status'], sittings.COMPLETED)
        self.assertEqual(result['submission_id'], receipt.pk)
        self.assertEqual(PaperSitting.objects.filter(pk=sitting.pk).values().get(), before)

    def test_equal_submission_and_opening_timestamp_counts_as_submitted(self):
        sitting, receipt = self.stale_attempt()
        ExamSubmission.objects.filter(pk=receipt.pk).update(submitted_at=sitting.first_opened_at)
        self.assertFalse(sittings.is_paper_open(self.user, 'pre'))
        self.assertIsNone(sittings.open_paper_of(self.user))
        self.assertEqual(sittings.describe(self.user, 'pre')['status'], sittings.COMPLETED)

    def test_real_pre_and_withdrawal_retakes_remain_locked_until_new_submission(self):
        self.complete_all_forms()
        for exam_type in ('pre', 'withdrawal'):
            with self.subTest(exam_type=exam_type):
                response = self.client_.post('/api/assessment/retake/', {'exam_type': exam_type}, format='json')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['sitting']['status'], sittings.OPEN)
                self.assertIsNone(response.json()['sitting']['submission_id'])
                self.assertTrue(sittings.is_paper_open(self.user, exam_type))
                self.assertEqual(self.availability()['exam_type'], exam_type)
                self.assertEqual(self.tutor_status(), 403)
                body = self.client_.get(f'/api/assessment/items/?type={exam_type}').json()
                self.assertEqual(body['sitting']['status'], sittings.OPEN)
                self.assertEqual(self.tutor_status(), 403)
                receipt = ExamSubmission.objects.create(student=self.user, exam_type=exam_type, score_pct=50)
                self.assertFalse(sittings.is_paper_open(self.user, exam_type))
                self.assertEqual(sittings.describe(self.user, exam_type)['submission_id'], receipt.pk)
                self.assertTrue(self.availability()['available'])
                self.assertEqual(self.tutor_status(), 200)

    def test_stale_open_attempt_cannot_be_submitted_again_without_retake(self):
        _, receipt = self.stale_attempt()
        response = submit(self.client_, 'pre')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['submission_id'], receipt.pk)
        self.assertEqual(ExamSubmission.objects.filter(student=self.user, exam_type='pre').count(), 1)

    def test_other_student_or_other_form_receipt_does_not_unlock_unfinished_pre(self):
        sittings.open_paper(self.user, 'pre')
        other, _ = enrol('other-receipt-student')
        ExamSubmission.objects.create(student=other, exam_type='pre', score_pct=50)
        ExamSubmission.objects.create(student=self.user, exam_type='post', score_pct=50)
        self.assertTrue(sittings.is_paper_open(self.user, 'pre'))
        self.assertEqual(self.availability()['exam_type'], 'pre')
        self.assertEqual(self.tutor_status(), 403)

    def test_completed_newest_flag_does_not_mask_an_unfinished_older_no_ai_paper(self):
        sitting, _ = self.stale_attempt('pre')
        with patch('django.utils.timezone.now', return_value=self.now - timedelta(minutes=45)):
            unfinished = sittings.open_paper(self.user, 'withdrawal')
        PaperSitting.objects.filter(pk=sitting.pk).update(last_opened_at=self.now)
        self.assertEqual(sittings.open_paper_of(self.user), 'withdrawal')
        self.assertEqual(sittings.blocking_paper(self.user), 'withdrawal')
        PaperSitting.objects.filter(pk=unfinished.pk).update(last_opened_at=self.now - timedelta(hours=5))
        self.assertIsNone(sittings.blocking_paper(self.user), 'The original activity TTL still applies')

    def test_effective_open_queries_remain_one_query_each(self):
        self.complete_all_forms()
        with self.assertNumQueries(1):
            self.assertFalse(sittings.is_paper_open(self.user, 'pre'))
        with self.assertNumQueries(1):
            self.assertIsNone(sittings.open_paper_of(self.user))


class ManifestTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        _, self.student = enrol('stu')
        _, self.teacher = enrol('tea', role='EXPERT_TEACHER')
        _, self.boss = enrol('boss', role='RESEARCHER_ADMIN')

    def test_only_a_researcher_may_read_it(self):
        self.assertEqual(self.student.get('/api/admin/manifest/').status_code, 403)
        self.assertEqual(self.teacher.get('/api/admin/manifest/').status_code, 403)
        self.assertEqual(self.boss.get('/api/admin/manifest/').status_code, 200)

    def test_it_records_everything_that_could_change_the_data(self):
        body = self.boss.get('/api/admin/manifest/').json()
        self.assertEqual(body['tutor']['temperature'], 0.0)
        self.assertIsInstance(body['tutor']['model_chain'], list)
        self.assertEqual(body['protocol']['arm_switch_policy'], 'after_protocol')
        self.assertEqual(body['protocol']['no_ai_papers'], ['pre', 'withdrawal'])
        self.assertEqual(len(body['item_bank']['sha256']), 64)
        self.assertEqual(body['item_bank']['items'], 60)
        self.assertIn('Django', body['versions'])
        self.assertIn('sandbox_tier', body['execution'])

    def test_it_is_offered_as_a_download(self):
        response = self.boss.get('/api/admin/manifest/')
        self.assertIn('attachment; filename="trace_tutor_manifest_', response['Content-Disposition'])


class ResetStudyDataTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.student, client = enrol('stu')
        self.teacher, _ = enrol('tea', role='EXPERT_TEACHER')
        sub = ExamSubmission.objects.create(student=self.student, exam_type='pre', score_pct=50, answers={})
        PaperSitting.objects.create(student=self.student, exam_type='pre', submitted_at=timezone.now(), submission=sub)
        InteractionLog.objects.create(user=self.student, event_type='HELP_REQUEST', payload={})
        InteractionLog.objects.create(user=self.teacher, event_type='LOGIN', payload={})
        ExpertRating.objects.create(expert_user=self.teacher, item_key='pre_mcq_01', alignment_score=4)

    def run_command(self, *args):
        out = io.StringIO()
        call_command('reset_study_data', *args, stdout=out)
        return out.getvalue()

    def test_without_yes_it_only_reports(self):
        output = self.run_command()
        self.assertIn('Nothing deleted', output)
        self.assertTrue(ExamSubmission.objects.exists())
        self.assertTrue(User.objects.filter(username='stu').exists())

    def test_with_yes_it_wipes_participants_and_keeps_staff_and_ratings(self):
        self.run_command('--yes')
        self.assertFalse(User.objects.filter(username='stu').exists())
        self.assertFalse(ExamSubmission.objects.exists())
        self.assertFalse(PaperSitting.objects.exists())
        self.assertFalse(InteractionLog.objects.filter(user=self.student).exists())
        self.assertTrue(User.objects.filter(username='tea').exists())
        self.assertTrue(InteractionLog.objects.filter(user=self.teacher).exists())
        self.assertEqual(ExpertRating.objects.count(), 1, 'expert ratings are not participant data')


class BackupCommandTests(TestCase):
    """A backup that cannot be restored is not a backup. The command dumps the database and
    the file stores, writes a manifest of row counts, and --verify proves the dump restores
    into a scratch database with the same counts."""

    def setUp(self):
        from assessment.management.commands.backup_study import pg_tool
        try:
            pg_tool('pg_dump')
        except Exception as e:
            self.skipTest(f'PostgreSQL client tools not available: {e}')
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_take_list_verify_and_prune(self):
        from io import StringIO
        from django.core.management import call_command
        User.objects.create_user('someone', password='Testpass!2345')
        with override_settings(BACKUP_DIR=Path(self.tmp), BACKUP_KEEP=1):
            out = StringIO()
            first = call_command('backup_study', '--no-files', stdout=out)
            manifest = json.loads((Path(first) / 'manifest.json').read_text(encoding='utf-8'))
            self.assertIn('accounts_participantprofile', manifest['row_counts'])
            self.assertTrue((Path(first) / 'db.dump').stat().st_size > 0)
            self.assertIn('study_manifest', manifest)

            listed = StringIO()
            call_command('backup_study', '--list', stdout=listed)
            self.assertIn(Path(first).name, listed.getvalue())
            self.assertIn('unverified', listed.getvalue())

            verified = StringIO()
            call_command('backup_study', '--verify', stdout=verified)
            self.assertIn('restores cleanly', verified.getvalue())
            manifest = json.loads((Path(first) / 'manifest.json').read_text(encoding='utf-8'))
            self.assertIn('verified_at', manifest)

            # A second backup with --keep 1 prunes the first.
            second = call_command('backup_study', '--no-files', stdout=StringIO())
            self.assertFalse(Path(first).exists())
            self.assertTrue(Path(second).exists())
