"""The study statistics, and the guarantee that nothing is ever invented.

The t-distribution p-values are checked against published t-table critical values, so a
regression in the incomplete-beta implementation shows up as a failing test rather than
as a wrong p-value in a paper.
"""
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from accounts.models import ParticipantProfile
from assessment import analytics
from assessment.models import ExamSubmission
from logging_app.models import InteractionLog


class TDistributionTests(SimpleTestCase):
    def test_p_values_match_published_t_tables(self):
        # (t, df, two-tailed p) from standard tables.
        for t, df, expected in [
            (2.228, 10, 0.050),
            (3.169, 15, 0.0064),
            (2.000, 10, 0.0734),
            (1.000, 1, 0.5000),
            (1.960, 1e6, 0.0500),
        ]:
            got = analytics.two_tailed_t_p_value(t, df)
            self.assertAlmostEqual(got, expected, delta=0.001, msg=f't={t}, df={df}')

    def test_zero_t_is_certainly_not_significant(self):
        self.assertAlmostEqual(analytics.two_tailed_t_p_value(0.0, 5), 1.0, places=6)

    def test_p_value_is_symmetric_in_the_sign_of_t(self):
        self.assertAlmostEqual(analytics.two_tailed_t_p_value(2.5, 12),
                               analytics.two_tailed_t_p_value(-2.5, 12), places=12)

    def test_p_value_always_lies_in_the_unit_interval(self):
        for t in (0.0, 0.5, 2.0, 10.0, 1e6):
            for df in (1, 2, 30, 5000):
                p = analytics.two_tailed_t_p_value(t, df)
                self.assertGreaterEqual(p, 0.0)
                self.assertLessEqual(p, 1.0)

    def test_incomplete_beta_endpoints(self):
        self.assertEqual(analytics.regularized_incomplete_beta(2, 3, 0.0), 0.0)
        self.assertEqual(analytics.regularized_incomplete_beta(2, 3, 1.0), 1.0)

    def test_incomplete_beta_matches_a_closed_form_case(self):
        # I_x(1, 1) == x.
        for x in (0.25, 0.5, 0.75):
            self.assertAlmostEqual(analytics.regularized_incomplete_beta(1, 1, x), x, places=10)


class DescriptiveTests(SimpleTestCase):
    def test_describe_reports_n_mean_and_sample_sd(self):
        # Sample SD of [2,4,4,4,5,5,7,9] is 2.1381 (n-1 denominator).
        d = analytics.describe([2, 4, 4, 4, 5, 5, 7, 9])
        self.assertEqual(d['n'], 8)
        self.assertAlmostEqual(d['mean'], 5.0, places=4)
        self.assertAlmostEqual(d['sd'], 2.1381, places=3)

    def test_a_single_value_has_no_standard_deviation(self):
        self.assertEqual(analytics.describe([7]), {'n': 1, 'mean': 7.0, 'sd': None})

    def test_empty_group_yields_nothing_rather_than_zero(self):
        self.assertEqual(analytics.describe([]), {'n': 0, 'mean': None, 'sd': None})

    def test_nones_are_dropped_not_counted(self):
        self.assertEqual(analytics.describe([1, None, 3])['n'], 2)


