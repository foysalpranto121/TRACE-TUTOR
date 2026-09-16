"""Grading is the study's primary outcome measure, so it gets the closest tests.

Code items are graded by compiling and running the submission, which is slow and depends
on a toolchain being installed. Those tests patch the runner and assert on how scoring
interprets its verdict; tutor/tests.py covers the runner itself.
"""
from unittest.mock import patch

from django.test import SimpleTestCase

from assessment import scoring

MCQ = {'id': 'q1', 'type': 'concept_mcq', 'question': 'Which loop runs at least once?',
       'options': [{'id': 'a', 'text': 'while'}, {'id': 'b', 'text': 'do-while'}],
       'keyed_answer': 'b', 'chapter': 'Chapter 5', 'title': 'Loops',
       'curriculum_ref': 'p.146'}
C_ITEM = {'id': 'c1', 'type': 'c_programming', 'question': 'Print the sum.',
          'title': 'Sum', 'chapter': 'Chapter 5',
          'test_cases': [{'input': '2 3', 'output': '5'}],
          'sample_cases': [{'input': '2 3', 'output': '5'}],
          'input_format': 'two ints', 'output_format': 'the sum'}
HTML_ITEM = {'id': 'h1', 'type': 'html_coding', 'question': 'Build a table.',
             'title': 'Table', 'chapter': 'Chapter 4',
             'html_checks': [{'selector': 'table', 'name': 'has a table'}]}


class PublicItemTests(SimpleTestCase):
    """public_item() is the only shape that may cross the wire."""

    def test_mcq_keeps_options_but_drops_the_key(self):
        public = scoring.public_item(MCQ)
        self.assertEqual([o['id'] for o in public['options']], ['a', 'b'])
        self.assertNotIn('keyed_answer', public)

    def test_code_item_drops_test_cases_but_keeps_samples(self):
        public = scoring.public_item(C_ITEM)
        self.assertNotIn('test_cases', public)
        self.assertEqual(public['sample_cases'], C_ITEM['sample_cases'])

    def test_html_item_drops_checks(self):
        self.assertNotIn('html_checks', scoring.public_item(HTML_ITEM))

    def test_no_grading_secret_survives_for_any_item_type(self):
        secrets = ('keyed_answer', 'test_cases', 'html_checks')
        for item in (MCQ, C_ITEM, HTML_ITEM):
            public = scoring.public_item(item)
            for key in secrets:
                self.assertNotIn(key, public, f'{key} leaked from a {item["type"]} item')


class McqGradingTests(SimpleTestCase):
    def test_correct_answer(self):
        self.assertTrue(scoring._grade_mcq(MCQ, {'q1': 'b'})['correct'])

    def test_wrong_answer(self):
        self.assertFalse(scoring._grade_mcq(MCQ, {'q1': 'a'})['correct'])

    def test_answer_matching_is_case_insensitive_and_trimmed(self):
        for given in ('B', ' b ', 'B '):
            self.assertTrue(scoring._grade_mcq(MCQ, {'q1': given})['correct'], given)

    def test_blank_and_missing_count_as_wrong_not_as_errors(self):
        for answers in ({}, {'q1': ''}, {'q1': None}, {'q1': '   '}):
            outcome = scoring._grade_mcq(MCQ, answers)
            self.assertFalse(outcome['correct'])
            self.assertIn('No option selected', outcome['detail'])

    def test_an_answer_for_a_different_item_does_not_count(self):
        self.assertFalse(scoring._grade_mcq(MCQ, {'q2': 'b'})['correct'])


class CodeGradingTests(SimpleTestCase):
    def test_blank_submission_is_wrong_without_invoking_the_compiler(self):
        with patch('tutor.runner.run_code') as run:
            outcome = scoring._grade_code(C_ITEM, {'c1': '   '})
        run.assert_not_called()
        self.assertFalse(outcome['correct'])
        self.assertEqual(outcome['status'], 'NO_ANSWER')

    def test_only_a_full_pass_counts_as_correct(self):
        cases = {
            'SUCCESS': True,
            'WRONG_ANSWER': False,
            'COMPILE_ERROR': False,
            'RUNTIME_ERROR': False,
        }
        for status, expected in cases.items():
            with patch('tutor.runner.run_code', return_value={
                'status': status, 'test_results': [{'passed': expected}], 'passed_count': int(expected),
            }):
                self.assertEqual(scoring._grade_code(C_ITEM, {'c1': 'int main(){}'})['correct'],
                                 expected, status)

    def test_partial_pass_is_reported_but_not_correct(self):
        with patch('tutor.runner.run_code', return_value={
            'status': 'WRONG_ANSWER',
            'test_results': [{'passed': True}, {'passed': False}],
            'passed_count': 1,
        }):
            outcome = scoring._grade_code(C_ITEM, {'c1': 'int main(){}'})
        self.assertFalse(outcome['correct'])
        self.assertEqual((outcome['passed_count'], outcome['total_tests']), (1, 2))

    def test_a_dead_compiler_marks_the_item_wrong_instead_of_raising(self):
        with patch('tutor.runner.run_code', side_effect=OSError('no compiler')):
            outcome = scoring._grade_one(C_ITEM, {}, {'c1': 'int main(){}'})
        self.assertFalse(outcome['correct'])
        self.assertIn('Could not grade', outcome['detail'])


