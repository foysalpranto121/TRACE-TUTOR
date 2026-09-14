from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import caches
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission, ExpertGrade
from .models import InteractionLog
from .signals import dashboard_cache_key


def resolve_user(user_id=None, username=None, create=False):
    """Frontend sessions may carry a DB id or only a display username (demo sessions)."""
    user = None
    if user_id not in (None, ''):
        try:
            user = User.objects.filter(id=int(user_id)).first()
        except (TypeError, ValueError):
            user = None
    if user is None and username:
        name = str(username)[:150]
        if create:
            user, _ = User.objects.get_or_create(username=name)
        else:
            user = User.objects.filter(username=name).first()
    return user


@api_view(['POST'])
@permission_classes([AllowAny])
def log_telemetry(request):
    event_type = request.data.get('event_type', 'GENERIC_EVENT')
    event_data = request.data.get('event_data') or {}
    if not isinstance(event_data, dict):
        event_data = {'value': event_data}
    # Anonymous device id from the signed cookie (trace_backend.middleware) - research metadata only.
    device_id = getattr(request, 'device_id', None)
    if device_id and 'device_id' not in event_data:
        event_data['device_id'] = device_id
    user = resolve_user(event_data.get('user_id'), event_data.get('username'), create=True)
    problem_id = str(event_data.get('problem_id') or '')[:50] or None

    InteractionLog.objects.create(
        user=user,
        event_type=str(event_type)[:50],
        payload=event_data,
        arm=event_data.get('arm') or 'REASONING_VISIBLE',
        problem_id=problem_id,
    )
    return Response({'status': 'success', 'logged': True})


def _summarize(log):
    p = log.payload or {}
    t = log.event_type
    if t == 'CODE_RESULT':
        total = p.get('total') or 0
        return f"{p.get('status', '?')} - {p.get('passed_count', 0)}/{total} checks passed ({p.get('language', 'c')})"
    if t == 'HELP_REQUEST':
        return f"Asked AI: \"{str(p.get('prompt', ''))[:90]}\""
    if t == 'COPY_PASTE':
        return f"Copied {p.get('code_length', 0)} characters of AI-generated code"
    if t == 'SUBMIT_ASSESSMENT':
        return f"Submitted {p.get('exam_type', '?')} test - score {p.get('score', 0)}%"
    if t == 'ARM_TOGGLE_MANUAL':
        return f"Switched arm to {p.get('new_arm', '?')}"
    if t == 'WORKSPACE_ENTER':
        return 'Opened the coding workspace'
    return t.replace('_', ' ').title()


def _local_date(dt):
    return timezone.localtime(dt).date()


@api_view(['GET'])
@permission_classes([AllowAny])
def dashboard_summary(request):
    """Per-user summary served from the memory cache for up to a minute; it is dropped the moment the
    user's logs, submissions or profile change (logging_app/signals.py), so XP updates stay instant."""
    user = resolve_user(request.GET.get('user_id'), request.GET.get('username'))
    key = dashboard_cache_key(user.id if user else None)
    data = caches['default'].get(key)
    hit = data is not None
    if not hit:
        data = _build_dashboard(user)
        caches['default'].set(key, data, settings.DASHBOARD_CACHE_SECONDS)
    response = Response(data)
    response['X-Trace-Cache'] = 'hit' if hit else 'miss'
    return response


