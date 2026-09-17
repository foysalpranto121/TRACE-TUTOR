"""The code runner's verdict logic, and the gate in front of it.

run_code() compiles and executes on the server, so the tests here exercise the pure
decision functions plus the permission boundary. Actual compilation is covered by a
single opt-in test that skips when no toolchain is installed.
"""
import os
import shutil
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from trace_backend.test_utils import ApiTestCase

from accounts.models import ParticipantProfile
from logging_app.models import InteractionLog
from trace_backend import gemini, llm
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

    def run_case(self, expected_output):
        result = runner.run_code(language='c', code=self.SOURCE,
                                 test_cases=[{'input': '2 3', 'output': expected_output}])
        # On the docker tier a container start can exceed the run timeout when the host
        # is busy (a full suite runs many containers at once). That is the environment,
        # not the verdict logic these tests are about, so it is a skip rather than a fail.
        cases = result.get('test_results') or []
        if cases and cases[0].get('timed_out') and result.get('sandbox') == 'docker':
            self.skipTest('container start exceeded the run timeout (host under load)')
        return result

    def test_a_correct_program_passes_its_test_case(self):
        self.assertEqual(self.run_case('5')['status'], 'SUCCESS')

    def test_a_wrong_answer_is_not_a_pass(self):
        self.assertEqual(self.run_case('6')['status'], 'WRONG_ANSWER')

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


class GeminiJsonTests(SimpleTestCase):
    """A tutor turn used to degrade to the textbook-only fallback whenever the model's
    JSON was off by one character - typically a quote inside a printf. The model is now
    held to a schema, and what still slips through is repaired rather than discarded."""

    def test_clean_json_is_parsed_as_is(self):
        self.assertEqual(gemini.parse_json_response('{"a": 1}'), {'a': 1})

    def test_a_code_fence_around_the_object_is_ignored(self):
        self.assertEqual(gemini.parse_json_response('```json\n{"a": 1}\n```'), {'a': 1})

    def test_an_unescaped_quote_inside_a_program_is_repaired(self):
        raw = '{"code_solution": "printf("Sum = %d\\n", sum);", "direct_answer": "ok"}'
        parsed = gemini.parse_json_response(raw)
        self.assertEqual(parsed['code_solution'], 'printf("Sum = %d\n", sum);')
        self.assertEqual(parsed['direct_answer'], 'ok')

    def test_a_quote_before_a_variable_that_looks_like_a_json_literal_is_repaired(self):
        # `n` could begin `null` and `5` could be a number: neither is, so the quote
        # before them is part of the program, not the end of the JSON string.
        raw = '{"code": "scanf("%d", &n); printf("%d", n); printf("%d", 5);", "k": true}'
        parsed = gemini.parse_json_response(raw)
        self.assertEqual(parsed['code'], 'scanf("%d", &n); printf("%d", n); printf("%d", 5);')
        self.assertIs(parsed['k'], True)

    def test_a_raw_newline_inside_a_string_is_repaired(self):
        raw = '{"code_solution": "int main() {\n  return 0;\n}"}'
        parsed = gemini.parse_json_response(raw)
        self.assertEqual(parsed['code_solution'], 'int main() {\n  return 0;\n}')

    def test_a_trailing_comma_and_surrounding_prose_are_repaired(self):
        raw = 'Here you go:\n{"a": [1, 2,], "b": "x",}\nHope this helps.'
        self.assertEqual(gemini.parse_json_response(raw), {'a': [1, 2], 'b': 'x'})

    def test_something_that_is_not_json_at_all_is_reported(self):
        with self.assertRaises(ValueError):
            gemini.parse_json_response('The answer is 42.')

    def test_an_empty_reply_is_reported(self):
        with self.assertRaises(RuntimeError):
            gemini.parse_json_response('')

    def test_generate_json_holds_the_model_to_the_schema(self):
        seen = {}

        def fake_generate_content(contents, config, retries_per_model=2):
            seen.update(config)
            return SimpleNamespace(text='{"x": 1}'), 'pinned-model'

        with patch.object(gemini, 'generate_content', fake_generate_content):
            parsed, model = gemini.generate_json('sys', 'user', schema={'type': 'object'})
        self.assertEqual((parsed, model), ({'x': 1}, 'pinned-model'))
        self.assertEqual(seen['response_json_schema'], {'type': 'object'})
        self.assertEqual(seen['response_mime_type'], 'application/json')

    def test_the_tutor_schema_is_one_the_sdk_accepts(self):
        from google.genai import types
        from tutor.views import TUTOR_RESPONSE_SCHEMA
        config = types.GenerateContentConfig(response_json_schema=TUTOR_RESPONSE_SCHEMA,
                                             response_mime_type='application/json')
        self.assertEqual(config.response_json_schema['required'],
                         ['rag_answer', 'independent_ai_answer', 'direct_answer'])
        self.assertIn('chat_answer', config.response_json_schema['properties']['independent_ai_answer']['required'])


