"""Existing portal feedback must appear without copying or changing research rows."""
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import (ExamSubmission, ExpertFeedback, ExpertGrade,
                               ExpertRating, TeacherComment)


class FeedbackAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('feedback-admin', password='disposable-password')
        cls.student = User.objects.create_user('learner-one')
        ParticipantProfile.objects.create(user=cls.student, participant_code='QA-001', full_name='Learner One')
        cls.teacher = User.objects.create_user('teacher-one', first_name='Expert', last_name='One')
        cls.submission = ExamSubmission.objects.create(student=cls.student, exam_type='post', score_pct=60)
        cls.grade = ExpertGrade.objects.create(submission=cls.submission, expert_user=cls.teacher,
                                             assigned_marks=55, feedback_comments='Earlier qualitative feedback\nSecond paragraph')
        cls.exam, cls.item = scoring.all_items()[0]
        cls.rating = ExpertRating.objects.create(expert_user=cls.teacher, item_key=cls.item['id'],
                                                feedback='Earlier item comment <script>alert(1)</script>')

    def setUp(self):
        self.client.force_login(self.admin)

    def page(self, model, **query):
        return self.client.get(reverse(f'admin:assessment_{model}_changelist'), query)

    def test_assessment_index_lists_both_sections(self):
        response = self.client.get(reverse('admin:app_list', args=['assessment']))
        self.assertContains(response, 'Expert feedback')
        self.assertContains(response, 'Teacher comment')

    def test_historical_feedback_displays_student_expert_test_and_complete_text(self):
        response = self.page('expertfeedback')
        for value in ('Learner One', 'QA-001', 'Expert One', 'post',
                      'Earlier qualitative feedback\nSecond paragraph'):
            self.assertContains(response, value)
        self.assertEqual(response.context['cl'].result_count, 1)
        detail = self.client.get(reverse('admin:assessment_expertfeedback_change', args=[self.grade.pk]))
        self.assertContains(detail, f'Submission #{self.submission.pk}')
        self.assertContains(detail, 'Qualitative feedback')

    def test_historical_item_comment_resolves_item_and_escapes_teacher_content(self):
        response = self.page('teachercomment')
        self.assertContains(response, self.item['id'])
        self.assertContains(response, self.item['title'])
        self.assertContains(response, 'Expert One')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        detail = self.client.get(reverse('admin:assessment_teachercomment_change', args=[self.rating.pk]))
        self.assertContains(detail, 'Teacher comment')
        self.assertContains(detail, self.exam)

    def test_search_and_test_filter_find_saved_feedback(self):
        for query in ('QA-001', 'Learner One', 'teacher-one', 'qualitative'):
            self.assertEqual(self.page('expertfeedback', q=query).context['cl'].result_count, 1)
        self.assertEqual(self.page('expertfeedback', submission__exam_type__exact='pre').context['cl'].result_count, 0)
        self.assertEqual(self.page('teachercomment', q=self.item['id']).context['cl'].result_count, 1)
        self.assertEqual(self.page('teachercomment', q='Earlier item').context['cl'].result_count, 1)

    def test_blank_rows_hidden_and_portal_updates_visible_without_copying(self):
        other = User.objects.create_user('other-expert')
        for index, value in enumerate((None, '', '   ')):
            ExpertGrade.objects.create(expert_user=other, feedback_comments=value)
            ExpertRating.objects.create(expert_user=other, item_key=f'empty-{index}', feedback=value)
        self.assertEqual(self.page('expertfeedback').context['cl'].result_count, 1)
        self.assertEqual(self.page('teachercomment').context['cl'].result_count, 1)
        ExpertGrade.objects.filter(pk=self.grade.pk).update(feedback_comments='Updated by portal')
        ExpertRating.objects.filter(pk=self.rating.pk).update(feedback='Updated item comment')
        self.assertContains(self.page('expertfeedback'), 'Updated by portal')
        self.assertContains(self.page('teachercomment'), 'Updated item comment')
        self.assertEqual(ExpertFeedback._meta.db_table, ExpertGrade._meta.db_table)
        self.assertEqual(TeacherComment._meta.db_table, ExpertRating._meta.db_table)
        self.assertEqual(ExpertGrade.objects.count(), 4)
        self.assertEqual(ExpertRating.objects.count(), 4)

    def test_views_are_read_only_and_require_staff_and_view_permissions(self):
        for model, pk in (('expertfeedback', self.grade.pk), ('teachercomment', self.rating.pk)):
            self.assertEqual(self.client.get(reverse(f'admin:assessment_{model}_add')).status_code, 403)
            self.assertEqual(self.client.post(reverse(f'admin:assessment_{model}_change', args=[pk]),
                                             {'feedback_comments': 'overwrite'}).status_code, 403)
            self.assertEqual(self.client.post(reverse(f'admin:assessment_{model}_delete', args=[pk])).status_code, 403)
        staff = User.objects.create_user('read-only-staff', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.page('expertfeedback').status_code, 403)
        staff.user_permissions.add(Permission.objects.get(codename='view_expertfeedback'))
        self.assertEqual(self.page('expertfeedback').status_code, 200)
        self.assertEqual(self.page('teachercomment').status_code, 403)
        self.client.force_login(self.student)
        self.assertEqual(self.page('expertfeedback').status_code, 302)
        self.assertEqual(self.page('teachercomment').status_code, 302)
        self.grade.refresh_from_db()
        self.assertEqual(self.grade.feedback_comments, 'Earlier qualitative feedback\nSecond paragraph')

    def test_missing_legacy_relations_still_render(self):
        grade = ExpertGrade.objects.create(feedback_comments='Legacy feedback without a submission')
        rating = ExpertRating.objects.create(item_key='retired-item', feedback='Legacy item comment')
        self.assertContains(self.page('expertfeedback'), grade.feedback_comments)
        self.assertContains(self.page('teachercomment'), rating.feedback)
        self.assertContains(self.page('teachercomment'), 'retired-item')
