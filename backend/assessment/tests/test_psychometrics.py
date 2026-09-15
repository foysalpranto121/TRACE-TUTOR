"""Item certification statistics.

Difficulty, point-biserial and KR-20 are checked against values computed by hand from
small fixed datasets, so a regression is a failing test rather than a wrong number in a
certification report.
"""
import math
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from accounts.models import ParticipantProfile
from assessment import psychometrics
from assessment.models import ExamSubmission, ExpertRating

MCQ = {'id': 'q1', 'type': 'concept_mcq', 'chapter': 'Chapter 5', 'keyed_answer': 'a',
       'question': 'q', 'options': [{'id': 'a', 'text': 'a'}]}


def bank(n=4, exam_type='pre'):
    return {exam_type: [dict(MCQ, id=f'q{i}') for i in range(1, n + 1)]}


class ModifiedKappaTests(SimpleTestCase):
    def test_perfect_agreement_among_many_raters_gives_kappa_near_one(self):
        self.assertAlmostEqual(psychometrics._modified_kappa(1.0, 8), 1.0, places=2)

    def test_kappa_is_below_i_cvi_because_it_removes_chance_agreement(self):
        i_cvi = 0.8
        kappa = psychometrics._modified_kappa(i_cvi, 5)
        self.assertLess(kappa, i_cvi)
        self.assertGreater(kappa, 0)

    def test_chance_correction_bites_harder_with_few_raters(self):
        """Same I-CVI, fewer raters: more of the agreement could be luck, so kappa drops.

        At I-CVI 1.0 kappa is exactly 1 for any rater count, which is why this uses a
        partial-agreement value.
        """
        few = psychometrics._modified_kappa(0.8, 5)
        many = psychometrics._modified_kappa(0.8, 10)
        self.assertLess(few, many)

    def test_kappa_is_undefined_without_raters(self):
        self.assertIsNone(psychometrics._modified_kappa(None, 0))
        self.assertIsNone(psychometrics._modified_kappa(0.8, 0))


class VerdictTests(SimpleTestCase):
    def test_lynn_thresholds(self):
        self.assertEqual(psychometrics.verdict_for(0.80), 'certify')
        self.assertEqual(psychometrics.verdict_for(0.78), 'certify')
        self.assertEqual(psychometrics.verdict_for(0.77), 'revise')
        self.assertEqual(psychometrics.verdict_for(0.60), 'revise')
        self.assertEqual(psychometrics.verdict_for(0.59), 'discard')
        self.assertEqual(psychometrics.verdict_for(None), 'unrated')


class PointBiserialTests(SimpleTestCase):
    def test_a_perfectly_discriminating_item_scores_high(self):
        """Everyone who passed the item has the top total; everyone who failed, the bottom."""
        scores = [1, 1, 0, 0]
        totals = [4, 4, 1, 1]
        self.assertGreater(psychometrics._point_biserial(scores, totals), 0.9)

    def test_a_reversed_item_scores_negative(self):
        scores = [1, 1, 0, 0]
        totals = [1, 1, 4, 4]
        self.assertLess(psychometrics._point_biserial(scores, totals), -0.9)

    def test_matches_a_hand_computed_value(self):
        # scores [1,0,1,0,1,0], totals [5,2,4,3,5,1]
        # M1 = 14/3 = 4.6667, M0 = 6/3 = 2.0, mean = 20/6 = 3.3333
        # population variance = ((1.6667^2)+(1.3333^2)+(0.6667^2)+(0.3333^2)+(1.6667^2)+(2.3333^2))/6
        scores = [1, 0, 1, 0, 1, 0]
        totals = [5, 2, 4, 3, 5, 1]
        mean = sum(totals) / 6
        variance = sum((t - mean) ** 2 for t in totals) / 6
        expected = (14 / 3 - 2.0) / math.sqrt(variance) * math.sqrt(0.5 * 0.5)
        self.assertAlmostEqual(psychometrics._point_biserial(scores, totals), expected, places=10)

    def test_an_item_everyone_passes_has_no_estimate(self):
        self.assertIsNone(psychometrics._point_biserial([1, 1, 1], [3, 3, 3]))

    def test_an_item_nobody_passes_has_no_estimate(self):
        self.assertIsNone(psychometrics._point_biserial([0, 0, 0], [1, 2, 3]))

    def test_identical_totals_give_no_estimate(self):
        self.assertIsNone(psychometrics._point_biserial([1, 0, 1, 0], [2, 2, 2, 2]))


