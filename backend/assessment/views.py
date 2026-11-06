import csv
import hashlib
import json
from collections import defaultdict

from django.http import StreamingHttpResponse
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import ParticipantProfile, STAFF_ROLES
from accounts.permissions import IsResearcher, IsStaffRole

from . import analytics, grading, manifest, psychometrics, scoring, sittings, timing
from .models import (ExpertRating, ExamSubmission, ExpertGrade, PaperSitting,
                     TeacherReviewAssignment, ItemReviewAssignment, SubmissionReviewAssignment)


class Echo:
    """A write-only file-like object, so csv.writer can feed a streaming response."""

    def write(self, value):
        return value

RATING_FIELDS = {
    'alignment': 'alignment_score',
    'accuracy': 'accuracy_score',
    'clarity': 'clarity_score',
    'difficulty': 'difficulty_score',
    'answerability': 'answerability_score',
}
I_CVI_PASS = 0.78          # Lynn (1986) acceptance threshold for an item's content validity index
ALIGNMENT_RELEVANT = 3     # 3 or 4 on the 1-4 scale counts the item as relevant


def _review_revision(row, fields):
    """Content revision for conditional updates without changing research rows."""
    if row is None:
        return None
    values = [row.pk, row.expert_user_id, *[getattr(row, field) for field in fields]]
    return hashlib.sha256(json.dumps(values, default=str, ensure_ascii=False).encode()).hexdigest()


def _rating_revision(row):
    return _review_revision(row, [*RATING_FIELDS.values(), 'feedback'])


def _grade_revision(row):
    return _review_revision(row, ['assigned_marks', 'max_marks', 'feedback_comments', 'graded_at'])


def _integer_in_range(value, low, high):
    # Do not truncate decimals, accept booleans, or clamp invalid scores.
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        if not value.strip().isascii() or not value.strip().isdigit():
            return None
        try:
            value = int(value.strip())
        except ValueError:
            return None
    return value if isinstance(value, int) and low <= value <= high else None


def _current_expert(request):
    """IsStaffRole guarantees an authenticated teacher or researcher here, so the null
    branch is unreachable; it stays only so the helper is safe if a gate is ever relaxed."""
    return request.user if request.user.is_authenticated else None


def _rating_rows(item_ids):
    rows = ExpertRating.objects.filter(item_key__in=item_ids).values_list(
        'item_key', 'expert_user_id', 'alignment_score')
    per_item = defaultdict(lambda: [0, 0])  # item_key -> [raters, raters scoring >= 3]
    experts = set()
    for item_key, expert_id, alignment in rows:
        per_item[item_key][0] += 1
        if (alignment or 0) >= ALIGNMENT_RELEVANT:
            per_item[item_key][1] += 1
        experts.add(expert_id)
    return per_item, experts


def _i_cvi(counts):
    raters, relevant = counts
    return (relevant / raters) if raters else None


PROTOCOL_ORDER = ('pre', 'post', 'transfer', 'withdrawal')


def _accessible_exam_types(user, is_staff_role):
    """Which forms this caller may open.

    Staff need the whole bank to review it. A participant gets the forms they have
    already sat (so they can revisit their results) plus the next one in protocol
    order - and nothing beyond it. Without this, any enrolled student could simply
    request ?type=withdrawal and read the papers before sitting them, which would make
    the post, transfer and withdrawal scores uninterpretable.
    """
    if is_staff_role:
        return list(PROTOCOL_ORDER)
    return timing.status(user)['available']


