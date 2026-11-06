"""Sequential, resumable evaluation-fixture imports. PAYLOAD is injected by the caller.

Each participant commits their summary first, then gets genuinely graded generated
answers. Missing exams are omitted. Existing data and teacher grades are preserved.
"""
import copy
import hashlib
import json
import traceback
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import ExamSubmission
from assessment.views import get_student_submissions
from logging_app.models import InteractionLog
from rest_framework.test import APIRequestFactory, force_authenticate


def targets_for(source):
    targets = {}
    for exam in ('pre', 'post', 'transfer', 'withdrawal'):
        score = source[f'{exam}_score_pct']
        if score is not None:
            counts = [n for n in range(16) if round(n * 100 / 15) == score]
            assert len(counts) == 1, (source['participant_id'], exam, score)
            targets[exam] = (score, counts[0])
    return targets


def validate_source(source):
    assert len(source) == 29
    assert source['enrolled_arm'] in {'ANSWER_ONLY', 'REASONING_VISIBLE'}
    assert source['completion_status'] in {'COMPLETE', 'WITHDRAWAL_MISSING'}
    pre, post = source['pre_score_pct'], source['post_score_pct']
    assert pre < 100 and source['post_minus_pre_pp'] == post - pre
    gain = Decimal(post - pre) / Decimal(100 - pre)
    for field, value in [('normalized_gain', gain), ('normalized_gain_sq', gain ** 2)]:
        assert Decimal(str(source[field])) == value.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP), (source['participant_id'], field)
    if source['completion_status'] == 'WITHDRAWAL_MISSING':
        assert all(source[f] is None for f in ('withdrawal_score_pct', 'withdrawal_minus_post_pp', 'withdrawal_drop_sq'))
    else:
        drop = source['withdrawal_score_pct'] - post
        assert source['withdrawal_minus_post_pp'] == drop
        assert source['withdrawal_drop_sq'] == drop ** 2
    targets = targets_for(source)
    assert len(targets) == (3 if source['completion_status'] == 'WITHDRAWAL_MISSING' else 4)


def keys(source):
    code = source['participant_id']
    return f'user-supplied-participant-summary:{code}:v1', f'{code}:generated-correct-only-evaluation:v1'


def expected_profile(source):
    return {
        'participant_code': source['participant_id'], 'role': 'STUDENT',
        'full_name': source['student_name'], 'school_name': source['college_name'],
        'division': source['division'], 'assigned_arm': source['enrolled_arm'],
        'enrolled_arm': source['enrolled_arm'], 'grade': str(source['grade']),
        'age': source['age_years'], 'gender': source['gender'],
        'prior_experience': source['prior_experience'], 'device_type': source['device_type'],
        'weekly_study_hours': source['weekly_study_hours'],
    }


def read_rows(source):
    profile = ParticipantProfile.objects.select_related('user').get(participant_code=source['participant_id'])
    assert profile.user.email == source['gmail'], 'Email mismatch'
    assert all(getattr(profile, k) == v for k, v in expected_profile(source).items()), 'Profile mismatch'
    assert profile.withdrawn_at is None, 'Participant withdrew from study'
    import_key, _ = keys(source)
    receipt = InteractionLog.objects.get(user=profile.user, event_type='SUMMARY_IMPORT', payload__import_key=import_key)
    assert receipt.payload['source'] == source, 'Original summary mismatch'
    rows = list(ExamSubmission.objects.filter(student=profile.user).order_by('pk'))
    targets = targets_for(source)
    assert len(rows) == len(targets)
    assert {r.exam_type: r.score_pct for r in rows} == {e: t[0] for e, t in targets.items()}
    assert all(r.arm == source['enrolled_arm'] and r.is_graded for r in rows)
    return profile, rows


