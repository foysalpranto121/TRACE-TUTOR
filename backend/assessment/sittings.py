"""Paper sittings: the server's own record of who is sitting which paper right now.

Three protocol rules used to live only in the browser, where a second tab defeats them:

  * the pre-test is a baseline and the withdrawal task measures dependency, so the
    tutor must be unavailable while either is the participant's active paper;
  * a paper is sat once;
  * time-on-paper is part of the behavioural record.

A sitting opens when a participant is first served a paper's items and closes when
their submission lands. While a no-AI paper is open (and was opened recently - see
PAPER_SITTING_TTL_HOURS, so an abandoned tab cannot lock someone out for good) the tutor
endpoint refuses. The newest recently opened sitting is active, which prevents a stale
unfinished sitting from disabling AI in a later post/transfer retake. Staff browsing the
bank never get sittings.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from logging_app.models import InteractionLog
from .models import ExamSubmission, PaperSitting

OPEN, COMPLETED, NEW = 'open', 'completed', 'new'


def no_ai_papers():
    return tuple(getattr(settings, 'NO_AI_PAPERS', ('pre', 'withdrawal')))


def ttl():
    return timedelta(hours=float(getattr(settings, 'PAPER_SITTING_TTL_HOURS', 4)))


def open_paper(user, exam_type, arm=''):
    """Record that `user` has the paper in front of them. Idempotent; re-opening an
    unfinished paper refreshes last_opened_at so the no-AI lock follows real activity."""
    sitting, created = PaperSitting.objects.get_or_create(
        student=user, exam_type=exam_type, defaults={'arm': arm or ''})
    from . import timing
    timing.record_open(user, exam_type, sitting.first_opened_at)
    if created:
        InteractionLog.objects.create(
            user=user, event_type='PAPER_OPENED', arm=arm or sitting.arm or 'REASONING_VISIBLE',
            payload={'exam_type': exam_type})
    elif sitting.is_open:
        sitting.last_opened_at = timezone.now()
        sitting.save(update_fields=['last_opened_at'])
    return sitting


def close_paper(user, exam_type, submission, arm=''):
    """The submission has landed: close the sitting (creating one if the client never
    fetched the items, e.g. an API caller) and link it to the submission."""
    sitting, _ = PaperSitting.objects.get_or_create(
        student=user, exam_type=exam_type, defaults={'arm': arm or ''})
    from . import timing
    timing.record_open(user, exam_type, sitting.first_opened_at)
    sitting.submitted_at = submission.submitted_at or timezone.now()
    sitting.submission = submission
    sitting.save(update_fields=['submitted_at', 'submission'])
    return sitting


def already_submitted(user, exam_type):
    """A paper is sat once. Checked against submissions, not sittings, so it also
    covers rows that predate sittings."""
    return ExamSubmission.objects.filter(student=user, exam_type=exam_type).exists()


def retake_paper(user, exam_type, arm=''):
    """Reopen a previously completed paper so the participant can take it again."""
    sitting, _ = PaperSitting.objects.get_or_create(
        student=user, exam_type=exam_type, defaults={'arm': arm or ''})
    from . import timing
    timing.record_open(user, exam_type, sitting.first_opened_at)
    now = timezone.now()
    sitting.first_opened_at = now
    sitting.last_opened_at = now
    sitting.submitted_at = None
    sitting.submission = None
    if arm:
        sitting.arm = arm
    sitting.save(update_fields=['first_opened_at', 'last_opened_at', 'submitted_at', 'submission', 'arm'])
    InteractionLog.objects.create(
        user=user, event_type='PAPER_RETAKEN', arm=arm or sitting.arm or 'REASONING_VISIBLE',
        payload={'exam_type': exam_type})
    return sitting


def is_paper_open(user, exam_type):
    """Whether user currently has an open (unsubmitted) sitting for this paper."""
    sitting = PaperSitting.objects.filter(student=user, exam_type=exam_type).first()
    return sitting is not None and sitting.is_open


def open_paper_of(user, exam_types=None):
    """The paper this participant currently has open, or None.

    'Currently' means opened or re-opened within the TTL. `exam_types` narrows it to
    some papers (the no-AI ones, for the tutor gate); by default any paper counts, which
    is how a tutor turn gets stamped with the paper it was asked during.
    """
    since = timezone.now() - ttl()
    queryset = PaperSitting.objects.filter(student=user, submitted_at__isnull=True,
                                           last_opened_at__gte=since)
    if exam_types is not None:
        queryset = queryset.filter(exam_type__in=exam_types)
    return queryset.order_by('-last_opened_at').values_list('exam_type', flat=True).first()


def blocking_paper(user):
    """The active paper when it is a no-AI paper, otherwise ``None``.

    A retake can leave an older paper's sitting unsubmitted.  The most recently opened
    sitting is the paper the participant is actually using, so a stale withdrawal
    sitting must not disable the tutor during a newer post/transfer retake.  Opening the
    no-AI paper again makes it active and restores the block immediately.
    """
    active = open_paper_of(user)
    return active if active in no_ai_papers() else None


def describe(user, exam_type):
    """What the client needs to know about this participant's sitting of a paper."""
    sitting = PaperSitting.objects.filter(student=user, exam_type=exam_type).first()
    if sitting is None:
        return {'status': NEW, 'submission_id': None, 'first_opened_at': None, 'submitted_at': None}
    return {
        'status': OPEN if sitting.is_open else COMPLETED,
        'submission_id': sitting.submission_id,
        'first_opened_at': sitting.first_opened_at.isoformat(),
        'submitted_at': sitting.submitted_at.isoformat() if sitting.submitted_at else None,
        'no_ai': exam_type in no_ai_papers(),
    }


def minutes_by_paper():
    """(student_id, exam_type) -> minutes from first opening to submission, for the export."""
    out = {}
    for student_id, exam_type, opened, submitted in (
            PaperSitting.objects.filter(submitted_at__isnull=False)
            .values_list('student_id', 'exam_type', 'first_opened_at', 'submitted_at')):
        out[(student_id, exam_type)] = round((submitted - opened).total_seconds() / 60, 1)
    return out
