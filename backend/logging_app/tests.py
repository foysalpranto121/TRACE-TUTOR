"""Telemetry is the study's raw behavioural data, so identity has to be unforgeable."""
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission
from logging_app.models import InteractionLog


def enrol(username, role='STUDENT', arm='REASONING_VISIBLE'):
    user = User.objects.create_user(username=username, password='Testpass!2345')
    ParticipantProfile.objects.create(user=user, role=role, assigned_arm=arm, consent_given=True)
    return user, APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)


class TelemetryIdentityTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.victim, _ = enrol('victim', arm='ANSWER_ONLY')
        self.attacker, self.client_ = enrol('attacker', arm='REASONING_VISIBLE')

    def log(self, event_data, event_type='HELP_REQUEST'):
        return self.client_.post('/api/telemetry/log/',
                                 {'event_type': event_type, 'event_data': event_data},
                                 format='json')

    def test_an_event_is_attributed_to_the_caller(self):
        self.log({'problem_id': 'p1'})
        self.assertEqual(InteractionLog.objects.get().user, self.attacker)

    def test_a_body_cannot_attribute_an_event_to_another_participant(self):
        self.log({'user_id': self.victim.id, 'username': 'victim'})
        self.assertEqual(InteractionLog.objects.get().user, self.attacker)

    def test_the_arm_comes_from_the_profile_not_from_the_body(self):
        self.log({'arm': 'ANSWER_ONLY'})
        self.assertEqual(InteractionLog.objects.get().arm, 'REASONING_VISIBLE')

    def test_forged_identity_keys_are_stripped_from_the_stored_payload(self):
        self.log({'user_id': 9999, 'username': 'ghost', 'arm': 'ANSWER_ONLY', 'problem_id': 'p1'})
        payload = InteractionLog.objects.get().payload
        for key in ('user_id', 'username', 'arm'):
            self.assertNotIn(key, payload)
        self.assertEqual(payload['problem_id'], 'p1')

    def test_telemetry_cannot_conjure_participant_accounts(self):
        before = User.objects.count()
        self.log({'username': 'ghost-participant'})
        self.assertEqual(User.objects.count(), before)

    def test_anonymous_telemetry_is_refused(self):
        response = APIClient().post('/api/telemetry/log/',
                                    {'event_type': 'HELP_REQUEST', 'event_data': {}}, format='json')
        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(InteractionLog.objects.exists())

    def test_the_device_id_is_recorded_from_the_signed_cookie(self):
        self.log({})
        self.assertIn('device_id', InteractionLog.objects.get().payload)

    def test_a_non_dict_payload_is_wrapped_rather_than_rejected(self):
        self.client_.post('/api/telemetry/log/',
                          {'event_type': 'PING', 'event_data': 'just a string'}, format='json')
        self.assertEqual(InteractionLog.objects.get().payload['value'], 'just a string')

    def test_event_type_and_problem_id_are_truncated_to_the_column_width(self):
        self.log({'problem_id': 'p' * 200}, event_type='E' * 200)
        log = InteractionLog.objects.get()
        self.assertEqual(len(log.event_type), 50)
        self.assertEqual(len(log.problem_id), 50)


class DashboardScopeTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.victim, _ = enrol('victim')
        self.attacker, self.attacker_c = enrol('attacker')
        self.boss, self.boss_c = enrol('boss', role='RESEARCHER_ADMIN')
        ExamSubmission.objects.create(student=self.victim, exam_type='pre',
                                      score_pct=93, answers={})
        InteractionLog.objects.create(user=self.victim, event_type='HELP_REQUEST', payload={})

    def test_the_dashboard_always_describes_the_caller(self):
        body = self.attacker_c.get('/api/dashboard/').json()
        self.assertEqual(body['profile']['username'], 'attacker')

    def test_the_old_query_parameters_no_longer_select_a_subject(self):
        body = self.attacker_c.get(f'/api/dashboard/?user_id={self.victim.id}&username=victim').json()
        self.assertEqual(body['profile']['username'], 'attacker')
        self.assertEqual(body['assessments'], {})
        self.assertEqual(body['stats']['help_requests'], 0)

    def test_anonymous_callers_get_nothing(self):
        self.assertIn(APIClient().get('/api/dashboard/').status_code, (401, 403))

    def test_participants_do_not_see_study_wide_totals(self):
        self.assertNotIn('overview', self.attacker_c.get('/api/dashboard/').json())

    def test_researchers_do_see_study_wide_totals(self):
        body = self.boss_c.get('/api/dashboard/').json()
        self.assertIn('overview', body)
        self.assertEqual(body['overview']['participants'], 3)

    def test_a_participant_sees_their_own_submissions(self):
        _, victim_c = None, APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.get(user=self.victim).key)
        body = victim_c.get('/api/dashboard/').json()
        self.assertEqual(body['assessments']['pre']['latest_score'], 93)


class DashboardCacheTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu')

    def test_the_second_read_is_served_from_cache(self):
        self.assertEqual(self.client_.get('/api/dashboard/')['X-Trace-Cache'], 'miss')
        self.assertEqual(self.client_.get('/api/dashboard/')['X-Trace-Cache'], 'hit')

    def test_new_activity_drops_the_cached_summary(self):
        self.client_.get('/api/dashboard/')
        InteractionLog.objects.create(user=self.user, event_type='CODE_RESULT',
                                      payload={'status': 'SUCCESS'})
        self.assertEqual(self.client_.get('/api/dashboard/')['X-Trace-Cache'], 'miss')

    def test_one_participants_activity_does_not_invalidate_anothers_cache(self):
        other, other_c = enrol('other')
        self.client_.get('/api/dashboard/')
        other_c.get('/api/dashboard/')
        InteractionLog.objects.create(user=other, event_type='CODE_RESULT', payload={})
        self.assertEqual(self.client_.get('/api/dashboard/')['X-Trace-Cache'], 'hit')


class DashboardAggregateTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu')

    def test_counts_reflect_the_logged_events(self):
        for event, payload in [
            ('CODE_RESULT', {'status': 'SUCCESS', 'passed_count': 3, 'total': 3, 'problem_id': 'p1'}),
            ('CODE_RESULT', {'status': 'WRONG_ANSWER', 'passed_count': 1, 'total': 3, 'problem_id': 'p2'}),
            ('HELP_REQUEST', {'problem_id': 'p1', 'prompt': 'why?'}),
            ('COPY_PASTE', {'code_length': 40}),
        ]:
            InteractionLog.objects.create(user=self.user, event_type=event, payload=payload,
                                          problem_id=payload.get('problem_id'))
        stats = self.client_.get('/api/dashboard/').json()['stats']
        self.assertEqual(stats['code_runs'], 2)
        self.assertEqual(stats['help_requests'], 1)
        self.assertEqual(stats['copy_paste'], 1)
        self.assertEqual(stats['problems_solved'], 1)
        self.assertEqual(stats['problems_attempted'], 2)

    def test_a_participant_with_no_activity_gets_zeros_not_an_error(self):
        body = self.client_.get('/api/dashboard/').json()
        self.assertEqual(body['stats']['code_runs'], 0)
        self.assertEqual(body['problems'], [])
        self.assertEqual(len(body['daily']), 14)
