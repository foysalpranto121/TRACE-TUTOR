"""Read-only views of submissions, sittings and expert ratings for the Django admin.

Scores are computed server-side and ratings are entered through the expert portal; nothing
here is edited by hand. A failed grading is retried with `manage.py grade_submissions`, not by
changing the row.
"""
from django.contrib import admin
from django.db.models.functions import Trim
from django.urls import reverse
from django.utils.html import format_html

from . import scoring
from .models import (AssessmentTimeline, ExamSubmission, ExpertFeedback, ExpertGrade,
                     ExpertRating, PaperSitting, TeacherComment, TeacherReviewAssignment,
                     ItemReviewAssignment, SubmissionReviewAssignment)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def _code(user):
    profile = getattr(user, 'profile', None) if user else None
    return profile.participant_code if profile and profile.participant_code else (user.username if user else '')


@admin.register(AssessmentTimeline)
class AssessmentTimelineAdmin(ReadOnlyAdmin):
    list_display = ('student', 'window_start', 'window_end', 'pre_started_at', 'post_started_at',
                    'transfer_started_at', 'withdrawal_started_at', 'is_synthetic')
    search_fields = ('student__username', 'student__profile__participant_code')
    list_select_related = ('student',)
    readonly_fields = [f.name for f in AssessmentTimeline._meta.fields]


@admin.register(ExamSubmission)
class ExamSubmissionAdmin(ReadOnlyAdmin):
    list_display = ('id', 'participant', 'exam_type', 'arm', 'score_pct', 'grading_status', 'submitted_at',
                    'graded_at', 'grading_error_short')
    list_filter = ('exam_type', 'arm', 'grading_status')
    search_fields = ('student__username', 'student__profile__participant_code', 'grading_error')
    date_hierarchy = 'submitted_at'
    ordering = ('-submitted_at',)
    list_select_related = ('student', 'student__profile')
    readonly_fields = [f.name for f in ExamSubmission._meta.fields]

    @admin.display(description='participant')
    def participant(self, obj):
        return _code(obj.student)

    @admin.display(description='error')
    def grading_error_short(self, obj):
        return (obj.grading_error or '')[:80]


@admin.register(PaperSitting)
class PaperSittingAdmin(ReadOnlyAdmin):
    list_display = ('id', 'participant', 'exam_type', 'arm', 'first_opened_at', 'last_opened_at', 'submitted_at', 'submission')
    list_filter = ('exam_type', 'arm')
    search_fields = ('student__username', 'student__profile__participant_code')
    date_hierarchy = 'first_opened_at'
    ordering = ('-first_opened_at',)
    list_select_related = ('student', 'student__profile', 'submission')
    readonly_fields = [f.name for f in PaperSitting._meta.fields]

    @admin.display(description='participant')
    def participant(self, obj):
        return _code(obj.student)


@admin.register(ExpertRating)
class ExpertRatingAdmin(ReadOnlyAdmin):
    list_display = ('item_key', 'expert', 'alignment_score', 'accuracy_score', 'clarity_score', 'difficulty_score',
                    'answerability_score', 'created_at')
    list_filter = ('alignment_score', 'accuracy_score', 'clarity_score', 'answerability_score')
    search_fields = ('item_key', 'expert_user__username', 'feedback')
    ordering = ('item_key', 'expert_user')
    list_select_related = ('expert_user',)
    readonly_fields = [f.name for f in ExpertRating._meta.fields]

    @admin.display(description='expert', ordering='expert_user__username')
    def expert(self, obj):
        return obj.expert_user.username if obj.expert_user_id else ''


@admin.register(ExpertGrade)
class ExpertGradeAdmin(ReadOnlyAdmin):
    list_display = ('id', 'submission', 'expert_user', 'assigned_marks', 'max_marks', 'is_graded', 'graded_at')
    list_filter = ('is_graded',)
    ordering = ('-graded_at',)
    readonly_fields = [f.name for f in ExpertGrade._meta.fields]


def _name(user):
    if not user:
        return '—'
    profile = getattr(user, 'profile', None)
    name = (profile.full_name if profile else '') or user.get_full_name()
    return f'{name} ({user.username})' if name else user.username


def _text(value):
    # Escape teacher-authored content while preserving paragraphs and line breaks.
    return format_html('<div style="white-space:pre-wrap;min-width:240px;max-width:640px">{}</div>', value or '')


