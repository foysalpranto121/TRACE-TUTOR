"""Read-only views of submissions, sittings and expert ratings for the Django admin.

Scores are computed server-side and ratings are entered through the expert portal; nothing
here is edited by hand. A failed grading is retried with `manage.py grade_submissions`, not by
changing the row.
"""
from django.contrib import admin

from .models import ExamSubmission, ExpertGrade, ExpertRating, PaperSitting


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