def _is_staff_role(user):
    profile = ParticipantProfile.objects.filter(user=user).only('role').first()
    return bool(profile and profile.role in STAFF_ROLES)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assessment_schedule(request):
    schedule = timing.status(request.user)
    if _is_staff_role(request.user):
        schedule['available'] = list(PROTOCOL_ORDER)
    return Response(schedule)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_items(request):
    requested = str(request.GET.get('type') or 'pre').lower()
    if requested not in PROTOCOL_ORDER:
        return Response({'error': f'Unknown exam type: {requested}'}, status=400)

    available = _accessible_exam_types(request.user, _is_staff_role(request.user))
    if requested not in available:
        return Response({
            'error': 'That paper is not open to you yet. Complete the earlier forms first.',
            'exam_type': requested,
            'available': available,
            'schedule': timing.status(request.user),
        }, status=403)

    try:
        items = scoring.items_for(requested)
    except scoring.ItemBankError as exc:
        return Response({'error': str(exc)}, status=500)

    # Serving the paper to a participant opens their sitting of it (staff browsing the
    # bank do not sit papers). A completed paper comes back with its submission id so
    # the page shows the recorded result instead of a fresh form.
    sitting = None
    is_retake = request.GET.get('retake') in ('1', 'true', 'yes')
    if not _is_staff_role(request.user):
        profile = ParticipantProfile.objects.filter(user=request.user).only('assigned_arm').first()
        arm = profile.assigned_arm if profile else ''
        if is_retake:
            sittings.retake_paper(request.user, requested, arm=arm)
        elif (sittings.is_paper_open(request.user, requested)
              or not sittings.already_submitted(request.user, requested)):
            # An explicit retake has an older submission by definition. Refresh its
            # sitting when the participant returns to its tab so it becomes the active
            # paper again instead of leaving another tab's stale sitting in control.
            sittings.open_paper(request.user, requested, arm=arm)
        sitting = sittings.describe(request.user, requested)
        if not is_retake and sitting['status'] != sittings.COMPLETED and sittings.already_submitted(request.user, requested) and not sittings.is_paper_open(request.user, requested):
            # Submitted before sittings existed: report it as completed anyway.
            latest = ExamSubmission.objects.filter(student=request.user, exam_type=requested).order_by('-submitted_at').first()
            sitting = {**sitting, 'status': sittings.COMPLETED, 'submission_id': latest.pk}

    return Response({
        'exam_type': requested,
        'available': available,
        'sitting': sitting,
        'schedule': timing.status(request.user) if not _is_staff_role(request.user) else None,
        'items': [scoring.public_item(i) for i in items],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def retake_exam(request):
    requested = str(request.data.get('exam_type') or 'pre').lower()
    if requested not in PROTOCOL_ORDER:
        return Response({'error': f'Unknown exam type: {requested}'}, status=400)

    available = _accessible_exam_types(request.user, _is_staff_role(request.user))
    if requested not in available:
        return Response({
            'error': 'That paper is not open to you yet.',
            'exam_type': requested,
            'available': available,
            'schedule': timing.status(request.user),
        }, status=403)

    try:
        items = scoring.items_for(requested)
    except scoring.ItemBankError as exc:
        return Response({'error': str(exc)}, status=500)

    sitting = None
    if not _is_staff_role(request.user):
        profile = ParticipantProfile.objects.filter(user=request.user).only('assigned_arm').first()
        arm = profile.assigned_arm if profile else ''
        sittings.retake_paper(request.user, requested, arm=arm)
        sitting = sittings.describe(request.user, requested)

    return Response({
        'exam_type': requested,
        'available': available,
        'sitting': sitting,
        'schedule': timing.status(request.user) if not _is_staff_role(request.user) else None,
        'items': [scoring.public_item(i) for i in items],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_exam(request):
    exam_type = str(request.data.get('exam_type') or 'pre').lower()
    chapter = request.data.get('chapter')
    answers = request.data.get('answers') or {}
    code_answers = request.data.get('code_answers') or {}
    # The submission always belongs to the caller; a `user_id` in the body is ignored.
    student = request.user

    if exam_type not in PROTOCOL_ORDER:
        return Response({'error': f'Unknown exam type: {exam_type}'}, status=400)
    # Same gate as get_items: a paper you cannot open is a paper you cannot submit.
    is_staff = _is_staff_role(student)
    if exam_type not in _accessible_exam_types(student, is_staff):
        return Response({'error': 'That paper is not open to you yet. Complete the previous paper and its waiting period.',
                         'available': _accessible_exam_types(student, is_staff),
                         'schedule': timing.status(student)}, status=403)
    # A paper cannot be submitted twice concurrently or after its sitting is closed.
    # To take a paper again, the participant clicks Retake Assessment which reopens the sitting.
    if not is_staff:
        sitting = PaperSitting.objects.filter(student=student, exam_type=exam_type).first()
        if sitting is not None and not sitting.is_open:
            existing = sitting.submission or ExamSubmission.objects.filter(student=student, exam_type=exam_type).order_by('-submitted_at').first()
            return Response({'error': 'You have already submitted this paper.',
                             'submission_id': existing.pk if existing else None,
                             'grading_status': existing.grading_status if existing else None},
                            status=409)
        elif sitting is None and ExamSubmission.objects.filter(student=student, exam_type=exam_type).exists():
            existing = ExamSubmission.objects.filter(student=student, exam_type=exam_type).order_by('-submitted_at').first()
            return Response({'error': 'You have already submitted this paper.',
                             'submission_id': existing.pk if existing else None,
                             'grading_status': existing.grading_status if existing else None},
                            status=409)

    # Persist first, grade after. The row exists before any compiler runs, so a slow
    # or failed grading pass can never lose the exam. The client never decides the
    # score: nothing from the body reaches score_pct, and grading.py computes it.
    profile = ParticipantProfile.objects.filter(user=student).only('assigned_arm').first()
    submission = ExamSubmission.objects.create(
        student=student,
        exam_type=exam_type,
        arm=profile.assigned_arm if profile else '',  # the mode they sat this paper in
        score_pct=None,
        grading_status=ExamSubmission.PENDING,
        answers={'answers': answers if isinstance(answers, dict) else {},
                 'code_answers': code_answers if isinstance(code_answers, dict) else {},
                 'chapter': chapter,
                 'device_id': getattr(request, 'device_id', None)},
    )
    if not is_staff:
        # Closes the sitting: time-on-paper is now measurable, and the tutor is free again.
        sittings.close_paper(student, exam_type, submission, arm=submission.arm)
    graded_now = grading.enqueue(submission.pk)
    submission.refresh_from_db()
    payload = grading.representation(submission)
    payload['status'] = 'success'
    return Response(payload, status=200 if graded_now and submission.is_graded else 202)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_submission(request, pk):
    """Poll a submission's grading state. Owner or staff only - a submission id is
    sequential, so without this check any participant could read anyone's results."""
    submission = ExamSubmission.objects.filter(pk=pk).first()
    if submission is None:
        return Response({'error': 'No such submission.'}, status=404)
    if submission.student_id != request.user.id and not _is_staff_role(request.user):
        return Response({'error': 'No such submission.'}, status=404)
    return Response(grading.representation(submission))


@api_view(['GET'])
@permission_classes([IsStaffRole])
def get_expert_reviews(request):
    try:
        bank_items = scoring.all_items()
    except scoring.ItemBankError as exc:
        return Response({'error': str(exc)}, status=500)

    item_ids = [item['id'] for _, item in bank_items]
    per_item, experts = _rating_rows(item_ids)
    expert = _current_expert(request)
    allocated = TeacherReviewAssignment.objects.filter(expert_user=expert).exists()
    assigned_keys = set(ItemReviewAssignment.objects.filter(expert_user=expert).values_list('item_key', flat=True))
    mine = {r.item_key: r for r in ExpertRating.objects.filter(
        item_key__in=item_ids, expert_user=expert)}

    items_to_review = []
    for exam_type, item in bank_items:
        row = mine.get(item['id'])
        public = scoring.public_item(item)
        review = {
            'id': item['id'],
            'exam_type': exam_type,
            'type': item.get('type'),
            'chapter': item.get('chapter'),
            'title': item.get('title'),
            'question_text': item.get('question'),
            'curriculum_ref': item.get('curriculum_ref'),
            'ratings_count': per_item.get(item['id'], (0, 0))[0],
            'rating_revision': _rating_revision(row),
            'is_assigned': not allocated or item['id'] in assigned_keys,
            'my_rating': None if row is None else {
                'alignment': row.alignment_score, 'accuracy': row.accuracy_score,
                'clarity': row.clarity_score, 'difficulty': row.difficulty_score,
                'answerability': row.answerability_score, 'feedback': row.feedback or '',
            },
        }
        if 'options' in public:
            review['options'] = public['options']
        if 'code_snippet' in public:
            review['code_snippet'] = public['code_snippet']
        items_to_review.append(review)

    i_cvis = [_i_cvi(c) for c in per_item.values() if c[0]]
    return Response({
        'items_to_review': items_to_review,
        'cvi_stats': {
            'total_items': len(bank_items),
            'rated_items': len(i_cvis),
            'expert_count': len(experts),
            'ratings_count': sum(c[0] for c in per_item.values()),
            'i_cvi_pass_rate': (sum(1 for v in i_cvis if v >= I_CVI_PASS) / len(i_cvis)) if i_cvis else None,
            's_cvi_ave': (sum(i_cvis) / len(i_cvis)) if i_cvis else None,
        },
    })


@api_view(['POST'])
@permission_classes([IsStaffRole])
def submit_expert_rating(request):
    item_id = str(request.data.get('item_id') or '').strip()
    _, item = scoring.find_item(item_id) if item_id else (None, None)
    if item is None:
        return Response({'error': f'Unknown item_id: {item_id or "(missing)"}'}, status=400)

    payload = request.data.get('ratings')
    if not isinstance(payload, dict):
        return Response({'error': 'Provide all five rubric scores as an object.'}, status=400)
    defaults = {'feedback': str(request.data.get('feedback') or '')}
    errors = {}
    for key, field in RATING_FIELDS.items():
        score = _integer_in_range(payload.get(key), 1, 4)
        if score is None:
            errors[key] = 'Choose an integer score from 1 to 4.'
        else:
            defaults[field] = score
    if errors:
        return Response({'error': 'Score all five criteria from 1 to 4.', 'fields': errors}, status=400)

    expert = _current_expert(request)
    with transaction.atomic():
        # Lock the expert on first creation as well, when no rating row exists.
        type(expert).objects.select_for_update().get(pk=expert.pk)
        existing = ExpertRating.objects.filter(expert_user=expert, item_key=item_id).first()
        if ('expected_revision' in request.data
                and request.data['expected_revision'] != _rating_revision(existing)):
            return Response({'error': 'This rating changed in another session. Reload the latest rating before submitting.',
                             'reason': 'review_conflict'}, status=409)
        row, _ = ExpertRating.objects.update_or_create(
            expert_user=expert, item_key=item_id, defaults=defaults)
        per_item, _ = _rating_rows([item_id])
        return Response({'status': 'success', 'rated': True, 'item_id': item_id,
                         'rating_revision': _rating_revision(row),
                         'i_cvi': _i_cvi(per_item[item_id]) if item_id in per_item else None})


@api_view(['GET'])
@permission_classes([IsStaffRole])
def get_student_submissions(request):
    """All submissions for expert grading, labelled by participant_code."""
    submissions = (ExamSubmission.objects
                   .select_related('student', 'student__profile')
                   .prefetch_related('grades', 'grades__expert_user')
                   .order_by('-submitted_at', '-pk'))

    expert = _current_expert(request)
    allocated = TeacherReviewAssignment.objects.filter(expert_user=expert).exists()
    assigned_ids = set(SubmissionReviewAssignment.objects.filter(expert_user=expert).values_list('submission_id', flat=True))
    payload, banks, timing_records = [], {}, {}
    for sub in submissions:
        stored = sub.answers if isinstance(sub.answers, dict) else {}
        results = stored.get('results') or []
        code_answers = stored.get('code_answers') or {}
        profile = getattr(sub.student, 'profile', None)
        participant_code = getattr(profile, 'participant_code', None)

        if sub.exam_type not in banks:
            try:
                banks[sub.exam_type] = {i['id']: i for i in scoring.items_for(sub.exam_type)}
            except scoring.ItemBankError:
                banks[sub.exam_type] = {}
        titles = banks[sub.exam_type]

        code_blocks = []
        for res in results:
            if res.get('type') not in ('c_programming', 'html_coding'):
                continue
            item = titles.get(res.get('item_id'), {})
            code_blocks.append({
                'item_id': res.get('item_id'),
                'title': res.get('title') or item.get('title'),
                'question': item.get('question', ''),
                'code': code_answers.get(res.get('item_id'), ''),
                'auto': {
                    'status': res.get('status') or ('SUCCESS' if res.get('correct') else 'NOT_PASSED'),
                    'passed_count': res.get('passed_count'),
                    'total_tests': res.get('total_tests'),
                    'detail': res.get('detail', ''),
                },
            })

        # Marking is per expert. A colleague's completed review must not prefill this
        # expert's form or make their own assigned work appear completed.
        grades = sorted((g for g in sub.grades.all() if g.expert_user_id == expert.pk),
                        key=lambda g: (g.graded_at, g.pk), reverse=True)
        grade = grades[0] if grades else None
        if sub.student_id and sub.student_id not in timing_records:
            timing_records[sub.student_id] = timing.records(sub.student)
        payload.append({
            'id': sub.id,
            'is_assigned': not allocated or sub.id in assigned_ids,
            'my_grade_completed': bool(grade and grade.is_graded),
            'student_label': participant_code or getattr(sub.student, 'username', None) or 'Anonymous',
            'participant_code': participant_code,
            'exam_type': sub.exam_type,
            'chapter': stored.get('chapter'),
            'submitted_at': sub.submitted_at.isoformat(),
            'timing': timing.report(sub.student, sub.exam_type, sub.submitted_at,
                                    timing_records[sub.student_id]) if sub.student_id else None,
            'grading_status': sub.grading_status,
            'grading_error': sub.grading_error or None,
            'score_pct': sub.score_pct if sub.is_graded else None,
            'correct': sum(1 for r in results if r.get('correct')) if results else None,
            'total': len(results) or None,
            'code_answers': code_blocks,
            'grade_revision': _grade_revision(grade),
            'assigned_marks': grade.assigned_marks if grade else None,
            'max_marks': grade.max_marks if grade else 100,
            'feedback': (grade.feedback_comments or '') if grade else '',
            'status': 'GRADED' if grade and grade.is_graded else 'PENDING_REVIEW',
            'graded_by': getattr(grade.expert_user, 'username', None) if grade else None,
        })

    return Response({'count': len(payload), 'submissions': payload})


@api_view(['POST'])
@permission_classes([IsStaffRole])
def grade_student_submission(request):
    submission_id = _integer_in_range(request.data.get('submission_id'), 1, 9223372036854775807)
    marks = _integer_in_range(request.data.get('assigned_marks'), 0, 100)
    if marks is None:
        return Response({'error': 'Enter an integer mark from 0 to 100.',
                         'fields': {'assigned_marks': 'Enter an integer mark from 0 to 100.'}}, status=400)

    with transaction.atomic():
        # Serialize checks on the submission, including when no grade exists yet.
        submission = ExamSubmission.objects.select_for_update().filter(pk=submission_id).first()
        if submission is None:
            return Response({'error': f'Submission {submission_id} does not exist.'}, status=404)
        expert = _current_expert(request)
        latest = ExpertGrade.objects.filter(submission=submission, expert_user=expert).first()
        if ('expected_revision' in request.data
                and request.data['expected_revision'] != _grade_revision(latest)):
            return Response({'error': 'This grade changed in another session. Reload the latest marks before saving.',
                             'reason': 'review_conflict'}, status=409)
        grade, _ = ExpertGrade.objects.update_or_create(
            submission=submission, expert_user=expert,
            defaults={'assigned_marks': marks, 'max_marks': 100, 'is_graded': True,
                      'graded_at': timezone.now(),
                      'feedback_comments': str(request.data.get('feedback') or '')},
        )
        return Response({'status': 'success', 'submission_id': submission.id,
                         'assigned_marks': grade.assigned_marks, 'max_marks': 100,
                         'grade_revision': _grade_revision(grade),
                         'graded_at': grade.graded_at.isoformat()})


@api_view(['GET'])
@permission_classes([IsResearcher])
def get_admin_stats(request):
    """Study-wide outcomes computed from the collected data.

    Every field comes from ExamSubmission / InteractionLog rows. Outcomes that the
    data cannot yet support come back as null with a `note`; the client renders that
    as "not available" rather than substituting a number.
    """
    return Response(analytics.study_stats())


@api_view(['GET'])
@permission_classes([IsStaffRole])
def certification_report(request):
    """Is the item bank fit to measure anything yet?

    Expert content validity (I-CVI, modified kappa, S-CVI) plus pilot item analysis
    (difficulty, point-biserial discrimination, KR-20) and a parallel-forms comparison,
    with an explicit list of what is still blocking certification.
    """
    try:
        return Response(psychometrics.certification_report())
    except scoring.ItemBankError as exc:
        return Response({'error': str(exc)}, status=500)


@api_view(['GET'])
@permission_classes([IsResearcher])
def study_manifest(request):
    """The exact configuration that produced the data - model, temperature, fallback
    chain, switch policy, sandbox tier, item-bank hash, code version. Offered as a
    download so it can sit next to the exported dataset in the thesis appendix."""
    response = Response(manifest.build())
    stamp = timezone.localtime().strftime('%Y%m%d-%H%M')
    response['Content-Disposition'] = f'attachment; filename="trace_tutor_manifest_{stamp}.json"'
    return response


@api_view(['GET'])
@permission_classes([IsResearcher])
def export_dataset(request):
    """One CSV row per enrolled participant, pseudonymous (participant_code, never a name).

    Streamed so the export stays flat in memory as the cohort grows.
    """
    rows = analytics.participant_rows()
    stamp = timezone.localtime().strftime('%Y%m%d-%H%M')

    def csv_lines():
        buffer = Echo()
        writer = csv.DictWriter(buffer, fieldnames=analytics.CSV_COLUMNS, extrasaction='ignore')
        yield writer.writerow({c: c for c in analytics.CSV_COLUMNS})
        for row in rows:
            yield writer.writerow(row)

    response = StreamingHttpResponse(csv_lines(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="trace_tutor_dataset_{stamp}.csv"'
    response['X-Trace-Row-Count'] = str(len(rows))
    return response
