"""Item certification: content validity from expert ratings, item analysis from pilot data.

This decides whether the item bank is fit to measure anything. Two independent screens,
both from the study protocol:

  Content validity  Expert teachers rate each item on a 1-4 relevance scale. I-CVI is the
                    proportion rating it 3 or 4. Lynn (1986): certify at >= 0.78, revise
                    between 0.60 and 0.77, discard below. The bank as a whole needs
                    S-CVI/Ave >= 0.90. Modified kappa corrects I-CVI for chance
                    agreement, which matters most with few raters.

  Item analysis     From pilot responses: difficulty (proportion correct, wanted between
                    0.30 and 0.90) and point-biserial discrimination (wanted >= 0.20).
                    KR-20 reports the internal consistency of a whole form.

Every statistic returns None when the data cannot support it rather than a placeholder,
for the same reason as analytics.py: a number here is read as evidence.
"""
import math
from collections import defaultdict

from accounts.models import ParticipantProfile
from .models import ExpertRating, ExamSubmission
from . import scoring

# Thresholds (README > Research design).
DIFFICULTY_MIN = 0.30
DIFFICULTY_MAX = 0.90
DISCRIMINATION_MIN = 0.20
I_CVI_CERTIFY = 0.78
I_CVI_REVISE = 0.60
S_CVI_TARGET = 0.90
RELEVANT_FROM = 3          # 3 or 4 on the 1-4 scale counts the item as relevant
MIN_PILOT_RESPONSES = 5    # below this, item statistics are noise


# ------------------------------------------------------------------ content validity
def _modified_kappa(i_cvi, raters):
    """Kappa* = (I-CVI - Pc) / (1 - Pc), with Pc the chance agreement for `raters`.

    Polit, Beck & Owen (2007). With few raters a high I-CVI can arise by chance;
    kappa* is the number to report alongside it.
    """
    if i_cvi is None or raters <= 0:
        return None
    # Probability of chance agreement on relevance: [N! / (A!(N-A)!)] * 0.5^N, A = agreeing raters.
    agreeing = round(i_cvi * raters)
    chance = math.comb(raters, agreeing) * (0.5 ** raters)
    if chance >= 1:
        return None
    return (i_cvi - chance) / (1 - chance)


def verdict_for(i_cvi):
    if i_cvi is None:
        return 'unrated'
    if i_cvi >= I_CVI_CERTIFY:
        return 'certify'
    if i_cvi >= I_CVI_REVISE:
        return 'revise'
    return 'discard'


def content_validity():
    """Per-item I-CVI and kappa*, plus the bank-level S-CVI figures."""
    rows = ExpertRating.objects.values_list('item_key', 'expert_user_id', 'alignment_score')
    per_item = defaultdict(lambda: {'raters': 0, 'relevant': 0})
    experts = set()
    for item_key, expert_id, alignment in rows:
        per_item[item_key]['raters'] += 1
        if (alignment or 0) >= RELEVANT_FROM:
            per_item[item_key]['relevant'] += 1
        experts.add(expert_id)

    items = []
    for exam_type, item in scoring.all_items():
        counts = per_item.get(item['id'], {'raters': 0, 'relevant': 0})
        raters = counts['raters']
        i_cvi = (counts['relevant'] / raters) if raters else None
        items.append({
            'item_id': item['id'],
            'exam_type': exam_type,
            'type': item.get('type'),
            'chapter': item.get('chapter'),
            'raters': raters,
            'i_cvi': round(i_cvi, 4) if i_cvi is not None else None,
            'modified_kappa': (lambda k: round(k, 4) if k is not None else None)(
                _modified_kappa(i_cvi, raters)),
            'verdict': verdict_for(i_cvi),
        })

    rated = [i['i_cvi'] for i in items if i['i_cvi'] is not None]
    verdicts = defaultdict(int)
    for item in items:
        verdicts[item['verdict']] += 1

    return {
        'items': items,
        'summary': {
            'total_items': len(items),
            'rated_items': len(rated),
            'expert_count': len(experts),
            # S-CVI/Ave: mean I-CVI across items. S-CVI/UA: proportion of items every
            # expert judged relevant - the stricter of the two.
            's_cvi_ave': round(sum(rated) / len(rated), 4) if rated else None,
            's_cvi_ua': round(sum(1 for v in rated if v == 1.0) / len(rated), 4) if rated else None,
            's_cvi_target': S_CVI_TARGET,
            'meets_target': (sum(rated) / len(rated) >= S_CVI_TARGET) if rated else None,
            'verdicts': dict(verdicts),
        },
    }


