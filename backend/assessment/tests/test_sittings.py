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
