from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

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
    """One sitting of one form.

    The row is written the instant the participant presses Submit, with the raw answers
    and no score; grading happens afterwards (assessment/grading.py) and fills in the
    score and per-item results. That ordering is deliberate: grading compiles five C
    programs and is the slowest thing the platform does, and a whole cohort submits
    inside the same minute. Persisting first means a slow or failed grading run can
    never lose a participant's exam.
    """
    PENDING, GRADING, GRADED, FAILED = 'pending', 'grading', 'graded', 'failed'
    GRADING_STATES = [(PENDING, 'Pending'), (GRADING, 'Grading'), (GRADED, 'Graded'), (FAILED, 'Failed')]

    student = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    exam_type = models.CharField(max_length=20)
    # The tutor mode the participant was in when they pressed Submit. Recorded rather
    # than inferred, so a per-protocol analysis (by mode actually used) is possible and
    # any mismatch with the enrolled arm is visible instead of assumed away.
    arm = models.CharField(max_length=20, blank=True, default='')
    # Null until graded. Rows created directly (tests, imports) default to already-graded,
    # so a score given at creation is honoured; the submit endpoint creates them pending.
    score_pct = models.IntegerField(null=True, blank=True)
    answers = models.JSONField(default=dict)
    submitted_at = models.DateTimeField(auto_now_add=True, db_index=True)
    grading_status = models.CharField(max_length=10, choices=GRADING_STATES, default=GRADED, db_index=True)
    # When a grader claimed this row (moved it PENDING -> GRADING). A row that is still
    # 'grading' long after this was set belongs to a grader that died - a restart mid
    # compile, say - and is requeued by the next sweep instead of polling forever.
    claimed_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    grading_error = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-submitted_at']
        indexes = [
            # analytics._first_submissions() walks exactly this ordering, and the paper
            # access gate asks "which forms has this participant already submitted?".
            models.Index(fields=['student', 'exam_type', 'submitted_at'],
                         name='submission_student_exam_idx'),
        ]

    @property
    def is_graded(self):
        return self.grading_status == self.GRADED


class PaperSitting(models.Model):
    """One participant's sitting of one paper: opened when the items are first served,
    closed when the submission lands.

    This is what lets the server enforce the protocol rather than trusting the browser:
    the tutor refuses while a no-AI paper (pre-test, withdrawal task) is open, a paper
    cannot be submitted twice, and time-on-paper is measured rather than guessed.
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sittings')
    exam_type = models.CharField(max_length=20)
    arm = models.CharField(max_length=20, blank=True, default='')       # mode when first opened
    first_opened_at = models.DateTimeField(auto_now_add=True)
    last_opened_at = models.DateTimeField(default=timezone.now)        # refreshed on every re-open
    submitted_at = models.DateTimeField(null=True, blank=True)
    submission = models.ForeignKey('ExamSubmission', null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name='sittings')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'exam_type'], name='uniq_sitting_per_student_paper'),
        ]

    @property
    def is_open(self):
        return self.submitted_at is None

    def __str__(self):
        return f'{self.exam_type} sitting by user {self.student_id} ({"open" if self.is_open else "submitted"})'


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
