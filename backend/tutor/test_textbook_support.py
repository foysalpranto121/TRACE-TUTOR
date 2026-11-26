"""Textbook concept coverage through the tutor endpoint, without a database or API calls."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from trace_backend.cache import cache_key
from tutor import views


PASSAGES = [
    {'id': 'loop', 'source_ref': 'NCTB HSC ICT (BV) p.182',
     'chapter': 'C programming', 'passage': 'A for loop initializes, tests, and updates a counter.'},
    {'id': 'multiply', 'source_ref': 'NCTB HSC ICT (BV) p.166',
     'chapter': 'C programming', 'passage': 'The * operator multiplies two operands.'},
]
PROMPT = 'How do I compute the product from 1 to N?'


def model_answer(support='concepts'):
    return {
        'rag_answer': {
            'textbook_rule': 'A for loop repeats statements; * multiplies operands.',
            'curriculum_citation': '[1] NCTB HSC ICT (BV) p.182; [2] NCTB HSC ICT (BV) p.166',
            'textbook_explanation': (
                'Use the loop concepts to visit each value and multiplication to combine values. '
                'The passages explain these concepts but do not give the complete product program.'),
            'support_level': support,
            'grounded': support != 'none',
        },
        'independent_ai_answer': {
            'chat_answer': 'Multiply the integers using an accumulator.',
            'concept_applied': 'Accumulation', 'problem_breakdown': ['Visit each value.'],
            'pedagogical_justification': 'Repeated multiplication builds the product.',
            'code_solution': 'int product = 1;',
        },
        'direct_answer': 'Multiply the integers from 1 to N.',
    }


class TextbookSupportTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(pk=1, is_authenticated=True)
        self.stored = {}
        self.resolve_arm = self.mock('resolve_arm', return_value='REASONING_VISIBLE')
        self.mock('sittings.blocking_paper', return_value=None)
        self.mock('sittings.open_paper_of', return_value=None)
        self.log_event = self.mock('_log_tutor_event')
        self.mock('corpus_version', return_value='textbook-support-corpus')
        self.retrieve = self.mock('rag_engine_instance.retrieve', return_value=deepcopy(PASSAGES))
        self.mock('rag_engine_instance.last_backend', 'vector')
        self.mock('TutorThrottle.allow_request', return_value=True)
        self.generate = self.mock('llm.generate_json', side_effect=lambda *a, **k: (model_answer(), 'test-model'))
        self.mock('llm.provider', return_value='openai')
        self.mock('tiered_get_or_set', side_effect=self.cached_result)

    def mock(self, name, *args, **kwargs):
        patcher = patch('tutor.views.' + name, *args, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def cached_result(self, key, producer, timeout, **kwargs):
        if key in self.stored:
            return deepcopy(self.stored[key]), 'persistent'
        result = producer()
        if kwargs.get('should_store', lambda value: True)(result):
            self.stored[key] = deepcopy(result)
        return result, 'computed'

    def ask(self, **kwargs):
        request = self.factory.post('/api/tutor/query/',
                                    {'prompt': PROMPT, 'language': 'en', **kwargs}, format='json')
        force_authenticate(request, user=self.user)
        response = views.query_tutor(request)
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_related_concepts_are_returned_with_their_citations_without_a_full_solution(self):
        result = self.ask()
        rag = result['rag_answer']
        self.assertEqual(rag['support_level'], 'concepts')
        self.assertTrue(rag['grounded'])
        self.assertIn('visit each value', rag['textbook_explanation'])
        self.assertIn('do not give the complete product program', rag['textbook_explanation'])
        self.assertIn('[2] NCTB', rag['curriculum_citation'])
        self.assertEqual(result['retrieved_passages'], PASSAGES)
        self.assertEqual(self.log_event.call_args.kwargs['support_level'], 'concepts')

    def test_full_support_is_distinct_from_concept_only_support(self):
        self.generate.side_effect = lambda *a, **k: (model_answer('full'), 'test-model')
        rag = self.ask()['rag_answer']
        self.assertEqual(rag['support_level'], 'full')
        self.assertTrue(rag['grounded'])

    def test_unrelated_retrieved_passages_do_not_imply_grounding(self):
        answer = model_answer('none')
        answer['rag_answer']['grounded'] = True
        self.generate.side_effect = lambda *a, **k: (deepcopy(answer), 'test-model')
        rag = self.ask()['rag_answer']
        self.assertEqual(rag['support_level'], 'none')
        self.assertFalse(rag['grounded'])
        self.assertEqual(rag['curriculum_citation'], '')

    def test_empty_retrieval_overrides_a_model_claiming_textbook_support(self):
        self.retrieve.return_value = []
        self.generate.side_effect = lambda *a, **k: (model_answer('full'), 'test-model')
        rag = self.ask()['rag_answer']
        self.assertEqual(rag['support_level'], 'none')
        self.assertFalse(rag['grounded'])
        self.assertEqual(rag['curriculum_citation'], '')
        self.assertNotIn('for loop', rag['textbook_rule'])

    def test_positive_support_requires_a_reference_to_an_actual_supplied_passage(self):
        for citation in ('', '   ', '[0] Missing', '[99] Invented', '[1] Real; [99] Invented'):
            with self.subTest(citation=citation):
                self.stored.clear()
                answer = model_answer()
                answer['rag_answer']['curriculum_citation'] = citation
                self.generate.side_effect = lambda *a, **k: (deepcopy(answer), 'test-model')
                rag = self.ask()['rag_answer']
                self.assertEqual(rag['support_level'], 'none')
                self.assertFalse(rag['grounded'])
                self.assertEqual(rag['curriculum_citation'], '')

    def test_seed_excerpts_are_not_claimed_as_verified_textbook_sources(self):
        self.retrieve.return_value = [
            {**PASSAGES[0], 'id': 'seed_en_01', 'doc': 'seed'},
            {**PASSAGES[1], 'id': 'seed_bn_01', 'doc': 'seed'},
        ]
        rag = self.ask()['rag_answer']
        self.assertEqual(rag['support_level'], 'none')
        self.assertFalse(rag['grounded'])

    def test_missing_or_invalid_coverage_metadata_never_implies_full_support(self):
        for level in (None, 'unknown'):
            for flag in (None, 'true', False, True):
                with self.subTest(level=level, flag=flag):
                    self.stored.clear()
                    answer = model_answer()
                    answer['rag_answer']['support_level'] = level
                    answer['rag_answer']['grounded'] = flag
                    self.generate.side_effect = lambda *a, **k: (deepcopy(answer), 'test-model')
                    rag = self.ask()['rag_answer']
                    self.assertNotIn('support_level', rag)
                    self.assertEqual(rag['grounded'], flag is True)

    def test_old_refusal_cache_is_bypassed_and_the_new_answer_is_shared_across_arms(self):
        legacy_key = cache_key('tutor-answer', 'v5-hint-policy', 'textbook-support-corpus',
                               'en', PROMPT, False, '', '', '', '', '', ['loop', 'multiply'])
        old = model_answer('none')
        old['rag_answer']['textbook_explanation'] = 'The complete answer is not in the passages.'
        self.stored[legacy_key] = {'parsed': old, 'model': 'old-model', 'provider': 'openai',
                                   'ai_status': 'live', 'error': None}
        first = self.ask()
        self.assertEqual(first['rag_answer']['support_level'], 'concepts')
        self.assertFalse(first['cached'])
        second = self.ask()
        self.assertTrue(second['cached'])
        self.assertEqual(second['rag_answer'], first['rag_answer'])
        self.resolve_arm.return_value = 'ANSWER_ONLY'
        control = self.ask()
        self.assertTrue(control['cached'])
        self.assertNotIn('rag_answer', control)
        self.assertNotIn('retrieved_passages', control)
        self.assertNotIn('support_level', control)
        self.assertEqual(control['direct_answer'], first['direct_answer'])
        self.generate.assert_called_once()

    def test_hint_requests_still_suppress_the_textbook_solution_and_grounding_claim(self):
        result = self.ask(prompt='Give me a hint')
        self.assertEqual(result['rag_answer'], {})
        self.assertEqual(result['independent_ai_answer']['code_solution'], '')
        self.assertEqual(result['independent_ai_answer']['problem_breakdown'], [])
        self.assertFalse(self.log_event.call_args.kwargs['grounded'])

    def test_provider_failure_retains_the_passage_and_does_not_cache_the_failure(self):
        self.generate.side_effect = RuntimeError('provider unavailable')
        result = self.ask()
        self.assertEqual(result['ai_status'], 'fallback')
        self.assertIn(PASSAGES[0]['passage'], result['rag_answer']['textbook_explanation'])
        self.assertNotEqual(result['rag_answer'].get('support_level'), 'full')
        self.assertFalse(result['rag_answer']['grounded'])
        self.ask()
        self.assertEqual(self.generate.call_count, 2)