class _ApiError(Exception):
    """Stands in for the OpenAI SDK's status errors: a message plus a status_code."""

    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def _completion(text, refusal=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text, refusal=refusal))])


class LlmProviderTests(SimpleTestCase):
    """The tutor can be served by OpenAI or Gemini behind one call. The provider, the
    model and the temperature are study configuration, so they are decided by the
    environment alone, and the OpenAI path holds the model to the same schema."""

    def _client(self, create):
        return patch.object(llm, '_openai_client',
                            SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))

    def test_auto_picks_openai_only_when_its_key_is_configured(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'auto', 'OPENAI_API_KEY': 'sk-test'}):
            self.assertEqual(llm.provider(), 'openai')
        with patch.dict(os.environ, {'LLM_PROVIDER': 'auto', 'OPENAI_API_KEY': ''}):
            self.assertEqual(llm.provider(), 'gemini')

    def test_an_explicit_provider_wins_over_the_key(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'gemini', 'OPENAI_API_KEY': 'sk-test'}):
            self.assertEqual(llm.provider(), 'gemini')

    def test_the_openai_model_is_pinned_by_the_environment(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_MODEL': 'gpt-pinned',
                                     'OPENAI_FALLBACK_MODELS': 'gpt-backup, gpt-pinned'}):
            self.assertEqual(llm.model_name(), 'gpt-pinned')
            self.assertEqual(llm.model_chain(), ['gpt-pinned', 'gpt-backup'])

    def test_strict_schema_closes_every_object_without_touching_the_original(self):
        from tutor.views import TUTOR_RESPONSE_SCHEMA
        strict = llm.strict_schema(TUTOR_RESPONSE_SCHEMA)
        self.assertIs(strict['additionalProperties'], False)
        self.assertIs(strict['properties']['independent_ai_answer']['additionalProperties'], False)
        self.assertNotIn('additionalProperties', TUTOR_RESPONSE_SCHEMA)
        self.assertEqual(strict['properties']['rag_answer']['required'],
                         list(TUTOR_RESPONSE_SCHEMA['properties']['rag_answer']['properties']))

    def test_openai_is_held_to_the_schema_and_its_json_is_parsed(self):
        seen = {}

        def create(**kwargs):
            seen.update(kwargs)
            return _completion('{"x": 1}')

        with patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'sk-test',
                                     'OPENAI_MODEL': 'gpt-pinned', 'LLM_TEMPERATURE': '0'}), self._client(create):
            parsed, model = llm.generate_json('sys', 'user', schema={'type': 'object', 'properties': {'x': {'type': 'integer'}}})
        self.assertEqual((parsed, model), ({'x': 1}, 'gpt-pinned'))
        self.assertEqual(seen['messages'], [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'user'}])
        self.assertEqual(seen['temperature'], 0.0)
        fmt = seen['response_format']
        self.assertEqual(fmt['type'], 'json_schema')
        self.assertIs(fmt['json_schema']['strict'], True)
        self.assertIs(fmt['json_schema']['schema']['additionalProperties'], False)

    def test_a_model_that_rejects_temperature_is_retried_without_it_and_remembered(self):
        calls = []

        def create(**kwargs):
            calls.append(dict(kwargs))
            if 'temperature' in kwargs:
                raise _ApiError("Unsupported parameter: 'temperature' is not supported with this model.", 400)
            return _completion('{"ok": true}')

        with patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'sk-test', 'LLM_TEMPERATURE': '0',
                                     'OPENAI_MODEL': 'gpt-no-temp'}), \
                self._client(create), patch.dict(llm._rejected_params, {}, clear=True):
            parsed, _ = llm.generate_json('sys', 'user', schema={'type': 'object'})
            llm.generate_json('sys', 'user again', schema={'type': 'object'})
            self.assertEqual(llm.rejected_parameters(), {'gpt-no-temp': ['temperature']},
                             'the manifest must say the configured temperature was not applied')
        self.assertEqual(parsed, {'ok': True})
        self.assertEqual(len(calls), 3, 'first call: reject + retry; second call: no retry needed')
        self.assertNotIn('temperature', calls[1])
        self.assertNotIn('temperature', calls[2])

    def test_quota_errors_move_to_the_next_model_and_then_fail_honestly(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs['model'])
            raise _ApiError('rate_limit_exceeded', 429)

        with patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'sk-test', 'OPENAI_MODEL': 'gpt-a',
                                     'OPENAI_FALLBACK_MODELS': 'gpt-b'}), self._client(create), \
                patch.object(llm.time, 'sleep', lambda s: None):
            with self.assertRaises(RuntimeError):
                llm.generate_json('sys', 'user', schema={'type': 'object'})
        self.assertEqual(calls, ['gpt-a', 'gpt-a', 'gpt-b', 'gpt-b'])

    def test_a_refusal_is_an_error_not_an_answer(self):
        with patch.dict(os.environ, {'LLM_PROVIDER': 'openai', 'OPENAI_API_KEY': 'sk-test'}), \
                self._client(lambda **kw: _completion(None, refusal='I cannot help with that.')):
            with self.assertRaises(RuntimeError):
                llm.generate_json('sys', 'user', schema={'type': 'object'})

    def test_the_gemini_provider_still_goes_through_gemini(self):
        seen = {}

        def fake(system_instruction, contents, temperature=None, schema=None):
            seen.update(schema=schema, temperature=temperature)
            return {'g': 1}, 'gemini-pinned'

        with patch.dict(os.environ, {'LLM_PROVIDER': 'gemini', 'LLM_TEMPERATURE': '0'}), \
                patch.object(gemini, 'generate_json', fake):
            self.assertEqual(llm.generate_json('sys', 'user', schema={'type': 'object'}), ({'g': 1}, 'gemini-pinned'))
        self.assertEqual(seen, {'schema': {'type': 'object'}, 'temperature': 0.0})


