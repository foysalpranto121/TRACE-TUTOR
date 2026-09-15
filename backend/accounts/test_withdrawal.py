"""Leaving the study erases what we hold - and only a participant can be withdrawn."""
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts import withdrawal
from accounts.models import ParticipantProfile
from assessment import analytics
from assessment.models import ExamSubmission, ExpertGrade
from logging_app.models import InteractionLog

STRONG = 'Str0ng-Pass-2026'


def enrol(username, role='STUDENT', **fields):
    user = User.objects.create_user(username=username, password=STRONG, email=f'{username}@example.com',
                                    first_name='Real Name')
    profile = ParticipantProfile.objects.create(
        user=user, role=role, consent_given=True, full_name='Real Name', phone='01700000000',
        school_name='Dhaka College', district='Dhaka', age=17, languages_known=['bn', 'en'], **fields)
    client = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)
    return user, profile, client


def generate_data(user):
    for event in ('LOGIN', 'HELP_REQUEST', 'CODE_RESULT'):
        InteractionLog.objects.create(user=user, event_type=event, payload={'prompt': 'secret question'})
    sub = ExamSubmission.objects.create(student=user, exam_type='pre', score_pct=55, answers={'answers': {'q1': 'a'}})
    grader = User.objects.create_user(username=f'grader-for-{user.pk}', password=STRONG)
    ExpertGrade.objects.create(submission=sub, expert_user=grader, assigned_marks=60)
    return sub


class ErasureTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.profile, self.client_ = enrol('alice')
        self.profile.avatar.save('u.webp', ContentFile(b'not really an image'), save=True)
        self.submission = generate_data(self.user)
        self.code = self.profile.participant_code

    def test_everything_the_participant_generated_is_deleted(self):
        withdrawal.withdraw(self.user)
        self.assertFalse(InteractionLog.objects.filter(user=self.user).exists())
        self.assertFalse(ExamSubmission.objects.filter(student=self.user).exists())
        self.assertFalse(ExpertGrade.objects.filter(submission=self.submission).exists(),
                         'expert grades hang off the submission and must go with it')

    def test_every_personal_field_is_blanked(self):
        withdrawal.withdraw(self.user)
        self.profile.refresh_from_db()
        for field in ('full_name', 'phone', 'school_name', 'district', 'grade', 'prior_experience'):
            self.assertEqual(getattr(self.profile, field), '', field)
        self.assertIsNone(self.profile.age)
        self.assertEqual(self.profile.languages_known, [])
        self.assertFalse(self.profile.avatar, 'the avatar file must be removed')
        self.assertFalse(self.profile.consent_given)

    def test_the_account_is_retired_not_deleted(self):
        withdrawal.withdraw(self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, f'withdrawn-{self.user.pk}')
        self.assertEqual(self.user.email, '')
        self.assertEqual(self.user.first_name, '')
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_the_pseudonymous_code_and_arm_survive_for_the_denominator(self):
        arm = self.profile.assigned_arm
        withdrawal.withdraw(self.user, by=withdrawal.RESEARCHER)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.participant_code, self.code)
        self.assertEqual(self.profile.assigned_arm, arm)
        self.assertIsNotNone(self.profile.withdrawn_at)
        self.assertEqual(self.profile.withdrawn_by, 'researcher')

    def test_withdrawing_twice_is_harmless(self):
        first = withdrawal.withdraw(self.user).withdrawn_at
        second = withdrawal.withdraw(self.user).withdrawn_at
        self.assertEqual(first, second)

    def test_staff_accounts_cannot_be_withdrawn(self):
        teacher, _, _ = enrol('tea', role='EXPERT_TEACHER')
        with self.assertRaises(withdrawal.NotAParticipant):
            withdrawal.withdraw(teacher)

    def test_the_export_shows_a_withdrawn_row_of_nulls(self):
        withdrawal.withdraw(self.user)
        row = next(r for r in analytics.participant_rows() if r['participant_code'] == self.code)
        self.assertTrue(row['withdrawn'])
        self.assertIsNone(row['pre'])
        self.assertEqual(row['help_requests'], 0)
        self.assertEqual(row['grade'], '')
        stats = analytics.study_stats()
        self.assertEqual(stats['total_participants'], 1)
        self.assertEqual(stats['withdrawn_participants'], 1)


class SelfWithdrawalEndpointTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.profile, self.client_ = enrol('alice')
        generate_data(self.user)

    def test_requires_the_correct_password(self):
        response = self.client_.post('/api/accounts/withdraw/', {'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.json()['fields'])
        self.assertTrue(InteractionLog.objects.filter(user=self.user).exists(), 'nothing erased')

    def test_withdraws_erases_and_signs_the_participant_out(self):
        response = self.client_.post('/api/accounts/withdraw/', {'password': STRONG}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'withdrawn')
        self.assertEqual(response.json()['participant_code'], self.profile.participant_code)
        self.assertFalse(InteractionLog.objects.filter(user=self.user).exists())
        # The token was revoked with the request; the same client is now nobody.
        self.assertIn(self.client_.get('/api/accounts/me/').status_code, (401, 403))

    def test_a_withdrawn_account_cannot_log_back_in(self):
        self.client_.post('/api/accounts/withdraw/', {'password': STRONG}, format='json')
        response = APIClient().post('/api/accounts/login/', {'identifier': 'alice', 'password': STRONG},
                                    format='json')
        self.assertEqual(response.status_code, 401)

    def test_staff_get_a_clear_refusal(self):
        _, _, teacher_c = enrol('tea', role='EXPERT_TEACHER')
        response = teacher_c.post('/api/accounts/withdraw/', {'password': STRONG}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('participants', response.json()['error'])


class ResearcherWithdrawalEndpointTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.profile, _ = enrol('alice')
        generate_data(self.user)
        _, _, self.boss = enrol('boss', role='RESEARCHER_ADMIN')
        _, _, self.teacher = enrol('tea', role='EXPERT_TEACHER')
        _, _, self.other = enrol('bob')

    def url(self, code=None):
        return f'/api/admin/participants/{code or self.profile.participant_code}/withdraw/'

    def test_a_researcher_can_action_a_withdrawal_by_participant_code(self):
        response = self.boss.post(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['withdrawn_by'], 'researcher')
        self.assertFalse(ExamSubmission.objects.filter(student=self.user).exists())

    def test_only_researchers_may(self):
        self.assertEqual(self.teacher.post(self.url()).status_code, 403)
        self.assertEqual(self.other.post(self.url()).status_code, 403)
        self.assertTrue(ExamSubmission.objects.filter(student=self.user).exists())

    def test_an_unknown_code_is_a_404(self):
        self.assertEqual(self.boss.post(self.url('TT-9999')).status_code, 404)


class RightOfAccessTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.profile, self.client_ = enrol('alice')
        generate_data(self.user)

    def test_a_participant_can_download_everything_held_about_them(self):
        body = self.client_.get('/api/accounts/my-data/').json()
        self.assertEqual(body['profile']['participant_code'], self.profile.participant_code)
        self.assertEqual(body['profile']['school_name'], 'Dhaka College')
        self.assertEqual(len(body['submissions']), 1)
        self.assertEqual(len(body['events']), 3)
        self.assertEqual(body['events'][1]['payload']['prompt'], 'secret question')

    def test_it_is_only_ever_the_callers_own_data(self):
        other, _, other_c = enrol('bob')
        body = other_c.get('/api/accounts/my-data/').json()
        self.assertEqual(body['account']['username'], 'bob')
        self.assertEqual(body['submissions'], [])
        self.assertEqual(body['events'], [])