def import_summary(source):
    code = source['participant_id']
    with transaction.atomic():
        if ParticipantProfile.objects.filter(participant_code=code).exists():
            profile, _ = read_rows(source)
            return profile, False
        assert not User.objects.filter(username=code).exists(), 'Username conflict'
        assert not User.objects.filter(email__iexact=source['gmail']).exists(), 'Email conflict'
        name = source['student_name'].split(' ', 1)
        user = User(username=code, email=source['gmail'], first_name=name[0], last_name=name[1] if len(name) > 1 else '')
        user.set_unusable_password()
        user.save()
        profile = ParticipantProfile.objects.create(user=user, **expected_profile(source))
        import_key, _ = keys(source)
        for exam, (score, _) in targets_for(source).items():
            ExamSubmission.objects.create(
                student=user, exam_type=exam, arm=source['enrolled_arm'], score_pct=score,
                grading_status=ExamSubmission.GRADED,
                answers={'answers': {}, 'code_answers': {}, 'results': [],
                         'import_metadata': {'import_key': import_key, 'kind': 'summary_only',
                                             'score_source': 'user_supplied', 'answers_available': False,
                                             'original_submission_time_available': False}},
            )
        InteractionLog.objects.create(
            user=user, event_type='SUMMARY_IMPORT', arm=source['enrolled_arm'],
            payload={'import_key': import_key, 'source': source,
                     'note': 'Aggregate import receipt, not observed learning events. Creation times are import times.'},
        )
        read_rows(source)
    return profile, True


