import random
from collections import Counter

from django.db import models
from django.contrib.auth.models import User

STAFF_ROLES = {'EXPERT_TEACHER', 'RESEARCHER_ADMIN'}

# Profile fields a user may set at registration and edit later (type -> coercion in views).
EDITABLE_PROFILE_FIELDS = {
    'full_name': 'str', 'phone': 'str', 'gender': 'str', 'age': 'int',
    'school_name': 'str', 'school_type': 'str', 'division': 'str', 'district': 'str', 'area_type': 'str',
    'grade': 'str', 'hsc_batch_year': 'int', 'academic_group': 'str', 'medium': 'str',
    'prior_experience': 'str', 'languages_known': 'list', 'ai_tool_familiarity': 'str',
    'device_type': 'str', 'internet_access': 'str', 'has_computer_at_home': 'bool', 'weekly_study_hours': 'int',
    'learning_goals': 'list', 'preferred_language': 'str',
    'designation': 'str', 'teaching_years': 'int',
}


class ParticipantProfile(models.Model):
    ROLE_CHOICES = [
        ('STUDENT', 'Student'),
        ('EXPERT_TEACHER', 'Expert Teacher / Examiner'),
        ('RESEARCHER_ADMIN', 'Researcher Admin'),
    ]
    ARM_CHOICES = [
        ('REASONING_VISIBLE', 'Treatment: Reasoning-Visible'),
        ('ANSWER_ONLY', 'Control: Answer-Only'),
    ]
    LANG_CHOICES = [('bn', 'Bangla'), ('en', 'English')]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    assigned_arm = models.CharField(max_length=20, choices=ARM_CHOICES, default='REASONING_VISIBLE')
    preferred_language = models.CharField(max_length=5, choices=LANG_CHOICES, default='bn')
    grade = models.CharField(max_length=10, default='11')
    prior_experience = models.CharField(max_length=50, default='novice')
    consent_given = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=10, default='v1')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Pseudonymous research identifier shown to the participant instead of their name in exports.
    participant_code = models.CharField(max_length=20, unique=True, null=True, blank=True)

    # Identity & demographics
    full_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=20, blank=True)
    age = models.PositiveSmallIntegerField(null=True, blank=True)

    # Institution & academic context
    school_name = models.CharField(max_length=200, blank=True)
    school_type = models.CharField(max_length=30, blank=True)
    division = models.CharField(max_length=40, blank=True)
    district = models.CharField(max_length=60, blank=True)
    area_type = models.CharField(max_length=20, blank=True)
    hsc_batch_year = models.PositiveSmallIntegerField(null=True, blank=True)
    academic_group = models.CharField(max_length=30, blank=True)
    medium = models.CharField(max_length=30, blank=True)

    # Learning background & access (covariates for the study)
    languages_known = models.JSONField(default=list, blank=True)
    ai_tool_familiarity = models.CharField(max_length=20, blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    internet_access = models.CharField(max_length=20, blank=True)
    has_computer_at_home = models.BooleanField(null=True, blank=True)
    weekly_study_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    learning_goals = models.JSONField(default=list, blank=True)

    # Staff
    designation = models.CharField(max_length=100, blank=True)
    teaching_years = models.PositiveSmallIntegerField(null=True, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.participant_code:
            self.participant_code = f'TT-{self.pk:04d}'
            super().save(update_fields=['participant_code'])

    @staticmethod
    def balanced_arm():
        """Allocate new students to the arm with fewer participants (ties broken at random)."""
        counts = Counter(ParticipantProfile.objects.filter(role='STUDENT').values_list('assigned_arm', flat=True))
        rv, ao = counts.get('REASONING_VISIBLE', 0), counts.get('ANSWER_ONLY', 0)
        if rv == ao:
            return random.choice(['REASONING_VISIBLE', 'ANSWER_ONLY'])
        return 'REASONING_VISIBLE' if rv < ao else 'ANSWER_ONLY'

    def __str__(self):
        return f"{self.user.username} ({self.role} - {self.assigned_arm})"
