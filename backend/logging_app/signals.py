"""Keep the per-user dashboard cache honest: drop a user's cached summary the moment anything it
is computed from changes (interaction logs, exam submissions, profile)."""
from django.core.cache import caches
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission
from .models import InteractionLog


def dashboard_cache_key(user_id):
    return f"dashboard:v1:{user_id or 'anon'}"


def invalidate_dashboard(user_id):
    caches['default'].delete(dashboard_cache_key(user_id))


@receiver([post_save, post_delete], sender=InteractionLog, dispatch_uid='trace.dash.log')
def _on_log_change(sender, instance, **kwargs):
    invalidate_dashboard(instance.user_id)


@receiver([post_save, post_delete], sender=ExamSubmission, dispatch_uid='trace.dash.submission')
def _on_submission_change(sender, instance, **kwargs):
    invalidate_dashboard(instance.student_id)


@receiver(post_save, sender=ParticipantProfile, dispatch_uid='trace.dash.profile')
def _on_profile_change(sender, instance, **kwargs):
    invalidate_dashboard(instance.user_id)