class InfrastructureFailureTests(SimpleTestCase):
    """A runner that could not judge an answer (Docker down, no compiler) must fail the
    whole submission - which makes it retryable - not bank a real-looking zero."""

    def setUp(self):
        patcher = patch('assessment.scoring.load_item_bank', return_value={'pre': [MCQ, C_ITEM]})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_sandbox_outage_fails_the_submission_instead_of_scoring_it(self):
        with patch('tutor.runner.run_code', return_value={'status': 'SANDBOX_UNAVAILABLE', 'test_results': []}):
            with self.assertRaises(scoring.GradingUnavailable):
                scoring.grade_submission('pre', {'q1': 'b'}, {'c1': 'int main(){}'})

    def test_a_grading_exception_also_fails_the_submission(self):
        with patch('tutor.runner.run_code', side_effect=OSError('compiler gone')):
            with self.assertRaises(scoring.GradingUnavailable):
                scoring.grade_submission('pre', {'q1': 'b'}, {'c1': 'int main(){}'})

    def test_a_genuine_wrong_answer_is_still_banked_not_treated_as_an_outage(self):
        with patch('tutor.runner.run_code', return_value={
                'status': 'COMPILE_ERROR', 'test_results': [], 'passed_count': 0}):
            score, correct, total, _ = scoring.grade_submission('pre', {'q1': 'b'}, {'c1': 'bad code'})
        self.assertEqual((correct, total), (1, 2), 'a compile error is a wrong answer, not a failure')
        self.assertEqual(score, 50)


class SubmissionGradingTests(SimpleTestCase):
    def setUp(self):
        self.bank = {'pre': [MCQ, dict(MCQ, id='q2', keyed_answer='a'),
                             dict(MCQ, id='q3', keyed_answer='a')]}
        patcher = patch('assessment.scoring.load_item_bank', return_value=self.bank)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_score_is_a_rounded_percentage(self):
        score, correct, total, _ = scoring.grade_submission(
            'pre', {'q1': 'b', 'q2': 'a', 'q3': 'b'}, {})
        self.assertEqual((correct, total), (2, 3))
        self.assertEqual(score, 67)  # 66.67 rounds to 67

    def test_all_correct_and_all_wrong(self):
        full, _, _, _ = scoring.grade_submission('pre', {'q1': 'b', 'q2': 'a', 'q3': 'a'}, {})
        none, _, _, _ = scoring.grade_submission('pre', {'q1': 'a', 'q2': 'b', 'q3': 'b'}, {})
        self.assertEqual((full, none), (100, 0))

    def test_an_empty_submission_scores_zero_rather_than_failing(self):
        score, correct, total, results = scoring.grade_submission('pre', {}, {})
        self.assertEqual((score, correct, total), (0, 0, 3))
        self.assertEqual(len(results), 3)

    def test_non_dict_answers_are_tolerated(self):
        score, _, _, _ = scoring.grade_submission('pre', 'not-a-dict', None)
        self.assertEqual(score, 0)

    def test_results_carry_one_entry_per_item_in_order(self):
        _, _, _, results = scoring.grade_submission('pre', {'q1': 'b'}, {})
        self.assertEqual([r['item_id'] for r in results], ['q1', 'q2', 'q3'])

    def test_a_client_supplied_score_is_ignored(self):
        """grade_submission derives the score itself; there is no input for a score."""
        score, _, _, _ = scoring.grade_submission('pre', {'q1': 'a', 'score': 100}, {})
        self.assertEqual(score, 0)


class ItemBankTests(SimpleTestCase):
    def test_unknown_exam_type_falls_back_to_pre(self):
        with patch('assessment.scoring.load_item_bank', return_value={'pre': [MCQ]}):
            self.assertEqual([i['id'] for i in scoring.items_for('nonsense')], ['q1'])

    def test_items_without_an_id_are_skipped(self):
        with patch('assessment.scoring.load_item_bank',
                   return_value={'pre': [MCQ, {'type': 'concept_mcq'}, 'garbage']}):
            self.assertEqual([i['id'] for i in scoring.items_for('pre')], ['q1'])

    def test_a_malformed_bank_raises_a_typed_error(self):
        with patch('assessment.scoring.load_item_bank',
                   side_effect=scoring.ItemBankError('bad bank')):
            with self.assertRaises(scoring.ItemBankError):
                scoring.items_for('pre')


class RealItemBankTests(SimpleTestCase):
    """The bank shipped in the repository has to actually be gradeable."""

    def test_every_form_loads_and_every_item_is_well_formed(self):
        bank = scoring.load_item_bank()
        for exam_type in scoring.EXAM_TYPES:
            items = bank.get(exam_type)
            self.assertIsInstance(items, list, f'{exam_type} is missing')
            self.assertTrue(items, f'{exam_type} is empty')
            for item in items:
                self.assertIn('id', item)
                self.assertIn(item['type'], ('concept_mcq', 'c_programming', 'html_coding'),
                              f"{item['id']} has type {item.get('type')}")
                if item['type'] == 'concept_mcq':
                    keys = {o['id'] for o in item.get('options') or []}
                    self.assertIn(item.get('keyed_answer'), keys,
                                  f"{item['id']} keys an answer that is not among its options")

    def test_item_ids_are_unique_across_the_whole_bank(self):
        ids = [item['id'] for _, item in scoring.all_items()]
        duplicates = {i for i in ids if ids.count(i) > 1}
        self.assertEqual(duplicates, set(), f'duplicate item ids: {duplicates}')

    def test_find_item_locates_an_item_and_its_form(self):
        exam_type, item = scoring.find_item(scoring.all_items()[0][1]['id'])
        self.assertIsNotNone(item)
        self.assertIn(exam_type, scoring.EXAM_TYPES)

    def test_find_item_returns_nothing_for_an_unknown_id(self):
        self.assertEqual(scoring.find_item('no-such-item'), (None, None))
