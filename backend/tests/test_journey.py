"""The whole participant journey, end to end, through the same API the browser uses.

Register -> dashboard -> workspace tools -> tutor -> pre-test -> results -> next paper
unlocks -> profile -> sign out; then the teacher rates and grades; then the researcher
reads the aggregates and the export; then the participant withdraws and every trace of
them is gone. Each step asserts the exact response shape the React pages consume, so a
backend change that would break a screen fails here first.

This is the backend half of a manual click-through. It cannot see whether a page
renders; it can guarantee that every call a page makes still answers the way that
page expects.
"""
from django.test import override_settings

from trace_backend.test_utils import ApiTestCase

from rest_framework.test import APIClient

from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import ExamSubmission
from logging_app.models import InteractionLog

PASSWORD = 'Str0ng-Pass-2026'
STAFF_CODE = 'JOURNEY-CODE'


@override_settings(STAFF_ACCESS_CODE=STAFF_CODE, CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=False)
class ParticipantJourneyTests(ApiTestCase):
    """One long, ordered story rather than many isolated cases: the order is the point."""

    def client_for(self, token):
        return APIClient(HTTP_AUTHORIZATION=f'Token {token}')

    def register(self, **payload):
        return APIClient().post('/api/accounts/register/', payload, format='json')

    def test_the_whole_study_from_enrolment_to_withdrawal(self):
        # ---------------------------------------------------------------- 1. enrol
        response = self.register(username='alice', full_name='Alice Rahman', password=PASSWORD,
                                 role='STUDENT', consent_given=True, school_name='Dhaka College',
                                 grade='11', preferred_language='bn')
        self.assertEqual(response.status_code, 201, response.content)
        alice = response.json()['user']
        alice_c = self.client_for(response.json()['token'])
        self.assertIn(alice['arm'], ('REASONING_VISIBLE', 'ANSWER_ONLY'))
        self.assertTrue(alice['participant_code'].startswith('TT-'))
        self.assertEqual(alice['language'], 'bn')
        self.assertFalse(alice['is_staff_role'])

        # The session-restore call the app makes on every load.
        self.assertEqual(alice_c.get('/api/accounts/me/').json()['username'], 'alice')

        # ------------------------------------------------------------ 2. dashboard
        dashboard = alice_c.get('/api/dashboard/').json()
        for key in ('profile', 'stats', 'problems', 'daily', 'assessments', 'recent'):
            self.assertIn(key, dashboard)
        self.assertNotIn('overview', dashboard, 'study-wide totals are staff-only')
        self.assertEqual(dashboard['stats']['code_runs'], 0)
        self.assertEqual(len(dashboard['daily']), 14)

        # ------------------------------------------------------------ 3. workspace
        status = alice_c.get('/api/code/status/').json()
        for key in ('ready', 'sandbox', 'html'):
            self.assertIn(key, status)

        html = alice_c.post('/api/code/run/', {
            'language': 'html',
            'code': '<!DOCTYPE html><html><body><table><tr><td>1</td></tr></table></body></html>',
            'test_cases': [{'selector': 'table', 'name': 'has a table'}],
        }, format='json').json()
        self.assertEqual(html['status'], 'SUCCESS')
        self.assertTrue(html['test_results'][0]['passed'])

        alice_c.post('/api/telemetry/log/', {'event_type': 'CODE_RESULT',
                                             'event_data': {'problem_id': 'p1', 'status': 'SUCCESS',
                                                            'passed_count': 1, 'total': 1}}, format='json')
        alice_c.post('/api/telemetry/log/', {'event_type': 'HELP_REQUEST',
                                             'event_data': {'problem_id': 'p1', 'prompt': 'why?'}}, format='json')
        # REGISTER/LOGIN/LOGOUT events are posted by the browser after the auth call
        # returns (AuthContext), not by the server, so only the two workspace events exist.
        logged = InteractionLog.objects.filter(user__username='alice')
        self.assertEqual(logged.count(), 2, 'CODE_RESULT + HELP_REQUEST')
        self.assertTrue(all(e.arm == alice['arm'] for e in logged), 'arm comes from the profile')

        # -------------------------------------------------------------- 4. tutor
        # No API key in tests: the tutor answers from its offline fallback, and the panel
        # must still get every field it renders.
        tutor = alice_c.post('/api/tutor/query/', {'prompt': 'What does a for loop do?',
                                                   'code': 'int main(){}', 'problem_id': 'p1',
                                                   'arm': alice['arm']}, format='json')
        self.assertEqual(tutor.status_code, 200)
        answer = tutor.json()
        for key in ('rag_answer', 'independent_ai_answer', 'direct_answer', 'retrieved_passages',
                    'ai_status', 'model', 'mode'):
            self.assertIn(key, answer)
        self.assertIn(answer['ai_status'], ('live', 'fallback'))
        self.assertIsInstance(answer['independent_ai_answer']['problem_breakdown'], list)

        # ------------------------------------------------------ 5. the pre-test
        papers = alice_c.get('/api/assessment/items/?type=pre').json()
        self.assertEqual(papers['available'], ['pre'])
        self.assertEqual(len(papers['items']), 15)
        self.assertTrue(all('keyed_answer' not in item for item in papers['items']))
        self.assertEqual(alice_c.get('/api/assessment/items/?type=post').status_code, 403)

        # Fetching the pre-test opened her sitting of it. It is a no-AI paper, so the
        # tutor now refuses her everywhere - a second tab on the workspace included.
        self.assertEqual(papers['sitting']['status'], 'open')
        blocked = alice_c.post('/api/tutor/query/', {'prompt': 'help me', 'problem_id': 'p1'}, format='json')
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()['reason'], 'paper_in_progress')

        answers = {i['id']: 'a' for i in papers['items'] if i['type'] == 'concept_mcq'}
        submitted = alice_c.post('/api/assessment/submit/',
                                 {'exam_type': 'pre', 'answers': answers, 'code_answers': {}},
                                 format='json')
        self.assertIn(submitted.status_code, (200, 202))
        result = submitted.json()
        self.assertEqual(result['grading_status'], 'graded')      # inline in tests
        for key in ('submission_id', 'score_pct', 'correct', 'total', 'results'):
            self.assertIn(key, result)
        self.assertEqual(len(result['results']), 15)

        # The poll endpoint the page uses shows the same thing, and only to its owner.
        polled = alice_c.get(f"/api/assessment/submissions/{result['submission_id']}/").json()
        self.assertEqual(polled['score_pct'], result['score_pct'])

        # Submitting closed the sitting: the tutor is back, the paper is now read-only.
        self.assertEqual(alice_c.post('/api/tutor/query/', {'prompt': 'help me', 'problem_id': 'p1'},
                                      format='json').status_code, 200)
        self.assertEqual(alice_c.post('/api/assessment/submit/', {'exam_type': 'pre', 'answers': {}},
                                      format='json').status_code, 409, 'a paper is sat once')
        self.assertEqual(alice_c.get('/api/assessment/items/?type=pre').json()['sitting']['status'], 'completed')

        # ---------------------------------------------- 6. results and progression
        dashboard = alice_c.get('/api/dashboard/').json()
        self.assertEqual(dashboard['assessments']['pre']['latest_score'], result['score_pct'])
        self.assertEqual(dashboard['stats']['help_requests'], 1)
        self.assertEqual(alice_c.get('/api/assessment/items/?type=post').json()['available'], ['pre', 'post'])
        self.assertEqual(alice_c.get('/api/assessment/items/?type=transfer').status_code, 403)

        # ------------------------------------------------------------- 7. profile
        updated = alice_c.patch('/api/accounts/profile/', {'weekly_study_hours': 6}, format='json').json()
        self.assertEqual(updated['weekly_study_hours'], 6)
        # Tutor mode is locked until the last paper is in (ARM_SWITCH_POLICY=after_protocol):
        # Alice has only sat the pre-test, so she stays in her allocated condition.
        other_arm = 'ANSWER_ONLY' if alice['arm'] == 'REASONING_VISIBLE' else 'REASONING_VISIBLE'
        locked = alice_c.patch('/api/accounts/profile/', {'assigned_arm': other_arm}, format='json')
        self.assertEqual(locked.status_code, 400)
        self.assertIn('all four papers', locked.json()['fields']['assigned_arm'])
        self.assertEqual(alice_c.get('/api/accounts/me/').json()['arm_switch_reason'], 'after_protocol')
        # ...and whatever the policy, the arm she was enrolled in is the one of record.
        with override_settings(ARM_SWITCH_POLICY='always'):
            switched = alice_c.patch('/api/accounts/profile/', {'assigned_arm': other_arm}, format='json')
            self.assertEqual(switched.status_code, 200)
            self.assertEqual(switched.json()['enrolled_arm'], alice['arm'], 'the allocation of record is immutable')
            alice_c.patch('/api/accounts/profile/', {'assigned_arm': alice['arm']}, format='json')
        mine = alice_c.get('/api/accounts/my-data/').json()
        self.assertEqual(len(mine['submissions']), 1)

        # ------------------------------------------------------- 8. the teacher
        response = self.register(username='teacher', full_name='Ms Teacher', password=PASSWORD,
                                 role='EXPERT_TEACHER', access_code=STAFF_CODE)
        self.assertEqual(response.status_code, 201, response.content)
        teacher_c = self.client_for(response.json()['token'])

        queue = teacher_c.get('/api/expert/reviews/').json()
        self.assertEqual(len(queue['items_to_review']), 60)
        first = queue['items_to_review'][0]['id']
        rated = teacher_c.post('/api/expert/rating/', {
            'item_id': first,
            'ratings': {'alignment': 4, 'accuracy': 4, 'clarity': 3, 'difficulty': 3, 'answerability': 4},
            'feedback': 'clear',
        }, format='json').json()
        self.assertEqual(rated['i_cvi'], 1.0)

        submissions = teacher_c.get('/api/expert/submissions/').json()['submissions']
        self.assertEqual(len(submissions), 1)
        self.assertEqual(submissions[0]['participant_code'], alice['participant_code'])
        self.assertEqual(submissions[0]['grading_status'], 'graded')
        graded = teacher_c.post('/api/expert/grade/', {'submission_id': submissions[0]['id'],
                                                       'assigned_marks': 70, 'feedback': 'good'},
                                format='json').json()
        self.assertEqual(graded['assigned_marks'], 70)

        certification = teacher_c.get('/api/expert/certification/').json()
        self.assertFalse(certification['ready']['certified'])
        self.assertEqual(certification['content_validity']['summary']['rated_items'], 1)

        # The teacher is not a participant: no study endpoints for researchers.
        self.assertEqual(teacher_c.get('/api/admin/stats/').status_code, 403)

        # ---------------------------------------------------- 9. the researcher
        response = self.register(username='researcher', full_name='Dr R', password=PASSWORD,
                                 role='RESEARCHER_ADMIN', access_code=STAFF_CODE)
        boss_c = self.client_for(response.json()['token'])

        stats = boss_c.get('/api/admin/stats/').json()
        self.assertEqual(stats['total_participants'], 1)
        self.assertEqual(stats['completion']['pre'], 1)
        self.assertIsNone(stats['learning_gain']['p_value'], 'one participant cannot yield a p-value')

        export = boss_c.get('/api/admin/export/')
        lines = [l for l in b''.join(export.streaming_content).decode('utf-8').splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertIn(alice['participant_code'], lines[1])
        self.assertNotIn('Alice', lines[1])
        self.assertNotIn('Dhaka College', lines[1])

        # ----------------------------------------------------------- 10. sign out
        self.assertEqual(alice_c.post('/api/accounts/logout/').status_code, 200)
        self.assertIn(alice_c.get('/api/accounts/me/').status_code, (401, 403))
        login = APIClient().post('/api/accounts/login/', {'identifier': 'alice', 'password': PASSWORD},
                                 format='json')
        self.assertEqual(login.status_code, 200)
        alice_c = self.client_for(login.json()['token'])

        # ---------------------------------------------------------- 11. withdraw
        gone = alice_c.post('/api/accounts/withdraw/', {'password': PASSWORD}, format='json')
        self.assertEqual(gone.status_code, 200)
        self.assertFalse(ExamSubmission.objects.filter(student__username='alice').exists())
        self.assertFalse(InteractionLog.objects.filter(user__username='alice').exists())
        profile = ParticipantProfile.objects.get(participant_code=alice['participant_code'])
        self.assertEqual(profile.full_name, '')
        self.assertEqual(profile.school_name, '')
        self.assertIsNotNone(profile.withdrawn_at)
        self.assertFalse(profile.user.is_active)

        stats = boss_c.get('/api/admin/stats/').json()
        self.assertEqual(stats['total_participants'], 1, 'still enrolled in the denominator')
        self.assertEqual(stats['withdrawn_participants'], 1)
        self.assertEqual(stats['completion']['pre'], 0, 'but with no data')
        lines = [l for l in b''.join(boss_c.get('/api/admin/export/').streaming_content)
                 .decode('utf-8').splitlines() if l.strip()]
        self.assertIn('True', lines[1].split(','), 'withdrawn flag in the export')

        self.assertEqual(APIClient().post('/api/accounts/login/',
                                          {'identifier': 'alice', 'password': PASSWORD},
                                          format='json').status_code, 401)