class Kr20Tests(SimpleTestCase):
    def test_matches_a_hand_computed_value(self):
        rows = [
            {'q1': 1, 'q2': 1, 'q3': 1, 'q4': 1},
            {'q1': 1, 'q2': 1, 'q3': 1, 'q4': 0},
            {'q1': 1, 'q2': 1, 'q3': 0, 'q4': 0},
            {'q1': 1, 'q2': 0, 'q3': 0, 'q4': 0},
            {'q1': 0, 'q2': 0, 'q3': 0, 'q4': 0},
        ]
        item_ids = ['q1', 'q2', 'q3', 'q4']
        totals = [4, 3, 2, 1, 0]
        mean = 2.0
        var = sum((t - mean) ** 2 for t in totals) / 4       # sample variance
        pq = sum((p := sum(r[i] for r in rows) / 5) * (1 - p) for i in item_ids)
        expected = (4 / 3) * (1 - pq / var)
        self.assertAlmostEqual(psychometrics.kr20(rows, item_ids), expected, places=10)

    def test_a_consistent_form_scores_higher_than_a_random_one(self):
        item_ids = ['q1', 'q2', 'q3', 'q4']
        consistent = [{k: v for k, v in zip(item_ids, row)} for row in
                      ([1, 1, 1, 1], [1, 1, 1, 0], [1, 1, 0, 0], [1, 0, 0, 0], [0, 0, 0, 0])]
        # Same spread of totals, but which items a student gets right is unrelated to
        # how well they did overall.
        noisy = [{k: v for k, v in zip(item_ids, row)} for row in
                 ([1, 0, 1, 0], [0, 1, 0, 1], [1, 1, 1, 0], [0, 0, 1, 1], [1, 0, 0, 0])]
        self.assertGreater(psychometrics.kr20(consistent, item_ids),
                           psychometrics.kr20(noisy, item_ids))

    def test_too_little_data_yields_nothing(self):
        self.assertIsNone(psychometrics.kr20([], ['q1', 'q2']))
        self.assertIsNone(psychometrics.kr20([{'q1': 1, 'q2': 1}], ['q1', 'q2']))

    def test_no_variance_in_totals_yields_nothing(self):
        rows = [{'q1': 1, 'q2': 0}, {'q1': 1, 'q2': 0}, {'q1': 1, 'q2': 0}]
        self.assertIsNone(psychometrics.kr20(rows, ['q1', 'q2']))


class ItemFlagTests(SimpleTestCase):
    def test_a_good_item_is_not_flagged(self):
        self.assertEqual(psychometrics.item_flags(0.60, 0.40, 30), [])

    def test_difficulty_outside_the_protocol_range_is_flagged(self):
        self.assertIn('too-hard', psychometrics.item_flags(0.10, 0.40, 30))
        self.assertIn('too-easy', psychometrics.item_flags(0.95, 0.40, 30))

    def test_weak_discrimination_is_flagged(self):
        self.assertIn('weak-discrimination', psychometrics.item_flags(0.60, 0.10, 30))

    def test_thin_data_is_reported_rather_than_judged(self):
        flags = psychometrics.item_flags(0.05, 0.01, 2)
        self.assertEqual(flags, ['insufficient-responses'],
                         'an item must not be condemned on two responses')


class ContentValidityTests(TestCase):
    def setUp(self):
        super().setUp()
        patcher = patch('assessment.scoring.load_item_bank', return_value=bank(4))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.experts = [User.objects.create_user(username=f'exp{i}', password='Testpass!2345')
                        for i in range(5)]

    def rate(self, item_id, alignments):
        for expert, score in zip(self.experts, alignments):
            ExpertRating.objects.create(expert_user=expert, item_key=item_id,
                                        alignment_score=score)

    def test_an_unrated_bank_reports_nothing_rather_than_zero(self):
        report = psychometrics.content_validity()
        self.assertIsNone(report['summary']['s_cvi_ave'])
        self.assertEqual(report['summary']['rated_items'], 0)
        self.assertTrue(all(i['verdict'] == 'unrated' for i in report['items']))

    def test_i_cvi_is_the_proportion_rating_the_item_relevant(self):
        self.rate('q1', [4, 4, 3, 2, 1])     # 3 of 5 rate it 3+
        item = next(i for i in psychometrics.content_validity()['items'] if i['item_id'] == 'q1')
        self.assertAlmostEqual(item['i_cvi'], 0.6)
        self.assertEqual(item['verdict'], 'revise')
        self.assertEqual(item['raters'], 5)

    def test_a_unanimously_relevant_item_certifies(self):
        self.rate('q1', [4, 4, 4, 3, 3])
        item = next(i for i in psychometrics.content_validity()['items'] if i['item_id'] == 'q1')
        self.assertEqual(item['i_cvi'], 1.0)
        self.assertEqual(item['verdict'], 'certify')

    def test_an_irrelevant_item_is_marked_for_discard(self):
        self.rate('q1', [1, 1, 2, 2, 1])
        item = next(i for i in psychometrics.content_validity()['items'] if i['item_id'] == 'q1')
        self.assertEqual(item['i_cvi'], 0.0)
        self.assertEqual(item['verdict'], 'discard')

    def test_s_cvi_averages_across_rated_items_only(self):
        self.rate('q1', [4, 4, 4, 4, 4])     # 1.0
        self.rate('q2', [4, 4, 4, 2, 2])     # 0.6
        summary = psychometrics.content_validity()['summary']
        self.assertAlmostEqual(summary['s_cvi_ave'], 0.8)
        self.assertEqual(summary['rated_items'], 2)
        self.assertIs(summary['meets_target'], False)

    def test_s_cvi_ua_counts_only_unanimous_items(self):
        self.rate('q1', [4, 4, 4, 4, 4])
        self.rate('q2', [4, 4, 4, 2, 2])
        self.assertAlmostEqual(psychometrics.content_validity()['summary']['s_cvi_ua'], 0.5)

    def test_meeting_the_target_is_reported(self):
        for item_id in ('q1', 'q2', 'q3', 'q4'):
            self.rate(item_id, [4, 4, 4, 4, 4])
        summary = psychometrics.content_validity()['summary']
        self.assertEqual(summary['s_cvi_ave'], 1.0)
        self.assertIs(summary['meets_target'], True)


