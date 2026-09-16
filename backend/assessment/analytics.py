"""Real study analytics computed from the database.

Everything here derives from ExamSubmission and InteractionLog rows. Nothing is
seeded, defaulted or illustrative: a metric that cannot be computed from the data
collected so far is returned as None, and the caller renders it as "not available".
That is deliberate - this dashboard is read as study output, so a placeholder number
here is indistinguishable from a finding.

Statistics are Welch's unequal-variance t-test plus Cohen's d (pooled SD). The
two-tailed p-value comes from the regularised incomplete beta function below, so the
platform needs no SciPy.
"""
import math
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Min, Q

from accounts.models import ParticipantProfile
from logging_app.models import InteractionLog
from . import sittings
from .models import ExamSubmission

EXAM_TYPES = ('pre', 'post', 'transfer', 'withdrawal')
ARMS = ('REASONING_VISIBLE', 'ANSWER_ONLY')

# Telemetry events summarised per participant in the export.
COUNTED_EVENTS = ('HELP_REQUEST', 'CODE_RESULT', 'COPY_PASTE', 'ARM_SWITCH')

# `arm` is the arm allocated at enrolment - the intent-to-treat grouping every outcome
# is compared by. `current_arm` and `arm_switches` are there so a per-protocol view can
# be built from the same file.
CSV_COLUMNS = [
    'participant_code', 'arm', 'current_arm', 'arm_switches', 'switched_during_protocol',
    'withdrawn', 'consent_given', 'grade', 'medium', 'area_type',
    'prior_experience', 'ai_tool_familiarity',
    'pre', 'post', 'transfer', 'withdrawal',
    'pre_arm', 'post_arm', 'transfer_arm', 'withdrawal_arm',
    'pre_minutes', 'post_minutes', 'transfer_minutes', 'withdrawal_minutes',
    'normalized_gain', 'withdrawal_drop',
    'help_requests', 'help_fallbacks', 'code_runs', 'copy_paste',
    'pre_attempts', 'post_attempts', 'transfer_attempts', 'withdrawal_attempts',
    'first_submission_at', 'last_submission_at',
]


# --------------------------------------------------------------------------- stats
def _betacf(a, b, x, max_iter=200, eps=3e-16, tiny=1e-300):
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def regularized_incomplete_beta(a, b, x):
    """I_x(a, b), the regularised incomplete beta function."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_bt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
              + a * math.log(x) + b * math.log1p(-x))
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def two_tailed_t_p_value(t, df):
    """P(|T| > |t|) for Student's t with df degrees of freedom."""
    if df <= 0 or not math.isfinite(t) or not math.isfinite(df):
        return None
    return regularized_incomplete_beta(df / 2.0, 0.5, df / (df + t * t))


def _mean(values):
    return sum(values) / len(values)


def _variance(values):
    """Sample variance (n-1). Undefined for fewer than two observations."""
    if len(values) < 2:
        return None
    m = _mean(values)
    return sum((v - m) ** 2 for v in values) / (len(values) - 1)


def describe(values):
    """n / mean / sd for one group, with mean and sd None when undefined."""
    values = [float(v) for v in values if v is not None]
    var = _variance(values)
    return {
        'n': len(values),
        'mean': round(_mean(values), 4) if values else None,
        'sd': round(math.sqrt(var), 4) if var is not None else None,
    }


def compare_arms(treatment, control):
    """Welch's t-test + Cohen's d between the two arms.

    Returns per-arm descriptives always, and the inferential fields only when both
    arms hold at least two observations and neither group is perfectly constant.
    """
    t_vals = [float(v) for v in treatment if v is not None]
    c_vals = [float(v) for v in control if v is not None]
    out = {
        'treatment': describe(t_vals),
        'control': describe(c_vals),
        'mean_difference': None,
        't_statistic': None,
        'df': None,
        'p_value': None,
        'cohens_d': None,
        'note': None,
    }
    n1, n2 = len(t_vals), len(c_vals)
    if n1 < 2 or n2 < 2:
        out['note'] = 'Needs at least two participants per arm.'
        return out

    m1, m2 = _mean(t_vals), _mean(c_vals)
    v1, v2 = _variance(t_vals), _variance(c_vals)
    out['mean_difference'] = round(m1 - m2, 4)
    se_sq = v1 / n1 + v2 / n2
    if se_sq <= 0:
        out['note'] = 'Both arms are constant; there is no variance to test.'
        return out

    t_stat = (m1 - m2) / math.sqrt(se_sq)
    df_den = (v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1)
    df = (se_sq ** 2) / df_den if df_den > 0 else None
    p = two_tailed_t_p_value(t_stat, df) if df else None

    pooled_var = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
    d = (m1 - m2) / math.sqrt(pooled_var) if pooled_var > 0 else None

    out.update({
        't_statistic': round(t_stat, 4),
        'df': round(df, 2) if df else None,
        'p_value': round(p, 6) if p is not None else None,
        'cohens_d': round(d, 4) if d is not None else None,
    })
    return out


