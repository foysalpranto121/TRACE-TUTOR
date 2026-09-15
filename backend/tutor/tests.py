"""The code runner's verdict logic, and the gate in front of it.

run_code() compiles and executes on the server, so the tests here exercise the pure
decision functions plus the permission boundary. Actual compilation is covered by a
single opt-in test that skips when no toolchain is installed.
"""
import os
import shutil
import unittest

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile
from trace_backend import gemini
from tutor import runner


class JudgeOutputTests(SimpleTestCase):
    def test_exact_match(self):
        self.assertTrue(runner.judge_output('5', '5'))

    def test_surrounding_whitespace_and_newlines_are_ignored(self):
        self.assertTrue(runner.judge_output('5', ' 5\n'))
        self.assertTrue(runner.judge_output('1 2 3', '1\n2\n3\n'))

    def test_an_empty_expectation_accepts_anything(self):
        self.assertTrue(runner.judge_output('', 'whatever'))
        self.assertTrue(runner.judge_output(None, ''))

    def test_wrong_output_fails(self):
        self.assertFalse(runner.judge_output('5', '6'))
        self.assertFalse(runner.judge_output('5', ''))

    def test_expected_output_may_sit_inside_surrounding_prose(self):
        self.assertTrue(runner.judge_output('7', 'The answer is 7'))
        self.assertTrue(runner.judge_output('Sum = 7', 'Result: Sum = 7 (done)'))

    def test_a_longer_number_does_not_satisfy_a_shorter_expectation(self):
        """A substring test graded 17 as a correct answer to an expected 7."""
        self.assertFalse(runner.judge_output('7', '17'))
        self.assertFalse(runner.judge_output('7', '77'))
        self.assertFalse(runner.judge_output('5', '15 25'))

    def test_a_partial_word_does_not_match(self):
        self.assertFalse(runner.judge_output('cat', 'concatenate'))

    def test_multi_token_expectations_must_appear_contiguously_and_in_order(self):
        self.assertTrue(runner.judge_output('1 2', 'x 1 2 y'))
        self.assertFalse(runner.judge_output('1 2', '2 1'))
        self.assertFalse(runner.judge_output('1 2', '1 x 2'))

    def test_matching_is_case_sensitive(self):
        self.assertFalse(runner.judge_output('Hello', 'hello'))


class DiagnosticParsingTests(SimpleTestCase):
    def test_an_error_line_becomes_a_diagnostic(self):
        diags = runner.parse_diagnostics("main.c:4:12: error: expected ';' after expression")
        self.assertEqual(len(diags), 1)
        self.assertEqual((diags[0]['line'], diags[0]['column'], diags[0]['severity']),
                         (4, 12, 'error'))

    def test_fatal_errors_are_reported_as_errors(self):
        diags = runner.parse_diagnostics("main.c:1:10: fatal error: 'stdioo.h' file not found")
        self.assertEqual(diags[0]['severity'], 'error')

    def test_warnings_keep_their_severity(self):
        diags = runner.parse_diagnostics('main.c:7:5: warning: unused variable')
        self.assertEqual(diags[0]['severity'], 'warning')

    def test_several_diagnostics_are_all_captured(self):
        stderr = ('main.c:3:1: error: first\n'
                  'main.c:9:2: warning: second\n'
                  'main.c:12:4: error: third\n')
        self.assertEqual(len(runner.parse_diagnostics(stderr)), 3)

    def test_toolchain_noise_is_filtered_out(self):
        stderr = 'main.c:1:1: warning: argument unused during compilation: -x'
        self.assertEqual(runner.parse_diagnostics(stderr), [])

    def test_empty_and_unparseable_stderr_yield_nothing(self):
        self.assertEqual(runner.parse_diagnostics(''), [])
        self.assertEqual(runner.parse_diagnostics(None), [])
        self.assertEqual(runner.parse_diagnostics('ld: cannot find -lm'), [])


