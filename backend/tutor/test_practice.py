"""Practice credit must come from the server's task checks and keep its provenance."""
import hashlib
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from assessment import analytics
from logging_app.models import InteractionLog
from logging_app.tests import enrol
from trace_backend.test_utils import ApiTestCase
from tutor import practice, runner

TABLE_ID = 'prob_html_table_201'
TABLE = ('<!DOCTYPE html><html><head><title>Marks</title></head><body><table>'
         '<tr><th>Roll</th><th>Marks</th></tr><tr><td>101</td><td>85</td></tr>'
         '</table></body></html>')
EMPTY_HTML = '<!DOCTYPE html><html><head><title>Task</title></head><body></body></html>'


class PracticeResultTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('practice-student', arm='ANSWER_ONLY')

    def run_task(self, code=TABLE, **extra):
        return self.client_.post('/api/code/run/', {
            'language': 'html', 'problem_id': TABLE_ID, 'code': code, **extra,
        }, format='json')

    def dashboard(self):
        response = self.client_.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_real_success_is_persisted_before_response_and_invalidates_progress_cache(self):
        self.assertEqual(self.dashboard()['stats']['practice_tasks_passed'], 0)
        response = self.run_task()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'SUCCESS')
        self.assertEqual(response.json()['practice_metric_version'], 2)
        log = InteractionLog.objects.get(event_type='CODE_RESULT')
        self.assertEqual((log.user, log.arm, log.problem_id), (self.user, 'ANSWER_ONLY', TABLE_ID))
        self.assertTrue(practice.is_verified_result(log.problem_id, log.payload))
        self.assertEqual(log.payload['code_sha256'], hashlib.sha256(TABLE.encode()).hexdigest())
        self.assertIn('device_id', log.payload)
        self.assertEqual((log.payload['passed_count'], log.payload['total']), (4, 4))
        body = self.dashboard()
        self.assertEqual(body['stats']['practice_tasks_passed'], 1)
        self.assertTrue(body['problems'][0]['verified_passed'])

    def test_forged_client_verdicts_are_refused(self):
        response = self.client_.post('/api/telemetry/log/', {
            'event_type': 'CODE_RESULT', 'event_data': {
                'problem_id': TABLE_ID, 'status': 'SUCCESS', 'source': practice.RESULT_SOURCE,
                'practice_metric_version': 2, 'catalog_sha256': practice.CATALOG_SHA256,
            },
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(InteractionLog.objects.exists())
        self.assertEqual(self.dashboard()['stats']['practice_tasks_passed'], 0)

    def test_client_checks_cannot_replace_the_task_checks(self):
        response = self.run_task(EMPTY_HTML, test_cases=[{'selector': 'body'}])
        self.assertEqual(response.json()['status'], 'WRONG_ANSWER')
        self.assertEqual(len(response.json()['test_results']), 4)
        self.assertEqual(self.dashboard()['stats']['practice_tasks_passed'], 0)

    def test_syntax_check_and_generic_execution_earn_no_practice_credit(self):
        self.assertEqual(self.run_task(mode='check').json()['status'], 'OK')
        response = self.client_.post('/api/code/run/', {
            'language': 'html', 'code': TABLE, 'test_cases': [{'selector': 'table'}],
        }, format='json')
        self.assertEqual(response.json()['status'], 'SUCCESS')
        self.assertFalse(InteractionLog.objects.exists())
        self.assertEqual(self.dashboard()['stats']['practice_tasks_passed'], 0)

    def test_unknown_ids_wrong_languages_and_invalid_ids_are_rejected(self):
        for fields in ({'problem_id': 'fake'}, {'language': 'python'}, {'problem_id': []}):
            with self.subTest(fields=fields):
                self.assertEqual(self.run_task(**fields).status_code, 400)
        self.assertFalse(InteractionLog.objects.exists())

    def test_repeated_passes_and_later_failures_do_not_change_distinct_completion_count(self):
        self.run_task()
        self.run_task()
        self.run_task(EMPTY_HTML)
        body = self.dashboard()
        self.assertEqual(body['stats']['practice_tasks_passed'], 1)
        self.assertEqual(body['stats']['code_runs'], 3)
        self.assertEqual(sum(day['solved'] for day in body['daily']), 1)
        self.assertTrue(body['problems'][0]['verified_passed'])

    def test_legacy_successes_stay_identifiable_and_are_not_upgraded(self):
        original = {'status': 'SUCCESS', 'problem_id': TABLE_ID, 'passed_count': 4, 'total': 4}
        log = InteractionLog.objects.create(user=self.user, event_type='CODE_RESULT',
                                            problem_id=TABLE_ID, payload=original)
        body = self.dashboard()
        self.assertEqual(body['stats']['problems_solved'], 1)
        self.assertEqual(body['stats']['legacy_tasks_successful'], 1)
        self.assertEqual(body['stats']['practice_tasks_passed'], 0)
        self.assertFalse(body['problems'][0]['verified_passed'])
        log.refresh_from_db()
        self.assertEqual(log.payload, original)
        self.run_task()
        row = analytics.participant_rows()[0]
        self.assertEqual((row['practice_tasks_passed_v2'], row['legacy_tasks_successful']), (1, 1))

    def test_completion_survives_more_than_3000_later_events(self):
        self.run_task()
        InteractionLog.objects.bulk_create([
            InteractionLog(user=self.user, event_type='PING') for _ in range(3001)
        ])
        self.assertEqual(self.dashboard()['stats']['practice_tasks_passed'], 1)

    def test_one_participants_success_never_credits_another(self):
        self.run_task()
        _, other = enrol('other-practice-student')
        self.assertEqual(other.get('/api/dashboard/').json()['stats']['practice_tasks_passed'], 0)

    def test_c_tasks_use_the_server_cases_and_exact_output_matching(self):
        with patch('tutor.views.runner.run_code', return_value={'status': 'WRONG_ANSWER', 'test_results': []}) as run:
            self.client_.post('/api/code/run/', {
                'problem_id': 'prob_c_loop_101', 'language': 'c', 'code': 'int main(){}',
                'test_cases': [{'input': '', 'output': ''}],
            }, format='json')
        self.assertEqual(run.call_args.kwargs['test_cases'], practice.TASKS['prob_c_loop_101']['test_cases'])
        self.assertTrue(run.call_args.kwargs['strict_output'])


@unittest.skipUnless(shutil.which('node'), 'Node is needed to load the actual frontend starters')
@override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=False)
class PracticeStarterTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        result = subprocess.run([
            'node', '--input-type=module', '-e',
            "import {NCTB_PROBLEMS} from './frontend/src/data/problems.js'; process.stdout.write(JSON.stringify(NCTB_PROBLEMS));",
        ], cwd=settings.BASE_DIR.parent, capture_output=True, text=True, encoding='utf-8', check=True)
        cls.problems = json.loads(result.stdout)

    def test_every_unchanged_starter_fails_the_actual_practice_checks(self):
        for problem in self.problems:
            if problem['lang'] == 'c' and not runner._find_c_compiler():
                continue
            with self.subTest(problem=problem['id']):
                result = runner.run_code(problem['lang'], problem['starterCode'],
                                         practice.TASKS[problem['id']]['test_cases'], strict_output=True)
                self.assertEqual(result['status'], 'WRONG_ANSWER', result)
                self.assertEqual(result['passed_count'], 0)

    @unittest.skipUnless(runner._find_c_compiler(), 'no C compiler installed')
    def test_correct_c_passes_but_printing_all_expected_answers_fails(self):
        source = '#include <stdio.h>\nint main(){int n;scanf("%d",&n);printf("Sum = %d\\n",n*(n+1)/2);return 0;}'
        cases = practice.TASKS['prob_c_loop_101']['test_cases']
        self.assertEqual(runner.run_code('c', source, cases, strict_output=True)['status'], 'SUCCESS')
        hardcoded = '#include <stdio.h>\nint main(){puts("Sum = 15 Sum = 55 Sum = 1 Sum = 276");return 0;}'
        self.assertEqual(runner.run_code('c', hardcoded, cases, strict_output=True)['status'], 'WRONG_ANSWER')
