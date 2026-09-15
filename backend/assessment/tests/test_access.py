"""Who can reach which endpoint, and what a participant is allowed to see.

These are the study's integrity guarantees, so they are asserted rather than assumed:
a participant must not read a later paper early, must not see another participant's
data, and must not reach the researcher aggregates or the raw dataset export.
"""
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission


def enrol(username, role='STUDENT', arm='REASONING_VISIBLE'):
    user = User.objects.create_user(username=username, password='Testpass!2345')
    ParticipantProfile.objects.create(user=user, role=role, assigned_arm=arm, consent_given=True)
    client = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)
    return user, client


class EndpointPermissionTests(ApiTestCase):
    """A table of every endpoint against every kind of caller."""

    @classmethod
    def setUpTestData(cls):
        cls.student_user, _ = enrol('stu')
        cls.teacher_user, _ = enrol('tea', role='EXPERT_TEACHER')
        cls.boss_user, _ = enrol('boss', role='RESEARCHER_ADMIN')

    def setUp(self):
        super().setUp()
        self.anon = APIClient()
        self.student = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.get(user=self.student_user).key)
        self.teacher = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.get(user=self.teacher_user).key)
        self.boss = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.get(user=self.boss_user).key)

    RESEARCHER_ONLY = ['/api/admin/stats/', '/api/admin/export/']
    STAFF_ONLY = ['/api/expert/reviews/', '/api/expert/submissions/', '/api/curriculum/passages/']

    def test_anonymous_callers_are_refused_everywhere(self):
        for url in self.RESEARCHER_ONLY + self.STAFF_ONLY + ['/api/dashboard/', '/api/code/status/']:
            self.assertIn(self.anon.get(url).status_code, (401, 403), url)

    def test_participants_cannot_reach_researcher_endpoints(self):
        for url in self.RESEARCHER_ONLY:
            self.assertEqual(self.student.get(url).status_code, 403, url)

    def test_teachers_cannot_reach_researcher_endpoints(self):
        for url in self.RESEARCHER_ONLY:
            self.assertEqual(self.teacher.get(url).status_code, 403, url)

    def test_participants_cannot_reach_staff_endpoints(self):
        for url in self.STAFF_ONLY:
            self.assertEqual(self.student.get(url).status_code, 403, url)

    def test_staff_can_reach_staff_endpoints(self):
        for url in self.STAFF_ONLY:
            self.assertEqual(self.teacher.get(url).status_code, 200, url)

    def test_researchers_can_reach_everything(self):
        for url in self.RESEARCHER_ONLY + self.STAFF_ONLY:
            self.assertEqual(self.boss.get(url).status_code, 200, url)

    def test_a_user_without_a_profile_is_treated_as_unprivileged(self):
        """The role gates read the profile; a missing one must fail closed."""
        orphan = User.objects.create_user(username='orphan', password='Testpass!2345')
        client = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=orphan).key)
        for url in self.RESEARCHER_ONLY + self.STAFF_ONLY:
            self.assertEqual(client.get(url).status_code, 403, url)


class ExamPaperAccessTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.student_user, self.student = enrol('stu')
        self.teacher_user, self.teacher = enrol('tea', role='EXPERT_TEACHER')

    def items(self, client, exam_type):
        return client.get(f'/api/assessment/items/?type={exam_type}')

    def test_a_new_participant_may_only_open_the_pre_test(self):
        self.assertEqual(self.items(self.student, 'pre').status_code, 200)
        for later in ('post', 'transfer', 'withdrawal'):
            self.assertEqual(self.items(self.student, later).status_code, 403, later)

    def test_the_next_paper_unlocks_only_after_the_previous_one_is_submitted(self):
        ExamSubmission.objects.create(student=self.student_user, exam_type='pre',
                                      score_pct=40, answers={})
        self.assertEqual(self.items(self.student, 'post').status_code, 200)
        self.assertEqual(self.items(self.student, 'transfer').status_code, 403)

    def test_a_completed_paper_stays_readable(self):
        ExamSubmission.objects.create(student=self.student_user, exam_type='pre',
                                      score_pct=40, answers={})
        self.assertEqual(self.items(self.student, 'pre').status_code, 200)

    def test_the_response_reports_which_papers_are_open(self):
        body = self.items(self.student, 'pre').json()
        self.assertEqual(body['available'], ['pre'])
        self.assertEqual(body['exam_type'], 'pre')

    def test_a_refusal_also_reports_which_papers_are_open(self):
        self.assertEqual(self.items(self.student, 'withdrawal').json()['available'], ['pre'])

    def test_staff_may_open_every_paper_to_review_the_bank(self):
        for exam_type in ('pre', 'post', 'transfer', 'withdrawal'):
            self.assertEqual(self.items(self.teacher, exam_type).status_code, 200, exam_type)

    def test_an_unknown_paper_is_rejected_rather_than_silently_served(self):
        self.assertEqual(self.items(self.student, 'nonsense').status_code, 400)

    def test_served_items_never_carry_the_answer_key(self):
        for item in self.items(self.teacher, 'pre').json()['items']:
            for secret in ('keyed_answer', 'test_cases', 'html_checks'):
                self.assertNotIn(secret, item, f"{item['id']} leaked {secret}")

    def test_a_locked_paper_cannot_be_submitted_either(self):
        response = self.student.post('/api/assessment/submit/',
                                     {'exam_type': 'withdrawal', 'answers': {}}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ExamSubmission.objects.exists())

    def test_an_open_paper_can_be_submitted(self):
        response = self.student.post('/api/assessment/submit/',
                                     {'exam_type': 'pre', 'answers': {}}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExamSubmission.objects.count(), 1)


class SubmissionOwnershipTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.victim_user, _ = enrol('victim')
        self.attacker_user, self.attacker = enrol('attacker')

    def test_a_submission_belongs_to_the_caller_whatever_the_body_says(self):
        self.attacker.post('/api/assessment/submit/', {
            'exam_type': 'pre', 'answers': {},
            'user_id': self.victim_user.id, 'username': 'victim',
        }, format='json')
        submission = ExamSubmission.objects.get()
        self.assertEqual(submission.student, self.attacker_user)

    def test_the_score_is_computed_server_side_not_taken_from_the_body(self):
        response = self.attacker.post('/api/assessment/submit/', {
            'exam_type': 'pre', 'answers': {}, 'score_pct': 100, 'score': 100,
        }, format='json')
        self.assertEqual(response.json()['score_pct'], 0)
        self.assertEqual(ExamSubmission.objects.get().score_pct, 0)


class ResearcherExportTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.boss_user, self.boss = enrol('boss', role='RESEARCHER_ADMIN')
        self.student_user, _ = enrol('alice')
        ExamSubmission.objects.create(student=self.student_user, exam_type='pre',
                                      score_pct=40, answers={})

    def csv(self):
        response = self.boss.get('/api/admin/export/')
        body = b''.join(response.streaming_content).decode('utf-8')
        return response, [line for line in body.splitlines() if line.strip()]

    def test_the_export_streams_a_header_and_one_row_per_participant(self):
        response, lines = self.csv()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith('participant_code,arm'))
        self.assertEqual(response['X-Trace-Row-Count'], '1')

    def test_the_export_is_offered_as_a_dated_download(self):
        response, _ = self.csv()
        self.assertIn('attachment; filename="trace_tutor_dataset_', response['Content-Disposition'])

    def test_the_export_identifies_people_only_by_participant_code(self):
        _, lines = self.csv()
        self.assertIn('TT-', lines[1])
        self.assertNotIn('alice', lines[1])

    def test_the_export_carries_the_real_recorded_score(self):
        _, lines = self.csv()
        self.assertIn('40', lines[1].split(','))


class AdminStatsTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        _, self.boss = enrol('boss', role='RESEARCHER_ADMIN')

    def test_an_empty_study_reports_nulls_rather_than_illustrative_numbers(self):
        body = self.boss.get('/api/admin/stats/').json()
        self.assertEqual(body['total_participants'], 0)
        for outcome in ('learning_gain', 'transfer_performance', 'ai_dependency_drop'):
            self.assertIsNone(body[outcome]['p_value'], outcome)
            self.assertIsNone(body[outcome]['cohens_d'], outcome)
            self.assertIsNotNone(body[outcome]['note'], outcome)

    def test_participant_counts_track_real_enrolments(self):
        enrol('s1', arm='REASONING_VISIBLE')
        enrol('s2', arm='ANSWER_ONLY')
        body = self.boss.get('/api/admin/stats/').json()
        self.assertEqual(body['total_participants'], 2)
        self.assertEqual(body['arms'], {'REASONING_VISIBLE': 1, 'ANSWER_ONLY': 1})