class DiagnosticFlagTests(SimpleTestCase):
    """gcc and clang each reject the other's diagnostic flags outright. The sandbox
    container is gcc; the host is usually zig cc (clang); a lab PC may have MinGW."""

    GCC = ['-fno-diagnostics-show-caret', '-fdiagnostics-color=never']
    CLANG = ['-fno-caret-diagnostics', '-fno-color-diagnostics']

    def test_plain_gcc_and_g_plus_plus(self):
        self.assertEqual(runner._diagnostic_flags(['gcc']), self.GCC)
        self.assertEqual(runner._diagnostic_flags(['g++']), self.GCC)

    def test_a_windows_mingw_override_with_a_full_path(self):
        self.assertEqual(runner._diagnostic_flags([r'C:\mingw64\bin\gcc.exe']), self.GCC)
        self.assertEqual(runner._diagnostic_flags([r'C:\mingw64\bin\G++.EXE']), self.GCC)

    def test_zig_cc_is_clang(self):
        self.assertEqual(runner._diagnostic_flags(['python.exe', '-m', 'ziglang', 'cc']), self.CLANG)
        self.assertEqual(runner._diagnostic_flags(['python.exe', '-m', 'ziglang', 'c++']), self.CLANG)

    def test_plain_clang(self):
        self.assertEqual(runner._diagnostic_flags(['clang']), self.CLANG)
        self.assertEqual(runner._diagnostic_flags(['/usr/bin/clang++']), self.CLANG)


class RunCodeGuardTests(SimpleTestCase):
    def test_an_unsupported_language_is_reported_not_executed(self):
        result = runner.run_code(language='rust', code='fn main(){}')
        self.assertEqual(result['status'], 'UNSUPPORTED')

    def test_empty_source_is_a_compile_error(self):
        result = runner.run_code(language='c', code='   ')
        self.assertEqual(result['status'], 'COMPILE_ERROR')
        self.assertIn('empty', result['diagnostics'][0]['message'].lower())

    def test_output_is_clipped_to_a_bounded_size(self):
        clipped = runner._clip('x' * (runner.MAX_OUTPUT_CHARS + 500))
        self.assertLess(len(clipped), runner.MAX_OUTPUT_CHARS + 100)
        self.assertIn('truncated', clipped)


class HtmlCheckingTests(SimpleTestCase):
    def test_valid_html_passes_the_default_check(self):
        html = '<!DOCTYPE html><html><head><title>t</title></head><body><p>hi</p></body></html>'
        result = runner.run_code(language='html', code=html)
        self.assertIn(result['status'], ('SUCCESS', 'WRONG_ANSWER'))
        self.assertEqual([d for d in result['diagnostics'] if d['severity'] == 'error'], [])

    def test_a_selector_check_detects_a_missing_element(self):
        html = '<!DOCTYPE html><html><body><p>no table here</p></body></html>'
        result = runner.run_code(language='html', code=html,
                                 test_cases=[{'selector': 'table', 'name': 'has a table'}])
        self.assertFalse(result['test_results'][0]['passed'])

    def test_a_selector_check_detects_a_present_element(self):
        html = '<!DOCTYPE html><html><body><table><tr><td>1</td></tr></table></body></html>'
        result = runner.run_code(language='html', code=html,
                                 test_cases=[{'selector': 'table', 'name': 'has a table'}])
        self.assertTrue(result['test_results'][0]['passed'])

    def test_check_mode_validates_without_running_the_checks(self):
        result = runner.run_code(language='html', code='<p>hi</p>', mode='check')
        self.assertIn(result['status'], ('OK', 'COMPILE_ERROR'))
        self.assertEqual(result['test_results'], [])


class PythonCheckingTests(SimpleTestCase):
    def test_a_syntax_error_is_reported_with_a_line_number(self):
        result = runner.run_code(language='python', code='def broken(\n', mode='check')
        self.assertEqual(result['status'], 'COMPILE_ERROR')
        self.assertTrue(result['diagnostics'])
        self.assertGreaterEqual(result['diagnostics'][0]['line'], 1)

    def test_valid_python_passes_the_syntax_check(self):
        result = runner.run_code(language='python', code='print(1 + 1)\n', mode='check')
        self.assertEqual(result['status'], 'OK')