class CompareArmsTests(SimpleTestCase):
    def test_welch_and_cohens_d_on_a_worked_example(self):
        result = analytics.compare_arms([27, 20, 22, 24, 23, 18, 25, 26],
                                        [18, 15, 20, 17, 19, 14, 16, 21])
        self.assertAlmostEqual(result['mean_difference'], 5.625, places=3)
        self.assertAlmostEqual(result['t_statistic'], 4.0717, places=3)
        self.assertAlmostEqual(result['cohens_d'], 2.0359, places=3)
        self.assertLess(result['p_value'], 0.01)
        self.assertIsNone(result['note'])

    def test_identical_groups_give_no_difference_and_no_effect(self):
        result = analytics.compare_arms([1, 2, 3, 4], [1, 2, 3, 4])
        self.assertEqual(result['mean_difference'], 0.0)
        self.assertAlmostEqual(result['p_value'], 1.0, places=6)
        self.assertEqual(result['cohens_d'], 0.0)

    def test_too_few_participants_reports_a_note_and_no_numbers(self):
        result = analytics.compare_arms([5], [3, 4])
        self.assertIsNone(result['p_value'])
        self.assertIsNone(result['cohens_d'])
        self.assertIsNone(result['t_statistic'])
        self.assertIn('at least two', result['note'])

    def test_an_empty_arm_reports_a_note_and_no_numbers(self):
        result = analytics.compare_arms([], [])
        self.assertIsNone(result['p_value'])
        self.assertEqual(result['treatment']['n'], 0)
        self.assertIsNotNone(result['note'])

    def test_two_constant_arms_are_not_testable(self):
        result = analytics.compare_arms([5, 5, 5], [5, 5, 5])
        self.assertIsNone(result['p_value'])
        self.assertIn('constant', result['note'])

    def test_descriptives_are_present_even_when_the_test_cannot_run(self):
        result = analytics.compare_arms([5], [])
        self.assertEqual(result['treatment'], {'n': 1, 'mean': 5.0, 'sd': None})


class NormalizedGainTests(SimpleTestCase):
    def test_hake_gain(self):
        self.assertEqual(analytics.normalized_gain(40, 70), 0.5)
        self.assertEqual(analytics.normalized_gain(50, 100), 1.0)
        self.assertEqual(analytics.normalized_gain(40, 40), 0.0)

    def test_a_drop_gives_a_negative_gain(self):
        self.assertLess(analytics.normalized_gain(60, 40), 0)

    def test_undefined_at_a_ceiling_pre_test(self):
        self.assertIsNone(analytics.normalized_gain(100, 100))

    def test_undefined_when_either_score_is_missing(self):
        self.assertIsNone(analytics.normalized_gain(None, 70))
        self.assertIsNone(analytics.normalized_gain(40, None))


class ParticipantRowTests(TestCase):
    def setUp(self):
        self.student = self._enrol('alice', 'REASONING_VISIBLE')

    def _enrol(self, username, arm, role='STUDENT'):
        user = User.objects.create_user(username=username, password='Testpass!2345')
        ParticipantProfile.objects.create(user=user, role=role, assigned_arm=arm, consent_given=True)
        return user

    def test_a_participant_with_no_data_yields_nulls_not_zeros(self):
        row = analytics.participant_rows()[0]
        self.assertIsNone(row['pre'])
        self.assertIsNone(row['normalized_gain'])
        self.assertIsNone(row['withdrawal_drop'])
        self.assertEqual(row['help_requests'], 0)

    def test_scores_gain_and_drop_are_derived_from_submissions(self):
        for exam_type, score in (('pre', 40), ('post', 70), ('withdrawal', 55)):
            ExamSubmission.objects.create(student=self.student, exam_type=exam_type,
                                          score_pct=score, answers={})
        row = analytics.participant_rows()[0]
        self.assertEqual((row['pre'], row['post'], row['withdrawal']), (40, 70, 55))
        self.assertEqual(row['normalized_gain'], 0.5)
        self.assertEqual(row['withdrawal_drop'], -15)

    def test_the_first_submission_counts_and_retakes_are_only_tallied(self):
        for score in (40, 90, 95):
            ExamSubmission.objects.create(student=self.student, exam_type='pre',
                                          score_pct=score, answers={})
        row = analytics.participant_rows()[0]
        self.assertEqual(row['pre'], 40, 'a retake must not overwrite the protocol attempt')
        self.assertEqual(row['pre_attempts'], 3)

    def test_event_counts_come_from_the_telemetry_table(self):
        for event in ('HELP_REQUEST', 'HELP_REQUEST', 'CODE_RESULT', 'COPY_PASTE'):
            InteractionLog.objects.create(user=self.student, event_type=event, payload={})
        row = analytics.participant_rows()[0]
        self.assertEqual((row['help_requests'], row['code_runs'], row['copy_paste']), (2, 1, 1))

    def test_staff_accounts_are_not_participants(self):
        self._enrol('boss', 'REASONING_VISIBLE', role='RESEARCHER_ADMIN')
        self.assertEqual([r['participant_code'] for r in analytics.participant_rows()],
                         [self.student.profile.participant_code])

    def test_rows_identify_people_by_participant_code_only(self):
        row = analytics.participant_rows()[0]
        self.assertTrue(row['participant_code'].startswith('TT-'))
        self.assertNotIn('alice', str(row.values()))
        self.assertNotIn('username', row)


