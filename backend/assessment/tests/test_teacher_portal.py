"""Teacher repairs use disposable PostgreSQL rows, never real grades or ratings."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import ExamSubmission, ExpertGrade, ExpertRating
from trace_backend.test_utils import ApiTestCase

CRITERIA = ('alignment', 'accuracy', 'clarity', 'difficulty', 'answerability')


def account(name, role='EXPERT_TEACHER'):
    user = User.objects.create_user(username=name)
    ParticipantProfile.objects.create(user=user, role=role, assigned_arm='REASONING_VISIBLE')
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


class TeacherPortalTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.teacher, self.client = account('qa-teacher')
        self.other, self.other_client = account('qa-other')
        self.student, self.student_client = account('qa-student', 'STUDENT')
        self.item_id = scoring.all_items()[0][1]['id']
        self.submission = ExamSubmission.objects.create(student=self.student, exam_type='pre', score_pct=None)

    def rate(self, client=None, **overrides):
        body = {'item_id': self.item_id, 'ratings': dict.fromkeys(CRITERIA, 4),
                'feedback': 'Disposable expert comment', 'expected_revision': None, **overrides}
        return (client or self.client).post('/api/expert/rating/', body, format='json')

    def grade(self, client=None, **overrides):
        body = {'submission_id': self.submission.pk, 'assigned_marks': 70,
                'feedback': 'Disposable grade feedback', 'expected_revision': None, **overrides}
        return (client or self.client).post('/api/expert/grade/', body, format='json')

    def test_complete_rating_is_persisted_retrieved_and_replaced_only_for_its_expert(self):
        response = self.rate()
        self.assertEqual(response.status_code, 200)
        original = response.json()['rating_revision']
        reviewed = next(i for i in self.client.get('/api/expert/reviews/').json()['items_to_review'] if i['id'] == self.item_id)
        self.assertEqual(reviewed['rating_revision'], original)
        self.assertEqual(reviewed['my_rating'], {**dict.fromkeys(CRITERIA, 4), 'feedback': 'Disposable expert comment'})
        self.assertEqual(self.rate(self.other_client).status_code, 200)
        changed = self.rate(ratings=dict.fromkeys(CRITERIA, 2), feedback='Revised comment', expected_revision=original)
        self.assertEqual(changed.status_code, 200)
        self.assertNotEqual(changed.json()['rating_revision'], original)
        self.assertEqual(ExpertRating.objects.count(), 2)
        self.assertEqual(ExpertRating.objects.get(expert_user=self.other).alignment_score, 4)
        self.assertEqual(ExpertRating.objects.get(expert_user=self.teacher).feedback, 'Revised comment')

    def test_incomplete_malformed_and_out_of_range_rubrics_never_write_defaults(self):
        invalid = [None, [], 'scores', {}, {'alignment': 4}]
        invalid += [{**dict.fromkeys(CRITERIA, 4), 'accuracy': value}
                    for value in (None, 0, 5, -1, 2.5, True, {}, 'NaN')]
        for ratings in invalid:
            with self.subTest(ratings=ratings):
                self.assertEqual(self.rate(ratings=ratings).status_code, 400)
                self.assertFalse(ExpertRating.objects.exists())

    def test_unknown_item_never_creates_a_research_rating(self):
        self.assertEqual(self.rate(item_id='not-a-real-item').status_code, 400)
        self.assertFalse(ExpertRating.objects.exists())

    def test_stale_rating_and_stale_first_creation_return_conflict_without_overwriting(self):
        first = self.rate()
        self.assertEqual(self.rate(feedback='Stale create').status_code, 409)
        revision = first.json()['rating_revision']
        self.assertEqual(self.rate(feedback='Second session', expected_revision=revision).status_code, 200)
        self.assertEqual(self.rate(feedback='Stale overwrite', expected_revision=revision).status_code, 409)
        self.assertEqual(ExpertRating.objects.get().feedback, 'Second session')

    def test_grade_boundaries_and_updates_are_retrievable_and_do_not_alter_server_scores(self):
        first = self.grade(assigned_marks=0)
        self.assertEqual(first.status_code, 200)
        second = self.grade(assigned_marks=100, expected_revision=first.json()['grade_revision'])
        self.assertEqual(second.status_code, 200)
        self.assertEqual(ExpertGrade.objects.count(), 1)
        row = self.client.get('/api/expert/submissions/').json()['submissions'][0]
        self.assertEqual(row['assigned_marks'], 100)
        self.assertEqual(row['grade_revision'], second.json()['grade_revision'])
        self.submission.refresh_from_db()
        self.assertIsNone(self.submission.score_pct)

    def test_invalid_marks_do_not_silently_become_zero_or_clamped_grades(self):
        for value in (None, '', 'bad', -1, 101, 0.5, True, {}, [], '20.5'):
            with self.subTest(value=value):
                self.assertEqual(self.grade(assigned_marks=value).status_code, 400)
                self.assertFalse(ExpertGrade.objects.exists())

    def test_unknown_submission_does_not_create_a_grade(self):
        self.assertEqual(self.grade(submission_id='bad').status_code, 404)
        self.assertFalse(ExpertGrade.objects.exists())

    def test_grade_revision_prevents_stale_overwrites_for_the_same_reviewer(self):
        first = self.grade()
        original = first.json()['grade_revision']
        self.assertEqual(self.grade(self.other_client, assigned_marks=90, expected_revision=None).status_code, 200)
        self.assertEqual(self.grade(assigned_marks=75, expected_revision=original).status_code, 200)
        self.assertEqual(self.grade(assigned_marks=20, expected_revision=original).status_code, 409)
        self.assertEqual(ExpertGrade.objects.get(expert_user=self.teacher).assigned_marks, 75)
        self.assertEqual(ExpertGrade.objects.get(expert_user=self.other).assigned_marks, 90)

    def test_updating_a_grade_keeps_each_experts_display_independent(self):
        first = self.grade()
        second = self.grade(self.other_client, assigned_marks=80, expected_revision=None)
        self.assertEqual(second.status_code, 200)
        third = self.grade(assigned_marks=95, expected_revision=first.json()['grade_revision'])
        self.assertEqual(third.status_code, 200)
        row = self.client.get('/api/expert/submissions/').json()['submissions'][0]
        self.assertEqual(row['assigned_marks'], 95)
        self.assertEqual(row['graded_by'], self.teacher.username)
        self.assertEqual(row['grade_revision'], third.json()['grade_revision'])
        other_row = self.other_client.get('/api/expert/submissions/').json()['submissions'][0]
        self.assertEqual(other_row['assigned_marks'], 80)

    def test_score_api_preserves_null_and_zero_and_pending_status(self):
        ExamSubmission.objects.create(student=self.student, exam_type='post', score_pct=0)
        ExamSubmission.objects.create(student=self.student, exam_type='transfer', score_pct=85, grading_status='pending')
        rows = self.client.get('/api/expert/submissions/').json()['submissions']
        self.assertIsNone(next(r for r in rows if r['exam_type'] == 'pre')['score_pct'])
        self.assertEqual(next(r for r in rows if r['exam_type'] == 'post')['score_pct'], 0)
        self.assertIsNone(next(r for r in rows if r['exam_type'] == 'transfer')['score_pct'])

    def test_submission_queue_includes_older_participants_beyond_100_rows(self):
        self.student.profile.participant_code = 'SIM-001'
        self.student.profile.save(update_fields=['participant_code'])
        newer_student, _ = account('qa-newer-student', 'STUDENT')
        newer_student.profile.participant_code = 'SIM-060'
        newer_student.profile.save(update_fields=['participant_code'])
        self.assertEqual(self.grade().status_code, 200)
        newer = ExamSubmission.objects.bulk_create([
            ExamSubmission(student=newer_student, exam_type='pre') for _ in range(104)
        ])
        # Imported cohorts can share a timestamp; the ID must break ties consistently.
        ExamSubmission.objects.all().update(submitted_at=self.submission.submitted_at)

        response = self.client.get('/api/expert/submissions/')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 105)
        self.assertEqual([row['id'] for row in data['submissions']],
                         sorted([self.submission.pk, *(sub.pk for sub in newer)], reverse=True))
        oldest = data['submissions'][-1]
        self.assertEqual(oldest['participant_code'], 'SIM-001')
        self.assertEqual(oldest['assigned_marks'], 70)

    def test_students_and_anonymous_callers_cannot_read_or_write_teacher_data(self):
        for client in (self.student_client, APIClient()):
            for url in ('/api/expert/reviews/', '/api/expert/submissions/', '/api/expert/certification/'):
                self.assertIn(client.get(url).status_code, (401, 403))
            self.assertIn(self.rate(client).status_code, (401, 403))
            self.assertIn(self.grade(client).status_code, (401, 403))
        self.assertFalse(ExpertGrade.objects.exists())
        self.assertFalse(ExpertRating.objects.exists())

    def test_teacher_profile_validation_persistence_and_role_immutability(self):
        saved = self.client.patch('/api/accounts/profile/',
                                 {'full_name': 'Disposable Teacher', 'school_name': 'QA School',
                                  'preferred_language': 'en', 'role': 'RESEARCHER_ADMIN'}, format='json')
        self.assertEqual(saved.status_code, 200)
        fresh = self.client.get('/api/accounts/profile/').json()
        self.assertEqual(fresh['full_name'], 'Disposable Teacher')
        self.assertEqual(fresh['school_name'], 'QA School')
        self.assertEqual(fresh['role'], 'EXPERT_TEACHER')
        self.assertEqual(self.client.patch('/api/accounts/profile/', {'full_name': ''}, format='json').status_code, 400)
        self.assertEqual(self.client.get('/api/accounts/profile/').json()['full_name'], 'Disposable Teacher')

    def test_teacher_arm_switch_is_persisted_but_enrolment_arm_is_immutable(self):
        original = self.teacher.profile.enrolled_arm
        self.assertEqual(self.client.patch('/api/accounts/profile/', {'assigned_arm': 'ANSWER_ONLY'}, format='json').status_code, 200)
        self.assertEqual(self.client.get('/api/accounts/me/').json()['arm'], 'ANSWER_ONLY')
        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.enrolled_arm, original)
        self.assertEqual(self.client.patch('/api/accounts/profile/', {'assigned_arm': 'INVALID'}, format='json').status_code, 400)

    def test_teacher_code_execution_preserves_success_errors_and_timeout_results(self):
        for result in ({'status': 'SUCCESS', 'test_results': [{'actual': '1', 'passed': True}]},
                       {'status': 'COMPILE_ERROR', 'compile_output': 'Disposable diagnostic'},
                       {'status': 'RUNTIME_ERROR', 'test_results': [{'timed_out': True}]}):
            with self.subTest(status=result['status']), patch('tutor.views.runner.run_code', return_value=result) as run:
                response = self.client.post('/api/code/run/', {'language': 'c', 'code': 'int main(){return 0;}'}, format='json')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), result)
                run.assert_called_once()
        with patch('tutor.views.runner.run_code') as run:
            self.assertIn(APIClient().post('/api/code/run/', {'code': 'int main(){}'}, format='json').status_code, (401, 403))
            run.assert_not_called()

    def test_existing_clients_without_revision_fields_keep_their_valid_api_contract(self):
        body = {'item_id': self.item_id, 'ratings': dict.fromkeys(CRITERIA, 4)}
        self.assertEqual(self.client.post('/api/expert/rating/', body, format='json').status_code, 200)
        self.assertEqual(self.client.post('/api/expert/grade/', {'submission_id': self.submission.pk, 'assigned_marks': 70}, format='json').status_code, 200)


@override_settings(GRADING_INLINE=True)
class ConcurrentReviewTests(TransactionTestCase):
    def setUp(self):
        self.teacher, _ = account('concurrent-teacher')
        self.other, _ = account('concurrent-other')
        self.item_id = scoring.all_items()[0][1]['id']
        self.submission = ExamSubmission.objects.create(student=self.teacher, exam_type='pre')

    def race(self, url, users, body):
        barrier = Barrier(2)
        def submit(user_id):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user=User.objects.get(pk=user_id))
                barrier.wait(timeout=10)
                return client.post(url, body, format='json').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(submit, users))

    def test_two_sessions_cannot_both_create_the_same_expert_rating(self):
        statuses = self.race('/api/expert/rating/', [self.teacher.pk, self.teacher.pk],
                             {'item_id': self.item_id, 'ratings': dict.fromkeys(CRITERIA, 4), 'expected_revision': None})
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(ExpertRating.objects.count(), 1)

    def test_two_different_experts_keep_independent_ratings(self):
        statuses = self.race('/api/expert/rating/', [self.teacher.pk, self.other.pk],
                             {'item_id': self.item_id, 'ratings': dict.fromkeys(CRITERIA, 4), 'expected_revision': None})
        self.assertEqual(statuses, [200, 200])
        self.assertEqual(ExpertRating.objects.count(), 2)

    def test_two_experts_can_create_independent_grades_for_the_same_submission(self):
        statuses = self.race('/api/expert/grade/', [self.teacher.pk, self.other.pk],
                             {'submission_id': self.submission.pk, 'assigned_marks': 70, 'expected_revision': None})
        self.assertEqual(statuses, [200, 200])
        self.assertEqual(ExpertGrade.objects.count(), 2)

    def test_two_sessions_cannot_both_create_the_same_experts_grade(self):
        statuses = self.race('/api/expert/grade/', [self.teacher.pk, self.teacher.pk],
                             {'submission_id': self.submission.pk, 'assigned_marks': 70, 'expected_revision': None})
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(ExpertGrade.objects.count(), 1)
