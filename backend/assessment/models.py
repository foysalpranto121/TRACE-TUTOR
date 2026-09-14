from django.db import models
from django.contrib.auth.models import User

class AssessmentItem(models.Model):
    """Legacy table. The live source of items is assessment/item_bank.json (see scoring.py);
    rows here are never created by the API, so anything keyed to this table must stay optional."""
    ITEM_TYPES = [
        ('concept_mcq', 'Concept Multiple Choice'),
        ('code_tracing', 'Code Tracing'),
        ('code_writing', 'Short Code Writing'),
    ]

    EXAM_TYPES = [
        ('pre', 'Pre-Test'),
        ('post', 'Post-Test'),
        ('transfer', 'Transfer Test'),
        ('withdrawal', 'Withdrawal Task'),
    ]

    type = models.CharField(max_length=20, choices=ITEM_TYPES)
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPES, default='pre')
    question = models.TextField()
    code_snippet = models.TextField(blank=True, null=True)
    options = models.JSONField(default=list) # [{id: 'a', text: '...'}, ...]
    keyed_answer = models.CharField(max_length=10)
    curriculum_ref = models.CharField(max_length=100)
    
    # Certification CVI metrics
    i_cvi_score = models.FloatField(default=0.85)
    is_certified = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Item {self.id} ({self.exam_type} - {self.type})"


class ExpertRating(models.Model):
    expert_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    item = models.ForeignKey(AssessmentItem, on_delete=models.CASCADE, related_name='ratings', null=True, blank=True)
    item_key = models.CharField(max_length=50, db_index=True, default='')  # item id in item_bank.json
    alignment_score = models.IntegerField(default=4)   # 1-4
    accuracy_score = models.IntegerField(default=4)    # 1-4
    clarity_score = models.IntegerField(default=4)     # 1-4
    difficulty_score = models.IntegerField(default=3)  # 1-4
    answerability_score = models.IntegerField(default=4)# 1-4
    feedback = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['expert_user', 'item_key'], name='uniq_rating_per_expert_item'),
        ]

    def __str__(self):
        return f"Rating {self.alignment_score} on {self.item_key}"


class ExamSubmission(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    exam_type = models.CharField(max_length=20)
    score_pct = models.IntegerField()
    answers = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(auto_now_add=True)


class ExpertGrade(models.Model):
    submission = models.ForeignKey(ExamSubmission, on_delete=models.CASCADE, related_name='grades', null=True)
    expert_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    assigned_marks = models.IntegerField(default=85) # 0 to 100
    max_marks = models.IntegerField(default=100)
    feedback_comments = models.TextField(blank=True, null=True)
    is_graded = models.BooleanField(default=True)
    graded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['submission', 'expert_user'], name='uniq_grade_per_expert_submission'),
        ]

    def __str__(self):
        return f"Grade {self.assigned_marks}/{self.max_marks} for Sub {self.submission_id}"
