"""Enrolment, arm allocation, and the fields a participant may change about themselves."""
from collections import Counter

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile

STRONG = 'Str0ng-Pass-2026'


def enrol(username, role='STUDENT', arm='REASONING_VISIBLE'):
    user = User.objects.create_user(username=username, password=STRONG)
    ParticipantProfile.objects.create(user=user, role=role, assigned_arm=arm, enrolled_arm=arm,
                                      consent_given=True)
    return user, APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)


class RegistrationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def register(self, **overrides):
        payload = {'username': 'newstudent', 'full_name': 'New Student',
                   'password': STRONG, 'role': 'STUDENT', 'consent_given': True}
        payload.update(overrides)
        return self.client.post('/api/accounts/register/', payload, format='json')

    def test_a_student_can_enrol_and_receives_a_token(self):
        response = self.register()
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['token'])
        self.assertEqual(response.json()['user']['role'], 'STUDENT')

    def test_consent_is_required_for_a_student(self):
        response = self.register(consent_given=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn('consent_given', response.json()['fields'])

    def test_a_weak_password_is_rejected(self):
        for weak in ('short', '12345678', 'password'):
            self.assertEqual(self.register(password=weak).status_code, 400, weak)

    def test_usernames_are_validated_and_unique(self):
        self.register()
        self.assertIn('username', self.register().json()['fields'])
        self.assertIn('username', self.register(username='ab').json()['fields'])
        self.assertIn('username', self.register(username='has space').json()['fields'])

    def test_a_participant_is_given_a_pseudonymous_code(self):
        self.register()
        self.assertTrue(ParticipantProfile.objects.get().participant_code.startswith('TT-'))

    def test_a_participant_cannot_choose_their_own_arm_at_enrolment(self):
        """assigned_arm is not an editable profile field, so the body cannot set it."""
        arms = set()
        for i in range(8):
            self.register(username=f'student{i:02d}')
            arms.add(ParticipantProfile.objects.get(user__username=f'student{i:02d}').assigned_arm)
        # With balanced allocation over 8 enrolments both arms must have been used.
        self.assertEqual(arms, {'REASONING_VISIBLE', 'ANSWER_ONLY'})


@override_settings(STAFF_ACCESS_CODE='THE-CODE')
class StaffRegistrationTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def register(self, **overrides):
        payload = {'username': 'newteacher', 'full_name': 'New Teacher',
                   'password': STRONG, 'role': 'EXPERT_TEACHER'}
        payload.update(overrides)
        return self.client.post('/api/accounts/register/', payload, format='json')

    def test_the_access_code_is_required(self):
        self.assertIn('access_code', self.register().json()['fields'])
        self.assertIn('access_code', self.register(access_code='wrong').json()['fields'])

    def test_the_correct_code_enrols_a_teacher(self):
        self.assertEqual(self.register(access_code='THE-CODE').status_code, 201)

    @override_settings(STAFF_ACCESS_CODE='')
    def test_staff_registration_is_refused_outright_when_no_code_is_configured(self):
        """An empty configured code must not mean 'any code will do'."""
        for attempt in ({}, {'access_code': ''}, {'access_code': 'anything'}):
            self.assertIn('access_code', self.register(**attempt).json()['fields'])


class ArmAllocationTests(ApiTestCase):
    def test_allocation_stays_balanced_across_many_enrolments(self):
        client = APIClient()
        for i in range(20):
            client.post('/api/accounts/register/', {
                'username': f'stud{i:03d}', 'full_name': f'Student {i}',
                'password': STRONG, 'role': 'STUDENT', 'consent_given': True,
            }, format='json')
        counts = Counter(ParticipantProfile.objects.filter(role='STUDENT')
                         .values_list('assigned_arm', flat=True))
        self.assertEqual(counts['REASONING_VISIBLE'], 10)
        self.assertEqual(counts['ANSWER_ONLY'], 10)

    def test_allocation_fills_the_smaller_arm(self):
        for i in range(3):
            enrol(f'rv{i}', arm='REASONING_VISIBLE')
        self.assertEqual(ParticipantProfile.balanced_arm(), 'ANSWER_ONLY')

    def test_staff_are_not_allocated_into_the_study(self):
        for i in range(4):
            enrol(f'rv{i}', arm='REASONING_VISIBLE', role='EXPERT_TEACHER')
        # Only students count towards balance, so the arms are still tied.
        self.assertIn(ParticipantProfile.balanced_arm(), ('REASONING_VISIBLE', 'ANSWER_ONLY'))


class ArmSwitchTests(ApiTestCase):
    """The arm is the experiment's independent variable. When a participant may move
    between conditions is the ARM_SWITCH_POLICY; the allocation of record never changes
    under any policy, and every switch is logged with who made it, why, and whether the
    protocol was already complete."""

    def setUp(self):
        super().setUp()
        self.student_user, self.student = enrol('stu', arm='ANSWER_ONLY')
        self.teacher_user, self.teacher = enrol('tea', role='EXPERT_TEACHER', arm='ANSWER_ONLY')

    def switch(self, client, arm, reason=None):
        body = {'assigned_arm': arm}
        if reason is not None:
            body['arm_switch_reason'] = reason
        return client.patch('/api/accounts/profile/', body, format='json')

    def complete_protocol(self, user):
        from assessment.models import ExamSubmission
        for exam_type in ('pre', 'post', 'transfer', 'withdrawal'):
            ExamSubmission.objects.create(student=user, exam_type=exam_type, score_pct=50, answers={})

    # ---------------------------------------------------------- after_protocol (default)
    def test_the_default_policy_is_after_protocol(self):
        from accounts import arms
        self.assertEqual(arms.policy(), 'after_protocol')

    def test_a_participant_is_locked_until_the_last_paper_is_in(self):
        response = self.switch(self.student, 'REASONING_VISIBLE')
        self.assertEqual(response.status_code, 400)
        self.assertIn('all four papers', response.json()['fields']['assigned_arm'])
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.assigned_arm, 'ANSWER_ONLY')

    def test_three_papers_are_not_enough(self):
        from assessment.models import ExamSubmission
        for exam_type in ('pre', 'post', 'transfer'):
            ExamSubmission.objects.create(student=self.student_user, exam_type=exam_type, score_pct=50, answers={})
        self.assertEqual(self.switch(self.student, 'REASONING_VISIBLE').status_code, 400)

    def test_the_switch_unlocks_once_the_protocol_is_complete(self):
        self.complete_protocol(self.student_user)
        response = self.switch(self.student, 'REASONING_VISIBLE', reason='wanted to see the steps')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['arm'], 'REASONING_VISIBLE')

    def test_the_session_explains_the_lock_and_then_the_unlock(self):
        before = self.student.get('/api/accounts/me/').json()
        self.assertFalse(before['arm_self_select'])
        self.assertEqual(before['arm_switch_reason'], 'after_protocol')
        self.assertEqual(before['arm_switch_policy'], 'after_protocol')
        self.complete_protocol(self.student_user)
        after = self.student.get('/api/accounts/me/').json()
        self.assertTrue(after['arm_self_select'])
        self.assertEqual(after['arm_switch_reason'], 'completed')

    def test_a_pending_submission_still_counts_as_a_sat_paper(self):
        from assessment.models import ExamSubmission
        for exam_type in ('pre', 'post', 'transfer', 'withdrawal'):
            ExamSubmission.objects.create(student=self.student_user, exam_type=exam_type,
                                          score_pct=None, grading_status=ExamSubmission.PENDING, answers={})
        self.assertEqual(self.switch(self.student, 'REASONING_VISIBLE').status_code, 200)

    # ------------------------------------------------------------------- logging
    def test_every_switch_is_logged_with_who_why_and_when(self):
        from logging_app.models import InteractionLog
        self.complete_protocol(self.student_user)
        self.switch(self.student, 'REASONING_VISIBLE', reason='curious about the reasoning')
        event = InteractionLog.objects.get(user=self.student_user, event_type='ARM_SWITCH')
        self.assertEqual((event.payload['from'], event.payload['to']), ('ANSWER_ONLY', 'REASONING_VISIBLE'))
        self.assertTrue(event.payload['self_selected'])
        self.assertTrue(event.payload['protocol_complete'])
        self.assertEqual(event.payload['reason'], 'curious about the reasoning')
        self.assertEqual(event.payload['enrolled_arm'], 'ANSWER_ONLY')
        self.assertEqual(event.arm, 'REASONING_VISIBLE', 'the event carries the arm after the switch')

    @override_settings(ARM_SWITCH_POLICY='always')
    def test_a_switch_before_completion_is_marked_as_such(self):
        from logging_app.models import InteractionLog
        self.switch(self.student, 'REASONING_VISIBLE')
        event = InteractionLog.objects.get(user=self.student_user, event_type='ARM_SWITCH')
        self.assertFalse(event.payload['protocol_complete'])

    def test_switching_never_changes_the_arm_of_record(self):
        self.complete_protocol(self.student_user)
        self.switch(self.student, 'REASONING_VISIBLE')
        self.switch(self.student, 'ANSWER_ONLY')
        self.switch(self.student, 'REASONING_VISIBLE')
        self.student_user.profile.refresh_from_db()
        self.assertEqual(self.student_user.profile.enrolled_arm, 'ANSWER_ONLY')
        self.assertEqual(self.student.get('/api/accounts/me/').json()['enrolled_arm'], 'ANSWER_ONLY')

    # ------------------------------------------------------------ other policies
    @override_settings(ARM_SWITCH_POLICY='never')
    def test_never_locks_participants_even_after_completion(self):
        self.complete_protocol(self.student_user)
        response = self.switch(self.student, 'REASONING_VISIBLE')
        self.assertEqual(response.status_code, 400)
        self.assertIn('fixed for this study', response.json()['fields']['assigned_arm'])
        self.assertEqual(self.student.get('/api/accounts/me/').json()['arm_switch_reason'], 'never')

    @override_settings(ARM_SWITCH_POLICY='always')
    def test_always_lets_participants_switch_at_any_time(self):
        self.assertEqual(self.switch(self.student, 'REASONING_VISIBLE').status_code, 200)

    @override_settings(ARM_SWITCH_POLICY='nonsense')
    def test_an_unknown_policy_falls_back_to_the_safe_one(self):
        from accounts import arms
        self.assertEqual(arms.policy(), 'after_protocol')

    @override_settings(ARM_SWITCH_POLICY='never')
    def test_staff_may_switch_under_every_policy(self):
        response = self.switch(self.teacher, 'REASONING_VISIBLE')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.teacher.get('/api/accounts/me/').json()['arm_switch_reason'], 'staff')

    # ------------------------------------------------------------------- misc
    def test_a_participant_can_still_edit_their_other_profile_fields(self):
        response = self.student.patch('/api/accounts/profile/',
                                      {'school_name': 'Dhaka College', 'weekly_study_hours': 6},
                                      format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['school_name'], 'Dhaka College')

    def test_an_unknown_mode_is_refused(self):
        self.assertEqual(self.switch(self.teacher, 'MAGIC').status_code, 400)
        self.complete_protocol(self.student_user)
        self.assertEqual(self.switch(self.student, 'MAGIC').status_code, 400)

    @override_settings(ARM_SWITCH_POLICY='always')
    def test_allocation_balance_counts_enrolment_not_later_switches(self):
        """Participants enrolled ANSWER_ONLY who all switch must not make the next
        enrolment land in ANSWER_ONLY to 'rebalance' a move that never happened."""
        for i in range(3):
            user, client = enrol(f'mover{i}', arm='ANSWER_ONLY')
            self.switch(client, 'REASONING_VISIBLE')
        # Enrolled: stu + 3 movers = 4 ANSWER_ONLY, 0 REASONING_VISIBLE -> next is REASONING_VISIBLE.
        self.assertEqual(ParticipantProfile.balanced_arm(), 'REASONING_VISIBLE')