@unittest.skipUnless(runner._find_c_compiler(), 'no C toolchain available')
class CompilerIntegrationTests(SimpleTestCase):
    """Opt-in: actually compiles. Skipped when no toolchain is installed."""

    SOURCE = '#include <stdio.h>\nint main(){int a,b;scanf("%d %d",&a,&b);printf("%d\\n",a+b);return 0;}'

    def test_a_correct_program_passes_its_test_case(self):
        result = runner.run_code(language='c', code=self.SOURCE,
                                 test_cases=[{'input': '2 3', 'output': '5'}])
        self.assertEqual(result['status'], 'SUCCESS')

    def test_a_wrong_answer_is_not_a_pass(self):
        result = runner.run_code(language='c', code=self.SOURCE,
                                 test_cases=[{'input': '2 3', 'output': '6'}])
        self.assertEqual(result['status'], 'WRONG_ANSWER')

    def test_a_compile_error_is_reported_with_diagnostics(self):
        result = runner.run_code(language='c', code='int main(){ return }')
        self.assertEqual(result['status'], 'COMPILE_ERROR')
        self.assertTrue(any(d['severity'] == 'error' for d in result['diagnostics']))


class CodeEndpointPermissionTests(ApiTestCase):
    """The runner executes submitted code as the server user; it must stay behind a login."""

    def setUp(self):
        super().setUp()
        user = User.objects.create_user(username='stu', password='Testpass!2345')
        ParticipantProfile.objects.create(user=user, role='STUDENT', consent_given=True)
        self.client_ = APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)

    def test_anonymous_callers_cannot_execute_code(self):
        response = APIClient().post('/api/code/run/',
                                    {'language': 'c', 'code': 'int main(){}'}, format='json')
        self.assertIn(response.status_code, (401, 403))

    def test_anonymous_callers_cannot_query_the_tutor(self):
        response = APIClient().post('/api/tutor/query/', {'prompt': 'hello'}, format='json')
        self.assertIn(response.status_code, (401, 403))

    def test_anonymous_callers_cannot_read_compiler_status(self):
        self.assertIn(APIClient().get('/api/code/status/').status_code, (401, 403))

    def test_an_authenticated_participant_can_read_compiler_status(self):
        self.assertEqual(self.client_.get('/api/code/status/').status_code, 200)

    def test_the_tutor_requires_a_prompt(self):
        response = self.client_.post('/api/tutor/query/', {'prompt': '   '}, format='json')
        self.assertEqual(response.status_code, 400)


class ModelConfigTests(SimpleTestCase):
    """The tutor is the manipulation, so its generation settings are study-critical."""

    def setUp(self):
        super().setUp()
        self._saved = {k: os.environ.get(k) for k in
                       ('GEMINI_FALLBACK_MODELS', 'GEMINI_TEMPERATURE', 'GEMINI_MODEL')}
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_no_fallback_models_by_default(self):
        """A participant served by a different model than the cohort is a confound."""
        os.environ.pop('GEMINI_FALLBACK_MODELS', None)
        os.environ['GEMINI_MODEL'] = 'pinned-model'
        self.assertEqual(gemini.model_chain(), ['pinned-model'])

    def test_fallbacks_are_opt_in(self):
        os.environ['GEMINI_MODEL'] = 'pinned-model'
        os.environ['GEMINI_FALLBACK_MODELS'] = 'backup-a, backup-b'
        self.assertEqual(gemini.model_chain(), ['pinned-model', 'backup-a', 'backup-b'])

    def test_a_model_is_never_listed_twice(self):
        os.environ['GEMINI_MODEL'] = 'pinned-model'
        os.environ['GEMINI_FALLBACK_MODELS'] = 'pinned-model,backup-a'
        self.assertEqual(gemini.model_chain(), ['pinned-model', 'backup-a'])

    def test_generation_is_deterministic_by_default(self):
        os.environ.pop('GEMINI_TEMPERATURE', None)
        self.assertEqual(gemini.generation_temperature(), 0.0)

    def test_temperature_is_configurable_but_must_be_deliberate(self):
        os.environ['GEMINI_TEMPERATURE'] = '0.7'
        self.assertEqual(gemini.generation_temperature(), 0.7)

    def test_an_unparseable_temperature_falls_back_to_zero(self):
        os.environ['GEMINI_TEMPERATURE'] = 'warm'
        self.assertEqual(gemini.generation_temperature(), 0.0)
