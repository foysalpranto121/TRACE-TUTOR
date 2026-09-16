"""Server-side grading for the JSON item bank - the single source of truth for exam scores.

Nothing here may leak keyed_answer / test_cases / html_checks to a client: public_item() is the only
shape that goes out over the wire.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.cache import caches
from django.db import close_old_connections

ITEM_BANK_PATH = Path(__file__).resolve().parent / 'item_bank.json'
EXAM_TYPES = ('pre', 'post', 'transfer', 'withdrawal')
CODE_TYPES = {'c_programming': 'c', 'html_coding': 'html'}
GRADE_WORKERS = 3          # a form holds 8 code items; each C compile is expensive, so stay small
MAX_COMPILE_OUTPUT = 2000


class ItemBankError(RuntimeError):
    """The item bank is missing, unreadable or not shaped like a bank."""


class GradingUnavailable(RuntimeError):
    """A code item could not be graded because the runner was unavailable, not because
    the answer was wrong. Raised so the submission is recorded FAILED (and retried when
    the toolchain is back) instead of banking a real-looking zero."""


# Statuses that mean "the runner could not judge this answer", as opposed to a genuine
# wrong answer (COMPILE_ERROR, RUNTIME_ERROR, WRONG_ANSWER, NO_ANSWER). A submission
# with any of these is a grading failure, not a low score.
INFRASTRUCTURE_STATUSES = {'SANDBOX_UNAVAILABLE', 'UNSUPPORTED', 'UNKNOWN', 'GRADING_ERROR'}


def load_item_bank():
    """Item bank JSON, held in the memory cache and keyed by the file's mtime so edits show up
    without a restart."""
    try:
        mtime = ITEM_BANK_PATH.stat().st_mtime_ns
    except OSError as exc:
        raise ItemBankError(f'Item bank not readable at {ITEM_BANK_PATH}: {exc}') from exc

    key = f'item-bank:{mtime}'
    bank = caches['default'].get(key)
    if bank is None:
        try:
            with open(ITEM_BANK_PATH, encoding='utf-8') as fh:
                bank = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ItemBankError(f'Item bank at {ITEM_BANK_PATH} could not be parsed: {exc}') from exc
        if not isinstance(bank, dict) or not any(isinstance(bank.get(t), list) for t in EXAM_TYPES):
            raise ItemBankError(f'Item bank at {ITEM_BANK_PATH} has no {"/".join(EXAM_TYPES)} lists.')
        caches['default'].set(key, bank, 3600)
    return bank


def items_for(exam_type):
    """Every item of one form, with grading secrets still attached (server side only)."""
    bank = load_item_bank()
    items = bank.get(str(exam_type or '').lower())
    if not isinstance(items, list):
        items = bank.get('pre') or []
    return [i for i in items if isinstance(i, dict) and i.get('id')]


def all_items():
    """(exam_type, item) for the whole bank, in form order."""
    bank = load_item_bank()
    out = []
    for exam_type in EXAM_TYPES:
        for item in bank.get(exam_type) or []:
            if isinstance(item, dict) and item.get('id'):
                out.append((exam_type, item))
    return out


def find_item(item_id):
    for exam_type, item in all_items():
        if item['id'] == item_id:
            return exam_type, item
    return None, None


def public_item(item):
    """The student-facing shape: no keyed_answer, no test_cases, no html_checks."""
    out = {k: item.get(k) for k in ('id', 'type', 'chapter', 'title', 'question', 'curriculum_ref')}
    item_type = item.get('type')
    if item_type == 'concept_mcq':
        out['options'] = item.get('options') or []
    if item.get('code_snippet'):
        out['code_snippet'] = item['code_snippet']
    if item_type == 'c_programming':
        out['input_format'] = item.get('input_format') or ''
        out['output_format'] = item.get('output_format') or ''
        out['sample_cases'] = item.get('sample_cases') or []
    return out


def _grade_mcq(item, answers):
    chosen = answers.get(item['id'])
    chosen = '' if chosen is None else str(chosen).strip()
    if not chosen:
        return {'correct': False, 'detail': 'কোনো অপশন নির্বাচন করা হয়নি (No option selected)'}
    correct = chosen.lower() == str(item.get('keyed_answer', '')).strip().lower()
    verdict = 'সঠিক (Correct)' if correct else 'ভুল (Incorrect)'
    return {'correct': correct, 'detail': f'নির্বাচিত (Selected): {chosen} — {verdict}'}


def _code_detail(status, passed, total):
    if status == 'SUCCESS':
        return f'সব টেস্ট পাস (All {total} checks passed)'
    if status == 'COMPILE_ERROR':
        return 'কম্পাইল করা যায়নি (Compile error)'
    if status == 'RUNTIME_ERROR':
        return f'রানটাইম ত্রুটি (Runtime error) — {passed}/{total} passed'
    if status == 'WRONG_ANSWER':
        return f'{passed}/{total} টেস্ট পাস (Passed {passed} of {total} checks)'
    return f'গ্রেড করা যায়নি (Not graded): {status}'


def _grade_code(item, code_answers):
    checks = item.get('test_cases') if item['type'] == 'c_programming' else item.get('html_checks')
    checks = checks or []
    source = code_answers.get(item['id'])
    source = '' if source is None else str(source)
    if not source.strip():
        return {'correct': False, 'detail': 'কোনো কোড জমা দেওয়া হয়নি (No code submitted)',
                'status': 'NO_ANSWER', 'passed_count': 0, 'total_tests': len(checks)}

    from tutor.runner import run_code
    result = run_code(language=CODE_TYPES[item['type']], code=source, test_cases=checks, mode='run')
    status = result.get('status') or 'UNKNOWN'
    tests = result.get('test_results') or []
    passed = result.get('passed_count')
    if passed is None:
        passed = sum(1 for t in tests if t.get('passed'))
    total = len(tests) or len(checks)
    graded = {'correct': status == 'SUCCESS', 'detail': _code_detail(status, passed, total),
              'status': status, 'passed_count': passed, 'total_tests': total}
    compile_output = (result.get('compile_output') or '').strip()
    if compile_output:
        graded['compile_output'] = compile_output[:MAX_COMPILE_OUTPUT]
    return graded


def _grade_one(item, answers, code_answers):
    """One item can never break the whole submission."""
    try:
        if item.get('type') in CODE_TYPES:
            return _grade_code(item, code_answers)
        return _grade_mcq(item, answers)
    except Exception as exc:  # a broken item or a dead compiler must not 500 the submission
        return {'correct': False, 'detail': f'গ্রেড করা যায়নি (Could not grade): {exc}',
                'status': 'GRADING_ERROR'}
    finally:
        close_old_connections()


def grade_submission(exam_type, answers, code_answers):
    """Grade a whole form -> (score_pct, correct, total, results). Blank answers count as wrong."""
    answers = answers if isinstance(answers, dict) else {}
    code_answers = code_answers if isinstance(code_answers, dict) else {}
    items = items_for(exam_type)

    graded = [None] * len(items)
    code_slots = [(idx, item) for idx, item in enumerate(items) if item.get('type') in CODE_TYPES]
    for idx, item in enumerate(items):
        if item.get('type') not in CODE_TYPES:
            graded[idx] = _grade_one(item, answers, code_answers)

    if code_slots:
        with ThreadPoolExecutor(max_workers=min(GRADE_WORKERS, len(code_slots))) as pool:
            for (idx, _item), outcome in zip(
                code_slots, pool.map(lambda s: _grade_one(s[1], answers, code_answers), code_slots)
            ):
                graded[idx] = outcome

    results = []
    for item, outcome in zip(items, graded):
        entry = {'item_id': item['id'], 'type': item.get('type'), 'title': item.get('title'),
                 'correct': bool(outcome['correct']), 'detail': outcome['detail']}
        for key in ('passed_count', 'total_tests', 'compile_output', 'status'):
            if key in outcome:
                entry[key] = outcome[key]
        results.append(entry)

    stuck = sorted({r['status'] for r in results
                    if r.get('status') in INFRASTRUCTURE_STATUSES})
    if stuck:
        # Do not bank a score built on items the runner could not judge: every code item
        # marked wrong because Docker was down would look like a real, low score. Fail the
        # whole submission so grading.grade records it FAILED and retry_failed re-grades it.
        raise GradingUnavailable(
            f'{len(stuck)} runner status(es) prevented grading: {", ".join(stuck)}. '
            'The answers are saved; grade again once the code runner is available.')

    total = len(results)
    correct = sum(1 for r in results if r['correct'])
    score_pct = round(correct * 100 / total) if total else 0
    return score_pct, correct, total, results
