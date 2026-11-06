"""Seven-day post and fourteen-day transfer waits, with late submission allowed.

The wait starts on first opening, not submission. Both a submission and the wait
must be complete before the next paper opens. Stored anchors survive retakes.
"""
from datetime import timedelta
from django.utils import timezone
from .models import AssessmentTimeline, ExamSubmission, PaperSitting

ORDER = ('pre', 'post', 'transfer', 'withdrawal')
WAIT_DAYS = {'post': 7, 'transfer': 14}


def records(user):
    timeline = AssessmentTimeline.objects.filter(student=user).first()
    starts = {}
    for sitting in PaperSitting.objects.filter(student=user):
        starts[sitting.exam_type] = sitting.first_opened_at
    submissions = {}
    for row in ExamSubmission.objects.filter(student=user).order_by('submitted_at', 'pk'):
        submissions.setdefault(row.exam_type, row.submitted_at)
    for exam in ORDER:
        value = getattr(timeline, f'{exam}_started_at', None)
        # Legacy rows have no opening timestamp. Their submission is a conservative
        # fallback for access gating, but isn't presented as a measured opening.
        if value:
            starts[exam] = value
    return timeline, starts, submissions


def record_open(user, exam_type, opened_at):
    timeline, _ = AssessmentTimeline.objects.get_or_create(student=user)
    field = f'{exam_type}_started_at'
    AssessmentTimeline.objects.filter(pk=timeline.pk, **{f'{field}__isnull': True}).update(**{field: opened_at})


def wait_anchor(starts, submitted, exam):
    # A first retake of legacy data must not postpone a wait already completed.
    values = [v for v in (starts.get(exam), submitted.get(exam)) if v]
    return min(values) if values else None


def status(user, now=None):
    now = now or timezone.now()
    timeline, starts, submitted = records(user)
    available = [exam for exam in ORDER if exam in submitted]
    upcoming = next((exam for exam in ORDER if exam not in submitted), None)
    locked_until = None
    waiting_for = None
    if upcoming:
        index = ORDER.index(upcoming)
        previous = ORDER[index - 1] if index else None
        if previous in WAIT_DAYS:
            anchor = wait_anchor(starts, submitted, previous)
            if anchor:
                locked_until = anchor + timedelta(days=WAIT_DAYS[previous])
                if now < locked_until:
                    waiting_for = previous
        if waiting_for is None:
            available.append(upcoming)
    phases = {}
    for exam in ORDER:
        anchor = wait_anchor(starts, submitted, exam)
        next_at = anchor + timedelta(days=WAIT_DAYS[exam]) if anchor and exam in WAIT_DAYS else None
        phases[exam] = {
            'started_at': starts[exam].isoformat() if exam in starts else None,
            'submitted_at': submitted[exam].isoformat() if exam in submitted else None,
            'wait_days': WAIT_DAYS.get(exam, 0),
            'next_available_at': next_at.isoformat() if next_at else None,
        }
    return {
        'available': [exam for exam in ORDER if exam in available],
        'upcoming': upcoming, 'waiting_for': waiting_for,
        'locked_until': locked_until.isoformat() if waiting_for else None,
        'server_now': now.isoformat(), 'late_submission_allowed': True,
        'window_start': timeline.window_start.isoformat() if timeline and timeline.window_start else None,
        'window_end': timeline.window_end.isoformat() if timeline and timeline.window_end else None,
        'phases': phases,
    }


def report(user, exam_type, submitted_at, snapshot=None):
    timeline, starts, submitted = snapshot or records(user)
    opened = starts.get(exam_type)
    if opened and opened > submitted_at:
        opened = None  # This row predates the recorded opening, e.g. a legacy retake.
    first = starts.get('pre')
    completed = submitted.get('withdrawal')
    def days(start, finish):
        return round(max(0, (finish - start).total_seconds()) / 86400, 4) if start and finish else None
    return {
        'opened_at': opened.isoformat() if opened else None,
        'submitted_at': submitted_at.isoformat(),
        'paper_elapsed_days': days(opened, submitted_at),
        'study_started_at': first.isoformat() if first else None,
        'study_completed_at': completed.isoformat() if completed else None,
        'study_elapsed_days': days(first, completed),
        'days_to_latest_submission': days(first, max(submitted.values())) if submitted else None,
        'window_start': timeline.window_start.isoformat() if timeline and timeline.window_start else None,
        'window_end': timeline.window_end.isoformat() if timeline and timeline.window_end else None,
    }