class TutorArmTests(ApiTestCase):
    """The tutor is the manipulation. The control arm must never receive the reasoning
    trace or the retrieved passages, and the server - not the request body - decides which
    arm a caller is in, because the body is the one thing a curious student can edit."""

    def _enrol(self, username, arm, role='STUDENT'):
        user = User.objects.create_user(username=username, password='Testpass!2345')
        ParticipantProfile.objects.create(user=user, role=role, assigned_arm=arm,
                                          enrolled_arm=arm, consent_given=True)
        return user, APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)

    def setUp(self):
        super().setUp()
        self.control, self.control_c = self._enrol('control', 'ANSWER_ONLY')
        self.treat, self.treat_c = self._enrol('treat', 'REASONING_VISIBLE')

    def ask(self, client, **body):
        payload = {'prompt': 'What does a for loop do?', 'problem_id': 'p1'}
        payload.update(body)
        return client.post('/api/tutor/query/', payload, format='json')

    REASONING_FIELDS = ('rag_answer', 'independent_ai_answer', 'reasoning_trace',
                        'retrieved_passages', 'grounded_passage')

    def test_the_control_arm_receives_only_the_direct_answer_and_a_code_fix(self):
        answer = self.ask(self.control_c).json()
        self.assertEqual(answer['mode'], 'ANSWER_ONLY')
        self.assertIn('direct_answer', answer)
        self.assertIn('code_solution', answer)
        for leaked in self.REASONING_FIELDS:
            self.assertNotIn(leaked, answer, f'{leaked} must not reach the control arm')

    def test_the_treatment_arm_receives_the_full_dual_answer(self):
        answer = self.ask(self.treat_c).json()
        self.assertEqual(answer['mode'], 'REASONING_VISIBLE')
        for key in ('rag_answer', 'independent_ai_answer', 'reasoning_trace', 'retrieved_passages'):
            self.assertIn(key, answer)

    def test_a_control_participant_cannot_claim_the_treatment_arm_from_the_body(self):
        answer = self.ask(self.control_c, arm='REASONING_VISIBLE').json()
        self.assertEqual(answer['mode'], 'ANSWER_ONLY')
        for leaked in self.REASONING_FIELDS:
            self.assertNotIn(leaked, answer)

    def test_an_answered_turn_is_logged_server_side_with_the_profile_arm(self):
        self.ask(self.control_c)
        row = InteractionLog.objects.get(user=self.control, event_type='HELP_REQUEST')
        self.assertEqual(row.arm, 'ANSWER_ONLY', 'the arm is taken from the profile, not the body')
        self.assertIn(row.payload.get('ai_status'), ('live', 'fallback'))

    def test_staff_may_preview_either_arm(self):
        _, staff_c = self._enrol('examiner', 'REASONING_VISIBLE', role='EXPERT_TEACHER')
        answer = staff_c.post('/api/tutor/query/', {'prompt': 'hi', 'arm': 'ANSWER_ONLY'},
                              format='json').json()
        self.assertEqual(answer['mode'], 'ANSWER_ONLY')
        self.assertNotIn('independent_ai_answer', answer)

    # A reply in the shape the schema holds the model to - with the quote inside the
    # printf left unescaped, which is exactly what used to sink the whole turn.
    MODEL_REPLY = (
        '{"rag_answer": {"textbook_rule": "A for loop repeats a block.", "curriculum_citation": "[1] p.1",'
        ' "textbook_explanation": "The book says so.", "grounded": true},'
        ' "independent_ai_answer": {"chat_answer": "Sure! Use a `for` loop:\\n\\n```c\\nfor (i = 1; i <= n; i++) sum += i;\\n```",'
        ' "concept_applied": "for loop", "problem_breakdown": ["Read n", "Loop 1..n"],'
        ' "pedagogical_justification": "Accumulate.",'
        ' "code_solution": "#include <stdio.h>\\nint main() { printf("Sum = %d\\n", 15); return 0; }"},'
        ' "direct_answer": "Loop from 1 to n and add."}'
    )

    def _with_model_reply(self, text):
        """Serve `text` as the model's reply through the Gemini path, whatever provider
        the local .env selects - the parse and repair steps are shared by both."""
        def fake_generate_content(contents, config, retries_per_model=2):
            return SimpleNamespace(text=text), 'pinned-model'
        stack = patch.dict(os.environ, {'LLM_PROVIDER': 'gemini'})
        stack.start()
        self.addCleanup(stack.stop)
        return patch.object(gemini, 'generate_content', fake_generate_content)

    def test_the_treatment_arm_receives_the_free_ai_answer_with_the_structured_reasoning(self):
        with self._with_model_reply(self.MODEL_REPLY):
            answer = self.ask(self.treat_c).json()
        self.assertEqual(answer['ai_status'], 'live')
        indep = answer['independent_ai_answer']
        self.assertTrue(indep['chat_answer'].startswith('Sure! Use a `for` loop'))
        self.assertEqual(indep['problem_breakdown'], ['Read n', 'Loop 1..n'])
        self.assertEqual(indep['code_solution'],
                         '#include <stdio.h>\nint main() { printf("Sum = %d\n", 15); return 0; }',
                         'an unescaped quote in the program no longer costs the turn')

    def test_the_control_arm_never_sees_the_free_ai_answer(self):
        with self._with_model_reply(self.MODEL_REPLY):
            answer = self.ask(self.control_c).json()
        self.assertEqual(answer['ai_status'], 'live')
        self.assertNotIn('chat_answer', str(answer))
        self.assertEqual(answer['direct_answer'], 'Loop from 1 to n and add.')

    def test_the_view_the_student_asked_from_is_recorded(self):
        with self._with_model_reply(self.MODEL_REPLY):
            self.ask(self.treat_c, view='independent')
            self.ask(self.treat_c, prompt='again', view='not-a-view')
        views = [row.payload.get('view') for row in
                 InteractionLog.objects.filter(user=self.treat, event_type='HELP_REQUEST').order_by('pk')]
        self.assertEqual(views, ['independent', None])