class StudyStatsTests(TestCase):
    def _enrol(self, username, arm, scores):
        user = User.objects.create_user(username=username, password='Testpass!2345')
        ParticipantProfile.objects.create(user=user, role='STUDENT', assigned_arm=arm,
                                          consent_given=True)
        for exam_type, score in scores.items():
            ExamSubmission.objects.create(student=user, exam_type=exam_type,
                                          score_pct=score, answers={})
        return user

    def test_an_empty_study_reports_zero_and_null_never_a_placeholder(self):
        stats = analytics.study_stats()
        self.assertEqual(stats['total_participants'], 0)
        self.assertEqual(stats['arms'], {'REASONING_VISIBLE': 0, 'ANSWER_ONLY': 0})
        for key in ('learning_gain', 'transfer_performance', 'ai_dependency_drop'):
            self.assertIsNone(stats[key]['p_value'])
            self.assertIsNone(stats[key]['cohens_d'])
            self.assertIsNone(stats[key]['treatment']['mean'])

    def test_counts_and_outcomes_reflect_the_rows_in_the_database(self):
        for i in range(3):
            self._enrol(f'tre{i}', 'REASONING_VISIBLE',
                        {'pre': 40, 'post': 80, 'transfer': 85, 'withdrawal': 82})
            self._enrol(f'con{i}', 'ANSWER_ONLY',
                        {'pre': 40, 'post': 70, 'transfer': 60, 'withdrawal': 50})
        stats = analytics.study_stats()
        self.assertEqual(stats['total_participants'], 6)
        self.assertEqual(stats['arms'], {'REASONING_VISIBLE': 3, 'ANSWER_ONLY': 3})
        self.assertEqual(stats['completion'], {'pre': 6, 'post': 6, 'transfer': 6, 'withdrawal': 6})
        self.assertEqual(stats['transfer_performance']['treatment']['mean'], 85.0)
        self.assertEqual(stats['transfer_performance']['control']['mean'], 60.0)

    def test_an_outcome_nobody_has_completed_stays_null(self):
        self._enrol('a', 'REASONING_VISIBLE', {'pre': 40, 'post': 80})
        self._enrol('b', 'ANSWER_ONLY', {'pre': 40, 'post': 70})
        stats = analytics.study_stats()
        self.assertIsNotNone(stats['learning_gain']['treatment']['mean'])
        self.assertIsNone(stats['transfer_performance']['treatment']['mean'])
        self.assertIsNone(stats['transfer_performance']['p_value'])


class CsvColumnTests(SimpleTestCase):
    def test_every_declared_column_is_actually_produced(self):
        """CSV_COLUMNS drives DictWriter; a column with no matching key exports blank."""
        keys = {
            'participant_code', 'arm', 'consent_given', 'grade', 'medium', 'area_type',
            'prior_experience', 'ai_tool_familiarity', 'normalized_gain', 'withdrawal_drop',
            'help_requests', 'code_runs', 'copy_paste', 'first_submission_at', 'last_submission_at',
        }
        for exam_type in analytics.EXAM_TYPES:
            keys.add(exam_type)
            keys.add(f'{exam_type}_attempts')
        self.assertEqual(set(analytics.CSV_COLUMNS), keys)

    def test_no_column_carries_a_real_name_or_email(self):
        for forbidden in ('username', 'email', 'full_name', 'phone', 'school_name'):
            self.assertNotIn(forbidden, analytics.CSV_COLUMNS)
