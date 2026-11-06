"""Read-only snapshot for the requested ten teachers and sixty-student cohort."""
import base64
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.auth.models import User
from django.db import connection, transaction
from django.db.models import Count, Q
from django.utils import timezone
from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import (AssessmentTimeline, ExamSubmission, ExpertGrade, ExpertRating,
                               ItemReviewAssignment, SubmissionReviewAssignment)
from logging_app.models import InteractionLog

EMAILS = (
    'aiyesha.cse@gmail.com', 'asique.iqbaldrmc@gmail.com', 'motaleb.fgc@gmail.com',
    'alamgirlm94@gmail.com', 'mdraihaniu@gmail.com', 'rokib.armc@gmail.com',
    'mamun.armc@gmail.com', 'shamim007.akanda@gmail.com', 'anisurict1@gmail.com',
    'kadirmd159@gmail.com',
)
CODES = [f'SIM-{n:03d}' for n in range(1, 61)]
condition = Q(pk__in=[])
for email in EMAILS:
    condition |= Q(email__iexact=email)

with transaction.atomic():
    with connection.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
    teachers = list(User.objects.filter(condition).order_by('pk').values(
        'id', 'username', 'email', 'profile__full_name', 'profile__school_name',
        'profile__division', 'profile__district', 'profile__designation',
        'profile__teaching_years', 'profile__role'))
    assert len(teachers) == 10 and all(t['profile__role'] == 'EXPERT_TEACHER' for t in teachers)
    teacher_ids = [t['id'] for t in teachers]
    students = list(ParticipantProfile.objects.filter(participant_code__in=CODES).order_by('participant_code').values(
        'user_id', 'participant_code', 'full_name', 'school_name', 'division', 'district',
        'user__email', 'enrolled_arm', 'assigned_arm', 'grade', 'age', 'gender',
        'prior_experience', 'device_type', 'weekly_study_hours', 'consent_given',
        'medium', 'area_type', 'ai_tool_familiarity'))
    assert len(students) == 60
    student_ids = [p['user_id'] for p in students]
    cohort_ids = set(ExamSubmission.objects.filter(student_id__in=student_ids).values_list('id', flat=True))
    # Include these teachers' earlier grades in their review export; the student
    # summary remains strictly the requested sixty SIM participants.
    historical_ids = ExpertGrade.objects.filter(expert_user_id__in=teacher_ids).values_list('submission_id', flat=True)
    submissions = list(ExamSubmission.objects.filter(
        Q(id__in=cohort_ids) | Q(id__in=historical_ids)).order_by('submitted_at', 'pk').values(
        'id', 'student_id', 'student__profile__participant_code', 'student__profile__full_name',
        'exam_type', 'arm', 'score_pct', 'submitted_at', 'grading_status', 'answers'))
    snapshot = {
        'extracted_at_utc': timezone.now(), 'timezone': 'Asia/Dhaka',
        'teacher_email_order': EMAILS, 'teachers': teachers, 'students': students,
        'cohort_submission_ids': sorted(cohort_ids), 'submissions': submissions,
        'timelines': list(AssessmentTimeline.objects.filter(student_id__in=student_ids).values()),
        'grades': list(ExpertGrade.objects.filter(expert_user_id__in=teacher_ids).order_by('pk').values()),
        'ratings': list(ExpertRating.objects.filter(expert_user_id__in=teacher_ids).order_by('pk').values()),
        'item_assignments': list(ItemReviewAssignment.objects.filter(expert_user_id__in=teacher_ids).values()),
        'submission_assignments': list(SubmissionReviewAssignment.objects.filter(
            expert_user_id__in=teacher_ids, submission_id__in=cohort_ids).values()),
        'items': [dict(scoring.public_item(item), exam_type=exam) for exam, item in scoring.all_items()],
        'telemetry_counts': list(InteractionLog.objects.filter(user_id__in=student_ids).values(
            'user_id', 'event_type').annotate(count=Count('id'))),
    }
    raw = json.dumps(snapshot, cls=DjangoJSONEncoder, ensure_ascii=False).encode('utf-8')
    print('TRACE_EXPORT_SNAPSHOT_BASE64:' + base64.b64encode(raw).decode())