class ItemAnalysisTests(TestCase):
    def setUp(self):
        super().setUp()
        patcher = patch('assessment.scoring.load_item_bank', return_value=bank(4))
        patcher.start()
        self.addCleanup(patcher.stop)

    def enrol_with_results(self, username, correct_map, exam_type='pre'):
        user = User.objects.create_user(username=username, password='Testpass!2345')
        ParticipantProfile.objects.create(user=user, role='STUDENT', consent_given=True)
        ExamSubmission.objects.create(
            student=user, exam_type=exam_type, score_pct=0,
            answers={'results': [{'item_id': k, 'correct': v} for k, v in correct_map.items()]})
        return user

    def test_no_pilot_data_reports_nothing(self):
        report = psychometrics.item_analysis('pre')
        self.assertEqual(report['respondents'], 0)
        self.assertIsNone(report['kr20'])
        self.assertTrue(all(i['difficulty'] is None for i in report['items']))

    def test_difficulty_is_the_proportion_answering_correctly(self):
        for i in range(10):
            self.enrol_with_results(f's{i}', {'q1': i < 7, 'q2': True, 'q3': False, 'q4': i < 5})
        items = {i['item_id']: i for i in psychometrics.item_analysis('pre')['items']}
        self.assertAlmostEqual(items['q1']['difficulty'], 0.7)
        self.assertAlmostEqual(items['q2']['difficulty'], 1.0)
        self.assertAlmostEqual(items['q3']['difficulty'], 0.0)

    def test_items_outside_the_difficulty_range_are_flagged(self):
        for i in range(10):
            self.enrol_with_results(f's{i}', {'q1': i < 7, 'q2': True, 'q3': False, 'q4': i < 5})
        items = {i['item_id']: i for i in psychometrics.item_analysis('pre')['items']}
        self.assertEqual(items['q1']['flags'], [])
        self.assertIn('too-easy', items['q2']['flags'])
        self.assertIn('too-hard', items['q3']['flags'])

    def test_only_the_first_submission_of_a_form_counts(self):
        user = self.enrol_with_results('s0', {'q1': False, 'q2': False, 'q3': False, 'q4': False})
        ExamSubmission.objects.create(
            student=user, exam_type='pre', score_pct=100,
            answers={'results': [{'item_id': k, 'correct': True} for k in ('q1', 'q2', 'q3', 'q4')]})
        report = psychometrics.item_analysis('pre')
        self.assertEqual(report['respondents'], 1)
        self.assertEqual(report['items'][0]['difficulty'], 0.0, 'the retake must not count')

    def test_staff_submissions_are_not_pilot_data(self):
        user = User.objects.create_user(username='teacher', password='Testpass!2345')
        ParticipantProfile.objects.create(user=user, role='EXPERT_TEACHER', consent_given=True)
        ExamSubmission.objects.create(
            student=user, exam_type='pre', score_pct=100,
            answers={'results': [{'item_id': 'q1', 'correct': True}]})
        self.assertEqual(psychometrics.item_analysis('pre')['respondents'], 0)


class CertificationReportTests(TestCase):
    def setUp(self):
        super().setUp()
        patcher = patch('assessment.scoring.load_item_bank',
                        return_value={t: [dict(MCQ, id=f'{t}-q{i}') for i in range(1, 3)]
                                      for t in ('pre', 'post', 'transfer', 'withdrawal')})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_untouched_bank_is_not_certified_and_says_why(self):
        report = psychometrics.certification_report()
        self.assertFalse(report['ready']['certified'])
        blockers = ' '.join(report['ready']['blockers'])
        self.assertIn('No expert ratings', blockers)
        self.assertIn('pilot response', blockers)

    def test_the_report_carries_the_protocol_thresholds(self):
        thresholds = psychometrics.certification_report()['thresholds']
        self.assertEqual(thresholds['i_cvi_certify'], 0.78)
        self.assertEqual(thresholds['s_cvi_target'], 0.90)
        self.assertEqual(thresholds['difficulty_range'], [0.30, 0.90])
        self.assertEqual(thresholds['discrimination_min'], 0.20)

    def test_form_equivalence_is_reported_once_there_is_data(self):
        report = psychometrics.certification_report()
        self.assertIn('per_form', report['form_equivalence'])
        self.assertEqual(set(report['form_equivalence']['per_form']),
                         {'pre', 'post', 'transfer', 'withdrawal'})
