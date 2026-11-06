"""Safe configured metadata and response provenance, with every model call mocked."""
import os
from unittest.mock import patch
from django.test import SimpleTestCase
from trace_backend import llm
from trace_backend.test_utils import ApiTestCase
from logging_app.tests import enrol
from assessment import sittings

ENV = {'LLM_PROVIDER': 'openai', 'OPENAI_MODEL': 'primary-model', 'OPENAI_API_KEY': 'private-test-marker',
       'OPENAI_FALLBACK_MODELS': 'backup-model', 'GEMINI_MODEL': 'gemini-primary', 'GEMINI_API_KEY': 'private-gemini-marker',
       'GEMINI_FALLBACK_MODELS': ''}
ANSWER = {'independent_ai_answer': {'chat_answer': 'Mock explanation', 'code_solution': 'int main() {return 0;}'},
          'rag_answer': {}, 'direct_answer': 'Mock answer'}

class PublicModelMetadataTests(SimpleTestCase):
    def test_only_safe_configured_provider_and_model_fields_are_exposed(self):
        with patch.dict(os.environ, ENV):
            metadata = llm.public_metadata()
        self.assertEqual(metadata, {'provider': 'openai', 'primary_model': 'primary-model',
                                   'fallback_models': ['backup-model'], 'configured': True})
        self.assertNotIn('private-test-marker', str(metadata))
        self.assertNotIn('private-gemini-marker', str(metadata))

    def test_gemini_and_unconfigured_providers_use_existing_routing(self):
        with patch.dict(os.environ, {**ENV, 'LLM_PROVIDER': 'gemini', 'GEMINI_FALLBACK_MODELS': 'gemini-backup'}):
            self.assertEqual(llm.public_metadata(), {'provider': 'gemini', 'primary_model': 'gemini-primary',
                                                    'fallback_models': ['gemini-backup'], 'configured': True})
        with patch.dict(os.environ, {**ENV, 'OPENAI_API_KEY': ''}):
            self.assertFalse(llm.public_metadata()['configured'])

class TutorModelMetadataTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user, self.client_ = enrol('model-metadata-student')
        env = patch.dict(os.environ, ENV)
        env.start(); self.addCleanup(env.stop)
        retrieval = patch('tutor.views.rag_engine_instance.retrieve', return_value=[])
        retrieval.start(); self.addCleanup(retrieval.stop)

    def ask(self):
        return self.client_.post('/api/tutor/query/', {'prompt': 'Explain a loop'}, format='json')

    def test_dashboard_model_metadata_changes_even_when_progress_is_cached(self):
        first = self.client_.get('/api/dashboard/').json()['tutor_model']
        self.assertEqual(first['primary_model'], 'primary-model')
        with patch.dict(os.environ, {'LLM_PROVIDER': 'gemini'}):
            response = self.client_.get('/api/dashboard/')
        self.assertEqual(response['X-Trace-Cache'], 'hit')
        self.assertEqual(response.json()['tutor_model']['provider'], 'gemini')
        self.assertEqual(response.json()['tutor_model']['primary_model'], 'gemini-primary')
        self.assertNotIn('private-test-marker', str(response.json()))

    def test_success_reports_the_selected_response_model_in_both_arms(self):
        for arm in ['REASONING_VISIBLE', 'ANSWER_ONLY']:
            profile = self.user.profile; profile.assigned_arm = arm; profile.save()
            with patch('tutor.views.llm.generate_json', return_value=(ANSWER, 'backup-model')):
                response = self.ask()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['model'], 'backup-model')
            self.assertEqual(response.json()['provider'], 'openai')
            self.assertEqual(response.json()['ai_status'], 'live')

    def test_textbook_fallback_does_not_claim_a_provider_generated_an_answer(self):
        with patch('tutor.views.llm.generate_json', side_effect=RuntimeError('offline')):
            response = self.ask()
        self.assertEqual(response.json()['ai_status'], 'fallback')
        self.assertIsNone(response.json()['provider'])

    def test_legacy_cached_response_never_infers_provider_from_current_configuration(self):
        cached = {'parsed': ANSWER, 'model': 'old-response-model', 'ai_status': 'live', 'error': None}
        with patch('tutor.views.tiered_get_or_set', return_value=(cached, 'persistent')):
            response = self.ask().json()
        self.assertEqual(response['model'], 'old-response-model')
        self.assertTrue(response['cached'])
        self.assertIsNone(response['provider'])

    def test_cached_provider_is_preserved_when_configured_provider_changes(self):
        cached = {'parsed': ANSWER, 'model': 'original-gemini', 'provider': 'gemini', 'ai_status': 'live', 'error': None}
        with patch('tutor.views.tiered_get_or_set', return_value=(cached, 'persistent')):
            response = self.ask().json()
        self.assertEqual((response['provider'], response['model']), ('gemini', 'original-gemini'))

    def test_pre_test_gate_still_rejects_without_generating(self):
        sittings.open_paper(self.user, 'pre')
        with patch('tutor.views.llm.generate_json') as generate:
            response = self.ask()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['reason'], 'paper_in_progress')
        generate.assert_not_called()