def _build_dashboard(user):
    today = timezone.localtime().date()
    logs = list(InteractionLog.objects.filter(user=user).order_by('-timestamp')[:3000]) if user else []

    problems = {}
    for log in reversed(logs):
        pid = log.problem_id or (log.payload or {}).get('problem_id')
        if not pid:
            continue
        p = problems.setdefault(pid, {
            'problem_id': pid, 'attempts': 0, 'solved': False, 'help_requests': 0,
            'last_status': None, 'best_passed': 0, 'total_tests': 0, 'language': None,
            'first_at': None, 'last_at': None,
        })
        payload = log.payload or {}
        if log.event_type == 'CODE_RESULT':
            p['attempts'] += 1
            status = payload.get('status')
            passed = int(payload.get('passed_count') or 0)
            total = int(payload.get('total') or 0)
            p['solved'] = p['solved'] or status == 'SUCCESS'
            p['best_passed'] = max(p['best_passed'], passed)
            p['total_tests'] = max(p['total_tests'], total)
            p['last_status'] = status
            p['language'] = payload.get('language')
        elif log.event_type == 'HELP_REQUEST':
            p['help_requests'] += 1
        elif log.event_type not in ('WORKSPACE_ENTER',):
            continue
        ts = timezone.localtime(log.timestamp).isoformat()
        p['first_at'] = p['first_at'] or ts
        p['last_at'] = ts

    counts = Counter(l.event_type for l in logs)
    day_set = {_local_date(l.timestamp) for l in logs}
    streak, cursor = 0, today
    if today not in day_set and (today - timedelta(days=1)) in day_set:
        cursor = today - timedelta(days=1)
    while cursor in day_set:
        streak += 1
        cursor -= timedelta(days=1)

    daily = []
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        daily.append({'date': day.isoformat(), 'label': day.strftime('%d %b'), 'code_runs': 0, 'help_requests': 0, 'solved': 0})
    by_date = {d['date']: d for d in daily}
    for l in logs:
        bucket = by_date.get(_local_date(l.timestamp).isoformat())
        if not bucket:
            continue
        if l.event_type == 'CODE_RESULT':
            bucket['code_runs'] += 1
            if (l.payload or {}).get('status') == 'SUCCESS':
                bucket['solved'] += 1
        elif l.event_type == 'HELP_REQUEST':
            bucket['help_requests'] += 1

    assessments = {}
    if user:
        for s in ExamSubmission.objects.filter(student=user).order_by('submitted_at'):
            a = assessments.setdefault(s.exam_type, {'exam_type': s.exam_type, 'attempts': 0, 'latest_score': None, 'best_score': 0, 'last_at': None})
            a['attempts'] += 1
            a['latest_score'] = s.score_pct
            a['best_score'] = max(a['best_score'], s.score_pct)
            a['last_at'] = timezone.localtime(s.submitted_at).isoformat()

    recent = [
        {
            'event_type': l.event_type,
            'timestamp': timezone.localtime(l.timestamp).isoformat(),
            'problem_id': l.problem_id or (l.payload or {}).get('problem_id'),
            'detail': _summarize(l),
            'status': (l.payload or {}).get('status'),
        }
        for l in logs if l.event_type not in ('CODE_RUN', 'WORKSPACE_ENTER')
    ][:15]

    profile = None
    if user:
        prof = ParticipantProfile.objects.filter(user=user).first()
        profile = {
            'id': user.id, 'username': user.username,
            'role': prof.role if prof else 'STUDENT',
            'arm': prof.assigned_arm if prof else None,
            'language': prof.preferred_language if prof else 'bn',
            'grade': prof.grade if prof else None,
            'joined': timezone.localtime(user.date_joined).isoformat(),
        }

    arm_counts = Counter(ParticipantProfile.objects.filter(role='STUDENT').values_list('assigned_arm', flat=True))
    overview = {
        'participants': ParticipantProfile.objects.count(),
        'students': ParticipantProfile.objects.filter(role='STUDENT').count(),
        'arms': dict(arm_counts),
        'submissions': ExamSubmission.objects.count(),
        'expert_grades': ExpertGrade.objects.count(),
        'events': InteractionLog.objects.count(),
        'help_requests': InteractionLog.objects.filter(event_type='HELP_REQUEST').count(),
        'code_runs': InteractionLog.objects.filter(event_type='CODE_RESULT').count(),
        'active_today': InteractionLog.objects.filter(timestamp__date=today).values('user').distinct().count(),
    }

    return {
        'profile': profile,
        'stats': {
            'problems_attempted': sum(1 for p in problems.values() if p['attempts'] > 0),
            'problems_solved': sum(1 for p in problems.values() if p['solved']),
            'code_runs': counts.get('CODE_RESULT', 0),
            'help_requests': counts.get('HELP_REQUEST', 0),
            'copy_paste': counts.get('COPY_PASTE', 0),
            'streak_days': streak,
            'active_days': len(day_set),
            'last_active': timezone.localtime(logs[0].timestamp).isoformat() if logs else None,
        },
        'problems': list(problems.values()),
        'daily': daily,
        'assessments': assessments,
        'recent': recent,
        'overview': overview,
    }
