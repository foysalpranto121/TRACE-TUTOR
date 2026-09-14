from django.db import models
from django.contrib.auth.models import User

class InteractionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    event_type = models.CharField(max_length=50) # e.g. HELP_REQUEST, CODE_RUN, COPY_PASTE, LOGIN, LOGOUT
    arm = models.CharField(max_length=20, default='REASONING_VISIBLE')
    problem_id = models.CharField(max_length=50, null=True, blank=True)
    payload = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} - {self.arm} at {self.timestamp}"
