"""Read-only view of the interaction log for the Django admin at /django-admin/."""
from django.contrib import admin

from .models import InteractionLog


@admin.register(InteractionLog)
class InteractionLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'participant', 'event_type', 'arm', 'problem_id', 'summary')
    list_filter = ('event_type', 'arm')
    search_fields = ('user__username', 'user__profile__participant_code', 'problem_id', 'payload')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    list_select_related = ('user', 'user__profile')
    list_per_page = 200
    readonly_fields = [f.name for f in InteractionLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='participant')
    def participant(self, obj):
        profile = getattr(obj.user, 'profile', None) if obj.user_id else None
        return profile.participant_code if profile and profile.participant_code else (obj.user.username if obj.user_id else '')

    @admin.display(description='payload')
    def summary(self, obj):
        payload = obj.payload or {}
        keys = ('ai_status', 'cache_tier', 'view', 'exam_type', 'reason', 'language', 'status', 'to_arm', 'from_arm')
        bits = [f'{k}={payload[k]}' for k in keys if k in payload and payload[k] not in (None, '')]
        return ', '.join(bits)[:120]
