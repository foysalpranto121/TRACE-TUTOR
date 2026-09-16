"""Background grading of exam submissions.

Why this exists: grading a form compiles and runs five C programs. Done inside the
submit request, a cohort of 30 pressing Submit together queued to ~37 s each and a
cohort of 60 would sit past every browser and proxy timeout. So submit_exam now only
persists the raw answers and returns; the grading runs here, and the client polls.

Two ways the work gets done, both idempotent and safe to run together:

  in-process   submit_exam calls enqueue(), which grades on a bounded pool of daemon
               threads inside the web process. Enough for a single lab server.
  worker       `manage.py grade_submissions` polls the table from a separate process.
               Use it when the web server runs several processes, or to drain rows left
               pending by a restart.

Claiming a row is one atomic UPDATE ... WHERE grading_status='pending', so exactly one
grader wins on every database engine; the loser simply moves on. A grading failure is
recorded on the row (status 'failed' + the error) rather than raised, so it is visible
in the expert portal and can be retried - a participant's exam is never lost to a
compiler hiccup.
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db import connections, transaction
from django.db.models import Q
from django.utils import timezone

from . import scoring
from .models import ExamSubmission

logger = logging.getLogger(__name__)

_pool_lock = threading.Lock()
_pool = None


def _concurrency():
    return max(1, int(getattr(settings, 'GRADING_CONCURRENCY', 2)))


def _stale_minutes():
    """How long a row may sit in 'grading' before it is treated as abandoned. Grading a
    form takes seconds, so ten minutes is comfortably past any real run."""
    return max(1, int(getattr(settings, 'GRADING_STALE_MINUTES', 10)))


def _inline():
    """Grade synchronously inside the request. Tests and tiny single-user setups only."""
    return bool(getattr(settings, 'GRADING_INLINE', False))


def _mode():
    """'thread': grade on background threads inside the web process (default; fine for
    a single lab server). 'worker': the web process only queues, and a separate
    `manage.py grade_submissions` process does every compile - so the request threads
    never share a GIL with a compiler and Submit stays fast under a whole cohort."""
    return str(getattr(settings, 'GRADING_MODE', 'thread')).lower()


def _semaphore():
    """Bounds how many submissions the web process grades at once.

    Each submission already fans its C items out over scoring.GRADE_WORKERS threads,
    so this is a cap on cohorts, not on compiles: 2 submissions x 3 workers = 6 compiles
    in flight, which is what a lab server can absorb without starving the request threads.
    """
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = threading.BoundedSemaphore(_concurrency())
        return _pool


# --------------------------------------------------------------------------- core
def claim(submission_id):
    """Atomically take ownership of a pending row. True if this caller won it."""
    won = (ExamSubmission.objects
           .filter(pk=submission_id, grading_status=ExamSubmission.PENDING)
           .update(grading_status=ExamSubmission.GRADING, claimed_at=timezone.now()))
    return won == 1


def requeue_stale(minutes=None):
    """Return rows stuck in 'grading' past the stale threshold to PENDING.

    A grader that dies between claim and persist - a restarted web process, a killed
    worker - leaves its row in 'grading' forever, and the participant's result page
    polls it forever. This is the backstop: the next sweep reclaims it. Rows with no
    claimed_at (claimed before this field existed) use submitted_at as the yardstick.
    """
    cutoff = timezone.now() - timedelta(minutes=minutes or _stale_minutes())
    return (ExamSubmission.objects
            .filter(grading_status=ExamSubmission.GRADING)
            .filter(Q(claimed_at__lt=cutoff) | Q(claimed_at__isnull=True, submitted_at__lt=cutoff))
            .update(grading_status=ExamSubmission.PENDING, claimed_at=None,
                    grading_error='Requeued after a grader did not finish'))


def grade(submission):
    """Grade one claimed submission and persist the outcome. Never raises.

    Both the scoring and the persist are inside the failure handler: if either throws -
    a compiler that never returns, a database error writing the score - the row is
    marked FAILED (and is retryable) rather than left stranded in 'grading'.
    """
    stored = submission.answers if isinstance(submission.answers, dict) else {}
    try:
        score_pct, correct, total, results = scoring.grade_submission(
            submission.exam_type, stored.get('answers') or {}, stored.get('code_answers') or {})
        stored['results'] = results
        with transaction.atomic():
            row = ExamSubmission.objects.select_for_update().get(pk=submission.pk) \
                if _supports_row_locks() else ExamSubmission.objects.get(pk=submission.pk)
            row.answers = stored
            row.score_pct = score_pct
            row.grading_status = ExamSubmission.GRADED
            row.graded_at = timezone.now()
            row.grading_error = ''
            row.save(update_fields=['answers', 'score_pct', 'grading_status', 'graded_at', 'grading_error'])
    except Exception as exc:  # noqa: BLE001 - the failure is recorded, not propagated
        logger.exception('Grading submission %s failed', submission.pk)
        try:
            ExamSubmission.objects.filter(pk=submission.pk).update(
                grading_status=ExamSubmission.FAILED, grading_error=str(exc)[:2000])
        except Exception:  # noqa: BLE001 - if even this write fails, requeue_stale reclaims it
            logger.exception('Could not mark submission %s FAILED', submission.pk)
        return False
    logger.info('Graded submission %s: %s/%s (%s%%)', submission.pk, correct, total, score_pct)
    return True


def _supports_row_locks():
    from django.db import connection
    return connection.features.has_select_for_update


def grade_now(submission_id):
    """Claim and grade one row in the calling thread. True if graded by this call."""
    if not claim(submission_id):
        return False
    submission = ExamSubmission.objects.get(pk=submission_id)
    return grade(submission)


def grade_pending(limit=50, workers=1):
    """Sweep pending rows, oldest first. Returns how many this call graded.

    `workers` > 1 grades that many submissions side by side - the dedicated worker
    process uses GRADING_CONCURRENCY here. One at a time made a cohort of 60 wait 156 s
    for marks on a 16-CPU box; in parallel it is half that.

    Rows stranded in 'grading' by a dead grader are reclaimed first, so a restart
    mid-cohort cannot leave a participant polling a result that never comes.
    """
    requeue_stale()
    ids = list(ExamSubmission.objects
               .filter(grading_status=ExamSubmission.PENDING)
               .order_by('submitted_at')
               .values_list('pk', flat=True)[:limit])
    if not ids:
        return 0
    if workers <= 1 or len(ids) == 1:
        return sum(1 for submission_id in ids if grade_now(submission_id))

    def in_own_connection(submission_id):
        try:
            return grade_now(submission_id)
        finally:
            connections.close_all()  # pool threads outlive this sweep; never hold a connection

    with ThreadPoolExecutor(max_workers=min(workers, len(ids))) as pool:
        return sum(1 for won in pool.map(in_own_connection, ids) if won)


def retry_failed(limit=50):
    """Put failed rows back in the queue (e.g. after fixing a broken toolchain)."""
    ids = list(ExamSubmission.objects
               .filter(grading_status=ExamSubmission.FAILED)
               .values_list('pk', flat=True)[:limit])
    return ExamSubmission.objects.filter(pk__in=ids).update(
        grading_status=ExamSubmission.PENDING, grading_error='')


# ----------------------------------------------------------------------- dispatch
def _worker(submission_id):
    semaphore = _semaphore()
    with semaphore:
        try:
            grade_now(submission_id)
            # While we are here, drain anything a restart or a crashed thread left behind.
            grade_pending(limit=10)
        except Exception:  # noqa: BLE001
            logger.exception('Grading worker crashed on submission %s', submission_id)
        finally:
            # Unconditionally, not close_old_connections(): that helper keeps a connection
            # open until CONN_MAX_AGE expires, and this thread is about to die. The load
            # test caught the leak - 52 idle Postgres sessions after a cohort of 60, on
            # a server whose default ceiling is 100.
            connections.close_all()


def enqueue(submission_id):
    """Schedule grading for a freshly submitted row.

    Returns True if the row was graded before returning (inline mode), False if it was
    handed to the background and the caller should tell the client to poll.
    """
    if _inline():
        grade_now(submission_id)
        return True
    if _mode() == 'worker':
        return False  # the grade_submissions process will claim it within its poll interval
    thread = threading.Thread(target=_worker, args=(submission_id,),
                              name=f'grade-{submission_id}', daemon=True)
    thread.start()
    return False


# --------------------------------------------------------------------- API shape
def representation(submission):
    """The one shape the client sees, whether the row is pending, graded or failed."""
    stored = submission.answers if isinstance(submission.answers, dict) else {}
    results = stored.get('results') if submission.is_graded else []
    results = results or []
    return {
        'submission_id': submission.pk,
        'exam_type': submission.exam_type,
        'chapter': stored.get('chapter'),
        'grading_status': submission.grading_status,
        'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None,
        'graded_at': submission.graded_at.isoformat() if submission.graded_at else None,
        'score_pct': submission.score_pct if submission.is_graded else None,
        'correct': sum(1 for r in results if r.get('correct')) if submission.is_graded else None,
        'total': len(results) if submission.is_graded else None,
        'results': results,
        'error': submission.grading_error or None,
    }