# --------------------------------------------------------------------- item analysis
def response_matrix(exam_type):
    """(item_ids, rows) where each row maps item_id -> 1/0 for one participant.

    Uses each participant's FIRST submission of the form, matching analytics.py: a
    retake after seeing feedback is not an independent observation.
    """
    items = scoring.items_for(exam_type)
    item_ids = [i['id'] for i in items]

    students = set(ParticipantProfile.objects.filter(role='STUDENT').values_list('user_id', flat=True))
    seen, rows = set(), []
    submissions = (ExamSubmission.objects
                   .filter(exam_type=exam_type, student__isnull=False)
                   .order_by('student_id', 'submitted_at')
                   .values_list('student_id', 'answers'))
    for student_id, answers in submissions:
        if student_id in seen or student_id not in students:
            continue
        seen.add(student_id)
        results = (answers or {}).get('results') or []
        scored = {r.get('item_id'): (1 if r.get('correct') else 0)
                  for r in results if r.get('item_id')}
        if scored:
            rows.append({item_id: scored.get(item_id, 0) for item_id in item_ids})
    return item_ids, rows


def _point_biserial(item_scores, totals):
    """r_pb between one dichotomous item and the total score.

    r_pb = (M1 - M0) / SD_total * sqrt(p * q)
    """
    n = len(item_scores)
    if n < 2:
        return None
    correct = [t for s, t in zip(item_scores, totals) if s == 1]
    wrong = [t for s, t in zip(item_scores, totals) if s == 0]
    if not correct or not wrong:
        return None  # everyone passed or everyone failed: no variance to correlate
    mean_total = sum(totals) / n
    variance = sum((t - mean_total) ** 2 for t in totals) / n  # population SD, per the formula
    if variance <= 0:
        return None
    p = len(correct) / n
    return ((sum(correct) / len(correct) - sum(wrong) / len(wrong))
            / math.sqrt(variance) * math.sqrt(p * (1 - p)))


def kr20(rows, item_ids):
    """Kuder-Richardson 20: internal consistency for dichotomously scored items."""
    n = len(rows)
    k = len(item_ids)
    if n < 2 or k < 2:
        return None
    totals = [sum(row.values()) for row in rows]
    mean_total = sum(totals) / n
    total_variance = sum((t - mean_total) ** 2 for t in totals) / (n - 1)
    if total_variance <= 0:
        return None
    pq = 0.0
    for item_id in item_ids:
        p = sum(row[item_id] for row in rows) / n
        pq += p * (1 - p)
    return (k / (k - 1)) * (1 - pq / total_variance)


def item_flags(difficulty, discrimination, responses):
    """Why an item would be pulled from the bank. Empty list means it passed."""
    flags = []
    if responses < MIN_PILOT_RESPONSES:
        flags.append('insufficient-responses')
        return flags
    if difficulty is not None and difficulty < DIFFICULTY_MIN:
        flags.append('too-hard')
    if difficulty is not None and difficulty > DIFFICULTY_MAX:
        flags.append('too-easy')
    if discrimination is None:
        flags.append('no-discrimination-estimate')
    elif discrimination < DISCRIMINATION_MIN:
        flags.append('weak-discrimination')
    return flags