class SubmissionArmTests(ApiTestCase):
    """Every paper records the mode it was sat in, so per-protocol analysis is possible."""

    def test_a_submission_is_stamped_with_the_current_arm(self):
        from assessment.models import ExamSubmission
        user, client = enrol('stu', arm='ANSWER_ONLY')
        client.post('/api/assessment/submit/', {'exam_type': 'pre', 'answers': {}}, format='json')
        self.assertEqual(ExamSubmission.objects.get().arm, 'ANSWER_ONLY')

    @override_settings(ARM_SWITCH_POLICY='always')
    def test_the_stamp_follows_the_mode_at_submission_time(self):
        from assessment.models import ExamSubmission
        user, client = enrol('stu', arm='ANSWER_ONLY')
        client.post('/api/assessment/submit/', {'exam_type': 'pre', 'answers': {}}, format='json')
        client.patch('/api/accounts/profile/', {'assigned_arm': 'REASONING_VISIBLE'}, format='json')
        client.post('/api/assessment/submit/', {'exam_type': 'post', 'answers': {}}, format='json')
        arms_by_paper = dict(ExamSubmission.objects.values_list('exam_type', 'arm'))
        self.assertEqual(arms_by_paper, {'pre': 'ANSWER_ONLY', 'post': 'REASONING_VISIBLE'})


class ProfileTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('stu')

    def test_a_participant_reads_their_own_profile(self):
        self.assertEqual(self.client_.get('/api/accounts/profile/').json()['username'], 'stu')

    def test_the_profile_needs_authentication(self):
        self.assertIn(APIClient().get('/api/accounts/profile/').status_code, (401, 403))

    def test_role_cannot_be_escalated_through_a_profile_update(self):
        self.client_.patch('/api/accounts/profile/', {'role': 'RESEARCHER_ADMIN'}, format='json')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, 'STUDENT')

    def test_participant_code_cannot_be_rewritten(self):
        original = self.user.profile.participant_code
        self.client_.patch('/api/accounts/profile/', {'participant_code': 'TT-9999'}, format='json')
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.participant_code, original)

    def test_an_out_of_range_language_falls_back_to_bangla(self):
        response = self.client_.patch('/api/accounts/profile/',
                                      {'preferred_language': 'fr'}, format='json')
        self.assertEqual(response.json()['language'], 'bn')

    def test_numeric_covariates_are_clamped_not_trusted(self):
        response = self.client_.patch('/api/accounts/profile/',
                                      {'weekly_study_hours': 999999}, format='json')
        self.assertLessEqual(response.json()['weekly_study_hours'], 32000)


class AuthTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, _ = enrol('stu')

    def test_login_by_username_and_by_email(self):
        self.user.email = 'stu@example.com'
        self.user.save(update_fields=['email'])
        client = APIClient()
        for identifier in ('stu', 'stu@example.com'):
            response = client.post('/api/accounts/login/',
                                   {'identifier': identifier, 'password': STRONG}, format='json')
            self.assertEqual(response.status_code, 200, identifier)

    def test_a_bad_password_is_rejected(self):
        response = APIClient().post('/api/accounts/login/',
                                    {'identifier': 'stu', 'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_a_deactivated_account_cannot_log_in(self):
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        response = APIClient().post('/api/accounts/login/',
                                    {'identifier': 'stu', 'password': STRONG}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_logout_revokes_the_token_server_side(self):
        token = Token.objects.get(user=self.user).key
        client = APIClient(HTTP_AUTHORIZATION='Token ' + token)
        self.assertEqual(client.post('/api/accounts/logout/').status_code, 200)
        self.assertFalse(Token.objects.filter(key=token).exists())
        self.assertIn(client.get('/api/accounts/me/').status_code, (401, 403))

    def test_changing_the_password_rotates_the_token(self):
        old = Token.objects.get(user=self.user).key
        client = APIClient(HTTP_AUTHORIZATION='Token ' + old)
        response = client.post('/api/accounts/password/', {
            'current_password': STRONG, 'new_password': 'An0ther-Str0ng-Pass'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()['token'], old)
        self.assertFalse(Token.objects.filter(key=old).exists())

    def test_the_wrong_current_password_blocks_the_change(self):
        client = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.get(user=self.user).key)
        response = client.post('/api/accounts/password/', {
            'current_password': 'wrong', 'new_password': 'An0ther-Str0ng-Pass'}, format='json')
        self.assertEqual(response.status_code, 400)
