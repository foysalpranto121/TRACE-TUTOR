"""Real code API regression checks. Run only in the intended Docker environment."""
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from accounts.models import ParticipantProfile
from trace_backend.test_utils import ApiTestCase
from tutor import sandbox

C_SUM = '#include <stdio.h>\nint main(){int n; if(scanf("%d",&n)!=1)return 2; printf("%d\\n",n*(n+1)/2);return 0;}'

class RealCodeApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        user = User.objects.create_user(username='disposable-code-teacher')
        ParticipantProfile.objects.create(user=user, role='EXPERT_TEACHER')
        self.client = APIClient()
        self.client.force_authenticate(user=user)
        self.assertEqual(sandbox.status()['tier'], sandbox.DOCKER)
        self.assertTrue(sandbox.status()['enforced'])

    def execute(self, code, **fields):
        response = self.client.post('/api/code/run/', {'language': 'c', 'code': code, **fields}, format='json')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_valid_c_uses_real_stdin_and_stdout(self):
        result = self.execute(C_SUM, test_cases=[{'input': '5', 'output': '15'}, {'input': '10', 'output': '55'}])
        self.assertEqual(result['sandbox'], 'docker')
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual([r['actual'] for r in result['test_results']], ['15', '55'])
        self.assertEqual(result['passed_count'], 2)

    def test_compile_error_has_diagnostics(self):
        result = self.execute('int main(){ this is not C; }')
        self.assertEqual(result['status'], 'COMPILE_ERROR')
        self.assertTrue(any(d['severity'] == 'error' for d in result['diagnostics']))

    def test_nonzero_program_exit_is_a_runtime_error(self):
        result = self.execute('int main(){return 7;}')
        self.assertEqual(result['status'], 'RUNTIME_ERROR')
        self.assertEqual(result['test_results'][0]['exit_code'], 7)

    def test_real_infinite_loop_is_timed_out(self):
        result = self.execute('int main(){while(1){}return 0;}')
        self.assertEqual(result['status'], 'RUNTIME_ERROR')
        self.assertTrue(result['test_results'][0]['timed_out'])
        self.assertIn('Time limit exceeded', result['test_results'][0]['stderr'])

    def test_malformed_requests_return_validation_errors(self):
        invalid = [[], {'code': 123}, {'language': [], 'code': C_SUM}, {'code': C_SUM, 'mode': 'unknown'},
                   {'code': C_SUM, 'test_cases': {}}, {'code': C_SUM, 'test_cases': [None]},
                   {'code': C_SUM, 'test_cases': [{'input': 5}]},
                   {'code': C_SUM, 'test_cases': [{'output': []}]}]
        for body in invalid:
            with self.subTest(body=body):
                response = self.client.post('/api/code/run/', body, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('error', response.json())

    def test_anonymous_code_execution_is_denied(self):
        self.assertIn(APIClient().post('/api/code/run/', {'language': 'c', 'code': C_SUM}, format='json').status_code, (401, 403))
