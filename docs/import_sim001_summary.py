"""Run through manage.py shell; import the supplied summary without inventing answers/events."""
import json

from django.contrib.auth.models import User
from django.db import transaction
from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission
from logging_app.models import InteractionLog

SOURCE = {
    'participant_id': 'SIM-001', 'student_name': 'Arafat Hosen',
    'college_name': 'Milestone collaege', 'division': 'Dhaka',
    'gmail': 'arafathossen44@gmail.com', 'enrolled_arm': 'ANSWER_ONLY',
    'completion_status': 'COMPLETE', 'grade': 11, 'age_years': 18,
    'gender': 'Male', 'prior_experience': 'None', 'device_type': 'Smartphone',
    'weekly_study_hours': 2, 'learning_minutes': 32, 'code_runs': 7,
    'learning_help_requests': 4, 'post_help_requests': 3, 'copy_events': 3,
    'tasks_solved': 4, 'pre_score_pct': 47, 'post_score_pct': 87,
    'transfer_score_pct': 60, 'withdrawal_score_pct': 40,
    'post_minus_pre_pp': 40, 'normalized_gain': 0.755,
    'withdrawal_minus_post_pp': -47.000, 'total_minutes': 103,
    'normalized_gain_sq': 0.570, 'withdrawal_drop_sq': 2209.000,
}
EXAMS = {'pre': 47, 'post': 87, 'transfer': 60, 'withdrawal': 40}
IMPORT_KEY = 'user-supplied-participant-summary:SIM-001:v1'


def run():
    with transaction.atomic():
        existing = ParticipantProfile.objects.filter(participant_code='SIM-001').first()
        if existing:
            receipt = InteractionLog.objects.filter(
                user=existing.user, event_type='SUMMARY_IMPORT',
                payload__import_key=IMPORT_KEY,
            ).first()
            assert receipt and receipt.payload.get('source') == SOURCE, 'Conflicting existing participant; no changes made.'
            rows = list(ExamSubmission.objects.filter(student=existing.user).values('exam_type', 'score_pct'))
            assert len(rows) == 4 and {r['exam_type']: r['score_pct'] for r in rows} == EXAMS
            print('ALREADY_IMPORTED', json.dumps(rows))
            return
        assert not User.objects.filter(email__iexact=SOURCE['gmail']).exists(), 'Email already exists; no changes made.'
        assert not User.objects.filter(username='SIM-001').exists(), 'Username already exists; no changes made.'
        user = User(username='SIM-001', email=SOURCE['gmail'], first_name='Arafat', last_name='Hosen')
        user.set_unusable_password()
        user.save()
        profile = ParticipantProfile.objects.create(
            user=user, participant_code='SIM-001', role='STUDENT',
            full_name=SOURCE['student_name'], school_name=SOURCE['college_name'],
            division='Dhaka', assigned_arm='ANSWER_ONLY', enrolled_arm='ANSWER_ONLY',
            grade='11', age=18, gender='Male', prior_experience='None',
            device_type='Smartphone', weekly_study_hours=2,
        )
        # No fabricated per-item answers, code, consent, event timestamps or sittings.
        # Preserve aggregate-only fields verbatim in a dedicated import receipt.
        for exam_type, score in EXAMS.items():
            ExamSubmission.objects.create(
                student=user, exam_type=exam_type, arm='ANSWER_ONLY', score_pct=score,
                grading_status=ExamSubmission.GRADED,
                answers={
                    'answers': {}, 'code_answers': {}, 'results': [],
                    'import_metadata': {
                        'import_key': IMPORT_KEY, 'kind': 'summary_only',
                        'score_source': 'user_supplied', 'answers_available': False,
                        'original_submission_time_available': False,
                        'note': 'Imported aggregate score; individual answers and code were not supplied.',
                    },
                },
            )
        InteractionLog.objects.create(
            user=user, event_type='SUMMARY_IMPORT', arm='ANSWER_ONLY',
            payload={'import_key': IMPORT_KEY, 'source': SOURCE,
                     'note': 'Aggregate import receipt, not an observed learning event. Creation timestamps are import times.'},
        )
        rows = list(ExamSubmission.objects.filter(student=user).values('id', 'exam_type', 'score_pct'))
        assert len(rows) == 4 and {r['exam_type']: r['score_pct'] for r in rows} == EXAMS
        print('IMPORTED', json.dumps({'participant_code': profile.participant_code, 'submissions': rows}))


run()