# --------------------------------------------------------------------- participants
def _first_submissions():
    """student_id -> exam_type -> {score, attempts, first_at, last_at}.

    The first submission of each form is the protocol-conformant one; later retakes
    are counted in `attempts` so anomalies stay visible instead of being averaged in.
    """
    by_student = defaultdict(dict)
    # Only graded rows carry a score; a submission still in the grading queue is not
    # yet an observation.
    rows = (ExamSubmission.objects
            .filter(student__isnull=False, exam_type__in=EXAM_TYPES,
                    grading_status=ExamSubmission.GRADED)
            .order_by('student_id', 'exam_type', 'submitted_at')
            .values_list('student_id', 'exam_type', 'score_pct', 'submitted_at', 'arm'))
    for student_id, exam_type, score, submitted_at, arm in rows:
        slot = by_student[student_id].get(exam_type)
        if slot is None:
            by_student[student_id][exam_type] = {
                'score': score, 'attempts': 1, 'arm': arm or None,
                'first_at': submitted_at, 'last_at': submitted_at,
            }
        else:
            slot['attempts'] += 1
            slot['last_at'] = submitted_at
    return by_student


def _first_switch_times():
    """student_id -> when they first changed tutor mode, if ever."""
    rows = (InteractionLog.objects
            .filter(user__isnull=False, event_type='ARM_SWITCH')
            .values('user_id').annotate(first=Min('timestamp')))
    return {r['user_id']: r['first'] for r in rows}


def _event_counts():
    """student_id -> {event_type: count} for the events summarised in the export, plus a
    'HELP_FALLBACK' pseudo-count of tutor turns the model did not answer (the offline
    fallback), so sessions where the manipulation was degraded can be excluded."""
    counts = defaultdict(dict)
    rows = (InteractionLog.objects
            .filter(user__isnull=False, event_type__in=COUNTED_EVENTS)
            .values('user_id', 'event_type')
            .annotate(n=Count('id')))
    for row in rows:
        counts[row['user_id']][row['event_type']] = row['n']
    fallbacks = (InteractionLog.objects
                 .filter(user__isnull=False, event_type='HELP_REQUEST', payload__ai_status='fallback')
                 .values('user_id')
                 .annotate(n=Count('id')))
    for row in fallbacks:
        counts[row['user_id']]['HELP_FALLBACK'] = row['n']
    return counts


def normalized_gain(pre, post):
    """Hake normalized gain (post - pre) / (100 - pre). Undefined at a ceiling pre-test."""
    if pre is None or post is None or pre >= 100:
        return None
    return round((post - pre) / (100.0 - pre), 4)


def participant_rows():
    """One row per enrolled student, in participant-code order. Real data only."""
    profiles = (ParticipantProfile.objects
                .filter(role='STUDENT')
                .select_related('user')
                .order_by('participant_code', 'pk'))
    submissions = _first_submissions()
    events = _event_counts()
    first_switches = _first_switch_times()
    minutes = sittings.minutes_by_paper()

    rows = []
    for profile in profiles:
        student_id = profile.user_id
        exams = submissions.get(student_id, {})
        scores = {t: (exams.get(t) or {}).get('score') for t in EXAM_TYPES}
        stamps = [e['first_at'] for e in exams.values()] + [e['last_at'] for e in exams.values()]
        counts = events.get(student_id, {})

        withdrawal_drop = None
        if scores['withdrawal'] is not None and scores['post'] is not None:
            withdrawal_drop = scores['withdrawal'] - scores['post']

        # A switch "during the protocol" is one made before the last paper was sat -
        # the kind that contaminates the primary comparison. A switch after it is the
        # revealed-preference finding the after_protocol policy is designed to collect.
        first_switch = first_switches.get(student_id)
        protocol_done_at = (exams.get('withdrawal') or {}).get('first_at')
        switched_during = bool(first_switch and (protocol_done_at is None or first_switch < protocol_done_at))

        row = {
            'participant_code': profile.participant_code or f'unassigned-{profile.pk}',
            'arm': profile.enrolled_arm or profile.assigned_arm,
            'current_arm': profile.assigned_arm,
            'arm_switches': counts.get('ARM_SWITCH', 0),
            'switched_during_protocol': switched_during,
            # A withdrawn participant stays in the export as a row of nulls so the
            # enrolment denominator is visible; everything they generated is gone.
            'withdrawn': bool(profile.withdrawn_at),
            'consent_given': profile.consent_given,
            'grade': profile.grade,
            'medium': profile.medium,
            'area_type': profile.area_type,
            'prior_experience': profile.prior_experience,
            'ai_tool_familiarity': profile.ai_tool_familiarity,
            'normalized_gain': normalized_gain(scores['pre'], scores['post']),
            'withdrawal_drop': withdrawal_drop,
            'help_requests': counts.get('HELP_REQUEST', 0),
            # How many of those turns fell back to the offline answer (model unavailable):
            # in REASONING_VISIBLE a fallback carries no reasoning, so a session with many
            # is a degraded dose of the manipulation and may need excluding.
            'help_fallbacks': counts.get('HELP_FALLBACK', 0),
            'code_runs': counts.get('CODE_RESULT', 0),
            'copy_paste': counts.get('COPY_PASTE', 0),
            'first_submission_at': min(stamps).isoformat() if stamps else None,
            'last_submission_at': max(stamps).isoformat() if stamps else None,
        }
        for exam_type in EXAM_TYPES:
            row[exam_type] = scores[exam_type]
            row[f'{exam_type}_attempts'] = (exams.get(exam_type) or {}).get('attempts', 0)
            row[f'{exam_type}_arm'] = (exams.get(exam_type) or {}).get('arm')
            row[f'{exam_type}_minutes'] = minutes.get((student_id, exam_type))
        rows.append(row)
    return rows


