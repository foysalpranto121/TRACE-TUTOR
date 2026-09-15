from django.db import models
from django.contrib.auth.models import User


class InteractionLog(models.Model):
    """One behavioural event. This table grows fastest of anything in the study and is
    read on every dashboard load, so its access patterns are indexed explicitly."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    event_type = models.CharField(max_length=50)  # e.g. HELP_REQUEST, CODE_RUN, COPY_PASTE, LOGIN, LOGOUT
    arm = models.CharField(max_length=20, default='REASONING_VISIBLE')
    problem_id = models.CharField(max_length=50, null=True, blank=True)
    payload = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            # The dashboard's own query: this participant's newest 3000 events.
            models.Index(fields=['user', '-timestamp'], name='ilog_user_recent_idx'),
            # Per-participant event tallies for the export and the dashboard counters.
            models.Index(fields=['user', 'event_type'], name='ilog_user_event_idx'),
            # Study-wide counts by event type (HELP_REQUEST, CODE_RESULT, COPY_PASTE).
            models.Index(fields=['event_type'], name='ilog_event_idx'),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.arm} at {self.timestamp}"