def make_answers(source):
    prepared = {}
    for exam, (score, correct_count) in targets_for(source).items():
        items = scoring.items_for(exam)
        assert len(items) == 15
        code_items = [i for i in items if i['type'] in scoring.CODE_TYPES]
        mcqs = [i for i in items if i['type'] not in scoring.CODE_TYPES]
        assert len(code_items) == 8 and len(mcqs) == 7
        # Interleave C and HTML tasks, and rotate selection by participant code.
        c_items = [i for i in code_items if i['type'] == 'c_programming']
        html_items = [i for i in code_items if i['type'] == 'html_coding']
        order = []
        for index in range(max(len(c_items), len(html_items))):
            for group in (c_items, html_items):
                if index < len(group):
                    order.append(group[index])
        offset = int(source['participant_id'].split('-')[1]) % len(order)
        order = order[offset:] + order[:offset]
        code_count = max(correct_count - len(mcqs), min(correct_count, (correct_count * 8 + 7) // 15))
        if correct_count:
            code_count = max(1, code_count)
        selected_code = order[:code_count]
        code_answers = {i['id']: PAYLOAD['code'][i['id']] for i in selected_code}
        chosen = {i['id']: str(i['keyed_answer']) for i in mcqs[:correct_count-code_count]}
        actual_score, correct, total, results = scoring.grade_submission(exam, chosen, code_answers)
        assert (actual_score, correct, total) == (score, correct_count, 15), (source['participant_id'], exam, results)
        supplied = set(chosen) | set(code_answers)
        assert all(r['correct'] == (r['item_id'] in supplied) for r in results)
        assert all(r.get('status') == 'NO_ANSWER' for r in results if r['type'] in scoring.CODE_TYPES and r['item_id'] not in supplied)
        prepared[exam] = {'answers': chosen, 'code_answers': code_answers, 'results': results}
        print('GRADED', source['participant_id'], exam, actual_score, 'correct', correct, 'code', code_count, flush=True)
    return prepared


def attach_answers(source):
    profile, original = read_rows(source)
    _, attach_key = keys(source)
    if InteractionLog.objects.filter(user=profile.user, payload__operation_key=attach_key).exists():
        return False
    assert all(not r.answers.get('answers') and not r.answers.get('code_answers') and not r.grades.exists() for r in original), 'Existing answers or teacher grades'
    snapshots = {r.pk: copy.deepcopy(r.answers) for r in original}
    prepared = make_answers(source)
    with transaction.atomic():
        rows = list(ExamSubmission.objects.select_for_update().filter(student=profile.user).order_by('pk'))
        assert [r.pk for r in rows] == [r.pk for r in original]
        assert not InteractionLog.objects.filter(user=profile.user, payload__operation_key=attach_key).exists()
        for row in rows:
            assert row.answers == snapshots[row.pk] and not row.grades.exists()
            assert row.score_pct == targets_for(source)[row.exam_type][0]
            stored = copy.deepcopy(row.answers)
            stored.update(prepared[row.exam_type])
            stored['import_metadata'].update({
                'kind': 'generated_evaluation_fixture', 'answers_available': True,
                'answers_source': 'AI_generated_for_user_authorized_teacher_flow_test',
                'operation_key': attach_key, 'unanswered_policy': 'incorrect_items_left_blank',
                'automatically_verified_score': row.score_pct,
            })
            row.answers = stored
            row.graded_at = timezone.now()
            row.save(update_fields=['answers', 'graded_at'])
        InteractionLog.objects.create(
            user=profile.user, event_type='EVALUATION_FIXTURE_ATTACH', arm=source['enrolled_arm'],
            payload={'operation_key': attach_key, 'synthetic': True,
                     'purpose': 'User-authorized teacher evaluation workflow test; correct answers only',
                     'previous_answers': {str(k): v for k, v in snapshots.items()},
                     'submission_ids': [r.pk for r in rows]},
        )
    return True


def verify(source, staff):
    _, saved = read_rows(source)
    targets = targets_for(source)
    request = APIRequestFactory().get('/api/assessment/student-submissions/')
    force_authenticate(request, user=staff)
    response = get_student_submissions(request)
    assert response.status_code == 200
    rows = [r for r in response.data['submissions'] if r['participant_code'] == source['participant_id']]
    assert len(rows) == len(targets)
    assert {r['exam_type'] for r in rows} == set(targets)
    for row in rows:
        assert (row['score_pct'], row['correct'], row['total']) == (*targets[row['exam_type']], 15)
        assert len(row['code_answers']) == 8
        for code in row['code_answers']:
            assert code['auto']['status'] == ('SUCCESS' if code['code'].strip() else 'NO_ANSWER')
    for row in saved:
        supplied = set(row.answers['answers']) | set(row.answers['code_answers'])
        assert all(r['correct'] == (r['item_id'] in supplied) for r in row.answers['results'])
        assert len(row.answers['results']) == 15
        assert row.answers['import_metadata']['kind'] == 'generated_evaluation_fixture'
    return {'participant': source['participant_id'],
            'scores': {r['exam_type']: r['score_pct'] for r in rows},
            'submissions': [r['id'] for r in rows],
            'nonblank_code': sum(bool(c['code'].strip()) for r in rows for c in r['code_answers']),
            'withdrawal_missing': 'withdrawal' not in targets,
            'statuses': sorted({r['status'] for r in rows})}


def run():
    assert hashlib.sha256(scoring.ITEM_BANK_PATH.read_bytes()).hexdigest() == PAYLOAD['bank_hash']
    sources = PAYLOAD['rows']
    assert len({r['participant_id'] for r in sources}) == len(sources)
    assert len({r['gmail'].casefold() for r in sources}) == len(sources)
    for source in sources:
        validate_source(source)
    staff_profile = ParticipantProfile.objects.filter(role__in=['EXPERT_TEACHER', 'RESEARCHER_ADMIN']).select_related('user').first()
    assert staff_profile, 'Staff account required for portal verification'
    reports, failures = [], []
    for source in sources:
        code = source['participant_id']
        try:
            print('START', code, flush=True)
            _, created = import_summary(source)
            print('SUMMARY_COMMITTED' if created else 'EXISTING_SUMMARY_VERIFIED', code, flush=True)
            attached = attach_answers(source)
            report = verify(source, staff_profile.user)
            report.update({'created': created, 'answers_attached': attached})
            reports.append(report)
            print('DONE', json.dumps(report), flush=True)
        except Exception as exc:
            failures.append({'participant': code, 'error': str(exc)})
            print('FAILED', code, str(exc), flush=True)
            traceback.print_exc()
    # Confirm all requested participants again after the complete sequential run.
    if not failures:
        for source in sources:
            verify(source, staff_profile.user)
    print('BATCH_RESULT', json.dumps({'verified': len(reports), 'created': sum(r['created'] for r in reports),
          'existing': sum(not r['created'] for r in reports),
          'new_submissions': sum(len(r['submissions']) for r in reports if r['created']),
          'new_code_answers': sum(r['nonblank_code'] for r in reports if r['answers_attached']),
          'failures': failures, 'reports': reports}), flush=True)
    assert not failures, 'One or more participants were not completed; see FAILED entries'


run()