def _split_by_arm(rows, field, arm_field='arm'):
    """Values of `field` for each arm. `arm_field` is 'arm' (enrolled: intent-to-treat)
    or e.g. 'transfer_arm' (the mode actually used for that paper: per-protocol)."""
    treatment = [r[field] for r in rows if r[arm_field] == 'REASONING_VISIBLE' and r[field] is not None]
    control = [r[field] for r in rows if r[arm_field] == 'ANSWER_ONLY' and r[field] is not None]
    return treatment, control


def study_stats():
    """The three research outcomes, computed from whatever data exists right now."""
    rows = participant_rows()

    arm_counts = {arm: sum(1 for r in rows if r['arm'] == arm) for arm in ARMS}
    completion = {
        exam_type: sum(1 for r in rows if r[exam_type] is not None)
        for exam_type in EXAM_TYPES
    }

    # Primary: by the arm allocated at enrolment (intent-to-treat). Per-protocol: by the
    # mode the participant was actually in when they sat the paper the outcome comes
    # from. Under the after_protocol policy the two agree; where they differ, the
    # difference is the crossover, and the per-protocol figures are observational.
    outcomes, per_protocol = {}, {}
    for key, field, paper in (('learning_gain', 'normalized_gain', 'post'),
                              ('transfer_performance', 'transfer', 'transfer'),
                              ('ai_dependency_drop', 'withdrawal_drop', 'withdrawal')):
        outcomes[key] = compare_arms(*_split_by_arm(rows, field))
        per_protocol[key] = compare_arms(*_split_by_arm(rows, field, arm_field=f'{paper}_arm'))

    completed = [r for r in rows if r['withdrawal'] is not None]
    preference = {
        arm: {
            'stayed': sum(1 for r in completed if r['arm'] == arm and r['current_arm'] == arm),
            'moved': sum(1 for r in completed if r['arm'] == arm and r['current_arm'] != arm),
        }
        for arm in ARMS
    }
    switched_any = sum(1 for r in rows if r['arm_switches'])
    switched_during = sum(1 for r in rows if r['switched_during_protocol'])

    staff = ParticipantProfile.objects.filter(role__in=('EXPERT_TEACHER', 'RESEARCHER_ADMIN')).count()
    event_totals = InteractionLog.objects.aggregate(
        total=Count('id'),
        help_requests=Count('id', filter=Q(event_type='HELP_REQUEST')),
        code_runs=Count('id', filter=Q(event_type='CODE_RESULT')),
        copy_paste=Count('id', filter=Q(event_type='COPY_PASTE')),
    )

    return {
        'total_participants': len(rows),
        'withdrawn_participants': sum(1 for r in rows if r['withdrawn']),
        # Outcomes are grouped by the arm allocated at enrolment (intent-to-treat).
        'arm_basis': 'enrolled',
        'arm_switch_policy': str(getattr(settings, 'ARM_SWITCH_POLICY', 'after_protocol')),
        'switched_participants': switched_any,
        'crossover': {
            'switched_any': switched_any,
            'switched_during_protocol': switched_during,   # contaminates the primary comparison
            'switched_after_protocol': switched_any - switched_during,
        },
        # Among participants who finished all four papers: did they stay in the mode
        # they were allocated, or move once they were free to?
        'preference': preference,
        'per_protocol': per_protocol,
        'consented_participants': sum(1 for r in rows if r['consent_given']),
        'staff_accounts': staff,
        'arms': arm_counts,
        'treatment_arm_n': arm_counts['REASONING_VISIBLE'],
        'control_arm_n': arm_counts['ANSWER_ONLY'],
        'completion': completion,
        'submissions': ExamSubmission.objects.count(),
        'events': event_totals,
        'active_accounts': User.objects.filter(is_active=True).count(),
        **outcomes,
    }