@admin.register(ExpertFeedback)
class ExpertFeedbackAdmin(ReadOnlyAdmin):
    list_display = ('id', 'student_name', 'participant_code', 'exam_type', 'expert_name',
                    'qualitative_feedback', 'assigned_marks', 'max_marks', 'graded_at')
    list_filter = ('submission__exam_type', 'expert_user', 'is_graded')
    search_fields = ('submission__student__username', 'submission__student__profile__full_name',
                     'submission__student__profile__participant_code', 'expert_user__username',
                     'expert_user__first_name', 'expert_user__last_name',
                     'expert_user__profile__full_name', 'feedback_comments')
    list_select_related = ('submission__student__profile', 'expert_user__profile')
    ordering = ('-graded_at', '-pk')
    date_hierarchy = 'graded_at'
    readonly_fields = ('student_name', 'participant_code', 'exam_type', 'submission_link',
                       'expert_name', 'qualitative_feedback', 'assigned_marks', 'max_marks',
                       'is_graded', 'graded_at')
    fields = readonly_fields

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            feedback_text=Trim('feedback_comments')).filter(
                feedback_comments__isnull=False).exclude(feedback_text='')

    @admin.display(description='Student', ordering='submission__student__profile__full_name')
    def student_name(self, obj):
        return _name(obj.submission.student if obj.submission else None)

    @admin.display(description='Participant code', ordering='submission__student__profile__participant_code')
    def participant_code(self, obj):
        return _code(obj.submission.student if obj.submission else None)

    @admin.display(description='Test', ordering='submission__exam_type')
    def exam_type(self, obj):
        return obj.submission.exam_type if obj.submission else '—'

    @admin.display(description='Submission')
    def submission_link(self, obj):
        if not obj.submission_id:
            return '—'
        return format_html('<a href="{}">Submission #{}</a>',
                           reverse('admin:assessment_examsubmission_change', args=[obj.submission_id]),
                           obj.submission_id)

    @admin.display(description='Expert', ordering='expert_user__username')
    def expert_name(self, obj):
        return _name(obj.expert_user)

    @admin.display(description='Qualitative feedback')
    def qualitative_feedback(self, obj):
        return _text(obj.feedback_comments)


@admin.register(TeacherComment)
class TeacherCommentAdmin(ReadOnlyAdmin):
    list_display = ('item_key', 'item_title', 'exam_type', 'teacher', 'teacher_comment', 'created_at')
    list_filter = ('expert_user',)
    search_fields = ('item_key', 'item__question', 'expert_user__username',
                     'expert_user__first_name', 'expert_user__last_name',
                     'expert_user__profile__full_name', 'feedback')
    list_select_related = ('expert_user__profile', 'item')
    ordering = ('item_key', 'expert_user', '-pk')
    date_hierarchy = 'created_at'
    readonly_fields = ('item_key', 'item_title', 'exam_type', 'teacher', 'teacher_comment',
                       'alignment_score', 'accuracy_score', 'clarity_score',
                       'difficulty_score', 'answerability_score', 'created_at')
    fields = readonly_fields

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            comment_text=Trim('feedback')).filter(feedback__isnull=False).exclude(comment_text='')

    @admin.display(description='Item')
    def item_title(self, obj):
        _, item = scoring.find_item(obj.item_key)
        return (item.get('title') or item.get('question') or obj.item_key) if item else (
            obj.item.question if obj.item else obj.item_key)

    @admin.display(description='Test')
    def exam_type(self, obj):
        exam_type, _ = scoring.find_item(obj.item_key)
        return exam_type or (obj.item.exam_type if obj.item else '—')

    @admin.display(description='Teacher', ordering='expert_user__username')
    def teacher(self, obj):
        return _name(obj.expert_user)

    @admin.display(description='Teacher comment')
    def teacher_comment(self, obj):
        return _text(obj.feedback)


@admin.register(TeacherReviewAssignment)
class TeacherReviewAssignmentAdmin(ReadOnlyAdmin):
    list_display = ('expert_user', 'assigned_at')
    search_fields = ('expert_user__username', 'expert_user__profile__full_name')
    list_select_related = ('expert_user',)
    readonly_fields = ('expert_user', 'assigned_at')


@admin.register(ItemReviewAssignment)
class ItemReviewAssignmentAdmin(ReadOnlyAdmin):
    list_display = ('item_key', 'expert_user', 'assigned_at')
    list_filter = ('expert_user',)
    search_fields = ('item_key', 'expert_user__username')
    list_select_related = ('expert_user',)
    readonly_fields = ('item_key', 'expert_user', 'assigned_at')


@admin.register(SubmissionReviewAssignment)
class SubmissionReviewAssignmentAdmin(ReadOnlyAdmin):
    list_display = ('submission', 'participant', 'test', 'expert_user', 'assigned_at')
    list_filter = ('expert_user', 'submission__exam_type')
    search_fields = ('submission__student__profile__participant_code', 'expert_user__username')
    list_select_related = ('submission__student__profile', 'expert_user')
    readonly_fields = ('submission', 'expert_user', 'assigned_at')

    @admin.display(description='Participant')
    def participant(self, obj):
        return _code(obj.submission.student)

    @admin.display(description='Test', ordering='submission__exam_type')
    def test(self, obj):
        return obj.submission.exam_type
