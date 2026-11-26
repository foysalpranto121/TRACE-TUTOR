"""Textbook support means a cited concept and one question, never a worked solution."""
import json
import math

from django.test import SimpleTestCase

from tutor.test_coaching import CoachingEndpointHarness, PASSAGES, POISONS, selection


class TextbookSupportTests(CoachingEndpointHarness, SimpleTestCase):
    def test_related_textbook_concepts_have_citations_and_the_same_single_learning_question(self):
        self.generate.side_effect = lambda *a, **k: (selection(passage_indices=[1, 2]), 'test-model')
        result = self.ask()
        rag = result['rag_answer']
        self.assertEqual(rag['support_level'], 'concepts')
        self.assertIs(rag['grounded'], True)
        self.assertEqual(rag['textbook_rule'], result['coaching']['concept'])
        self.assertEqual(rag['textbook_explanation'], result['coaching']['question'])
        self.assertEqual(rag['textbook_explanation'].count('?'), 1)
        self.assertEqual(rag['curriculum_citation'],
                         '[1] NCTB HSC ICT (BV) p.182; [2] NCTB HSC ICT (BV) p.166')
        self.assertEqual(self.log_event.call_args.kwargs['support_level'], 'concepts')
        self.assertIs(self.log_event.call_args.kwargs['grounded'], True)
        self.assert_guided(result)

    def test_only_safe_bibliography_is_returned_even_when_passages_contain_a_complete_solution(self):
        self.retrieve.return_value = [{**PASSAGES[0], 'passage': '\n'.join(POISONS)}]
        result = self.ask()
        self.assert_guided(result)
        self.assert_no_answer_leak(result)
        self.assertEqual(result['retrieved_passages'], [
            {'id': 'source-1', 'source_ref': 'NCTB HSC ICT (BV) p.182', 'similarity_score': 0.8}])
        self.assertEqual(result['grounded_passage'], '')

    def test_an_exact_worked_example_does_not_unlock_full_support_or_an_answer(self):
        self.retrieve.return_value[0]['passage'] = POISONS[1]
        result = self.ask()
        self.assertEqual(result['rag_answer']['support_level'], 'concepts')
        self.assertEqual(result['rag_answer']['textbook_explanation'], result['direct_answer'])
        self.assert_no_answer_leak(result)
        self.assert_guided(result)

    def test_empty_retrieval_never_claims_support_but_still_offers_a_learning_question(self):
        self.retrieve.return_value = []
        self.generate.side_effect = lambda *a, **k: (selection(passage_indices=[1, 2]), 'test-model')
        result = self.ask()
        self.assertEqual(result['rag_answer'], {})
        self.assertEqual(result['retrieved_passages'], [])
        self.assertFalse(self.log_event.call_args.kwargs['grounded'])
        self.assert_guided(result)

    def test_retrieval_alone_does_not_claim_support_when_the_selector_does_not_cite_it(self):
        self.generate.side_effect = lambda *a, **k: (selection(passage_indices=[]), 'test-model')
        result = self.ask()
        self.assertEqual(result['rag_answer'], {})
        self.assertFalse(self.log_event.call_args.kwargs['grounded'])
        self.assert_guided(result)

    def test_malformed_and_out_of_range_citations_are_ignored_instead_of_becoming_support(self):
        for indices in (None, '1', [0, 99], [-1, True], ['1', 1.0], [None, {}]):
            with self.subTest(indices=indices):
                self.stored.clear()
                self.generate.side_effect = lambda *a, **k: (selection(passage_indices=indices), 'test-model')
                result = self.ask()
                self.assertEqual(result['rag_answer'], {})
                self.assertFalse(self.log_event.call_args.kwargs['grounded'])
                self.assert_guided(result)

    def test_duplicate_citations_are_not_repeated_and_only_two_passages_can_be_selected(self):
        self.generate.side_effect = lambda *a, **k: (selection(passage_indices=[1, 1]), 'test-model')
        result = self.ask()
        self.assertEqual(result['rag_answer']['curriculum_citation'].count('[1]'), 1)
        self.stored.clear()
        self.retrieve.return_value.append({**PASSAGES[0], 'id': 'third', 'page': 194})
        self.generate.side_effect = lambda *a, **k: (selection(passage_indices=[1, 2, 3]), 'test-model')
        citation = self.ask()['rag_answer']['curriculum_citation']
        self.assertIn('[1]', citation)
        self.assertIn('[2]', citation)
        self.assertNotIn('[3]', citation)

    def test_seed_and_empty_excerpts_are_not_claimed_as_textbook_evidence(self):
        for replacements in ({'id': 'seed_bn_01'}, {'doc': 'seed'}, {'passage': '   '}):
            with self.subTest(passage=replacements):
                self.stored.clear()
                self.retrieve.return_value = [{**PASSAGES[0], **replacements}]
                result = self.ask()
                self.assertEqual(result['rag_answer'], {})
                self.assertFalse(self.log_event.call_args.kwargs['grounded'])
                self.assert_guided(result)
                if 'id' in replacements or 'doc' in replacements:
                    self.assertEqual(result['retrieved_passages'], [])

    def test_a_seed_before_a_real_passage_does_not_shift_the_real_citation_or_source_id(self):
        self.retrieve.return_value = [
            {**PASSAGES[0], 'id': 'seed_bn_01', 'doc': 'seed'}, PASSAGES[1],
        ]
        self.generate.side_effect = lambda *a, **k: (selection(passage_indices=[2]), 'test-model')
        result = self.ask()
        self.assertEqual(result['rag_answer']['curriculum_citation'], '[2] NCTB HSC ICT (BV) p.166')
        self.assertEqual(result['retrieved_passages'], [
            {'id': 'source-2', 'source_ref': 'NCTB HSC ICT (BV) p.166', 'similarity_score': 0.7}])
        self.assert_guided(result)

    def test_source_labels_are_rebuilt_without_poisoned_ids_chapters_or_free_text(self):
        self.retrieve.return_value = [{**PASSAGES[0], 'id': POISONS[0],
                                       'source_ref': POISONS[1], 'chapter': POISONS[2],
                                       'topic': POISONS[3], 'page': 175}]
        result = self.ask()
        self.assertEqual(result['rag_answer']['curriculum_citation'], '[1] NCTB HSC ICT p.175')
        self.assert_no_answer_leak(result)
        self.assert_guided(result)

    def test_bad_similarity_metadata_cannot_put_nonfinite_values_or_text_in_the_response(self):
        for score in (float('nan'), float('inf'), -5, 10, POISONS[0], {}):
            with self.subTest(score=score):
                self.stored.clear()
                self.retrieve.return_value = [{**PASSAGES[0], 'similarity_score': score}]
                result = self.ask()
                actual = result['retrieved_passages'][0]['similarity_score']
                self.assertTrue(math.isfinite(actual))
                self.assertGreaterEqual(actual, 0)
                self.assertLessEqual(actual, 1)
                self.assert_no_answer_leak(result)
                json.dumps(result, allow_nan=False)

    def test_hint_requests_keep_concept_support_but_only_one_question_in_either_language(self):
        for language, prompt in (('en', 'Give me a hint'), ('bn', 'একটি ইঙ্গিত দাও')):
            with self.subTest(language=language):
                result = self.ask(prompt=prompt, language=language)
                self.assert_guided(result)
                self.assertEqual(result['rag_answer']['textbook_explanation'], result['direct_answer'])
                self.assertEqual(result['direct_answer'].count('?'), 1)
                self.assert_no_answer_leak(result)

    def test_provider_failure_uses_safe_uncited_coaching_instead_of_an_excerpt(self):
        self.generate.side_effect = RuntimeError(POISONS[0])
        result = self.ask()
        self.assertEqual(result['ai_status'], 'fallback')
        self.assertEqual(result['rag_answer'], {})
        self.assertFalse(self.log_event.call_args.kwargs['grounded'])
        self.assert_guided(result)
        self.assert_no_answer_leak(result)
        self.assertNotIn(PASSAGES[0]['passage'], json.dumps(result))
        self.ask()
        self.assertEqual(self.generate.call_count, 2)
        self.assertEqual(self.stored, {})
