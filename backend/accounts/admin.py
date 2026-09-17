"""Read-only view of participants for the Django admin at /django-admin/.

Research rows are never edited by hand: the arm of record, consent and withdrawal are set by
the application under its own rules, and an edit here would make the study record lie. The
list is deliberately pseudonymous - code, role, arms, consent, withdrawal - with the personal
fields visible only on the detail page.
"""
from django.contrib import admin

from .models import ParticipantProfile


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ParticipantProfile)
class ParticipantProfileAdmin(ReadOnlyAdmin):
    list_display = ('participant_code', 'username', 'role', 'enrolled_arm', 'assigned_arm', 'preferred_language',
                    'consent_given', 'consent_at', 'withdrawn_at', 'withdrawn_by', 'created_at')
    list_filter = ('role', 'enrolled_arm', 'assigned_arm', 'consent_given', 'preferred_language', 'school_type',
                   'area_type', 'medium')
    search_fields = ('participant_code', 'user__username', 'school_name', 'district')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    readonly_fields = [f.name for f in ParticipantProfile._meta.fields]

    @admin.display(ordering='user__username', description='username')
    def username(self, obj):
        return obj.user.username