def item_analysis(exam_type):
    """Difficulty and discrimination for every item of one form."""
    item_ids, rows = response_matrix(exam_type)
    n = len(rows)
    totals = [sum(row.values()) for row in rows]
    bank = {i['id']: i for i in scoring.items_for(exam_type)}

    items = []
    for item_id in item_ids:
        scores = [row[item_id] for row in rows]
        difficulty = (sum(scores) / n) if n else None
        discrimination = _point_biserial(scores, totals) if n >= MIN_PILOT_RESPONSES else None
        items.append({
            'item_id': item_id,
            'type': bank.get(item_id, {}).get('type'),
            'chapter': bank.get(item_id, {}).get('chapter'),
            'responses': n,
            'difficulty': round(difficulty, 4) if difficulty is not None else None,
            'discrimination': round(discrimination, 4) if discrimination is not None else None,
            'flags': item_flags(difficulty, discrimination, n),
        })

    reliability = kr20(rows, item_ids)
    mean_total = (sum(totals) / n) if n else None
    sd_total = (math.sqrt(sum((t - mean_total) ** 2 for t in totals) / (n - 1))
                if n >= 2 else None)
    return {
        'exam_type': exam_type,
        'respondents': n,
        'item_count': len(item_ids),
        'mean_score': round(mean_total, 4) if mean_total is not None else None,
        'sd_score': round(sd_total, 4) if sd_total is not None else None,
        'kr20': round(reliability, 4) if reliability is not None else None,
        'items': items,
        'flagged_items': [i['item_id'] for i in items if i['flags']],
    }


def certification_report():
    """Everything needed to decide whether the bank is ready, in one payload."""
    forms = {t: item_analysis(t) for t in scoring.EXAM_TYPES}
    cvi = content_validity()

    # Parallel-forms check. The gain score assumes the forms are equivalent in
    # difficulty; if they are not, a difference between pre and post is partly an
    # artefact of which paper the participant happened to sit.
    comparable = [f for f in forms.values() if f['mean_score'] is not None]
    equivalence = {
        'forms_with_data': len(comparable),
        'mean_spread': (round(max(f['mean_score'] for f in comparable)
                              - min(f['mean_score'] for f in comparable), 4)
                        if len(comparable) > 1 else None),
        'per_form': {t: {'respondents': f['respondents'], 'mean': f['mean_score'],
                         'sd': f['sd_score'], 'kr20': f['kr20']}
                     for t, f in forms.items()},
    }

    return {
        'thresholds': {
            'i_cvi_certify': I_CVI_CERTIFY,
            'i_cvi_revise': I_CVI_REVISE,
            's_cvi_target': S_CVI_TARGET,
            'difficulty_range': [DIFFICULTY_MIN, DIFFICULTY_MAX],
            'discrimination_min': DISCRIMINATION_MIN,
            'min_pilot_responses': MIN_PILOT_RESPONSES,
        },
        'content_validity': cvi,
        'item_analysis': forms,
        'form_equivalence': equivalence,
        'ready': _readiness(cvi, forms),
    }


def _readiness(cvi, forms):
    """A blunt go / no-go, with the reasons spelled out."""
    blockers = []
    summary = cvi['summary']
    if not summary['rated_items']:
        blockers.append('No expert ratings have been collected.')
    elif summary['rated_items'] < summary['total_items']:
        blockers.append(f"{summary['total_items'] - summary['rated_items']} item(s) have no expert rating.")
    if summary['meets_target'] is False:
        blockers.append(f"S-CVI/Ave is {summary['s_cvi_ave']}, below the {S_CVI_TARGET} target.")
    discard = cvi['summary']['verdicts'].get('discard', 0)
    revise = cvi['summary']['verdicts'].get('revise', 0)
    if discard:
        blockers.append(f'{discard} item(s) fall below I-CVI {I_CVI_REVISE} and must be discarded.')
    if revise:
        blockers.append(f'{revise} item(s) need revision (I-CVI {I_CVI_REVISE}-{I_CVI_CERTIFY}).')

    for exam_type, form in forms.items():
        if form['respondents'] < MIN_PILOT_RESPONSES:
            blockers.append(f'{exam_type}: only {form["respondents"]} pilot response(s).')
        elif form['flagged_items']:
            blockers.append(f'{exam_type}: {len(form["flagged_items"])} item(s) flagged by item analysis.')

    return {'certified': not blockers, 'blockers': blockers}
