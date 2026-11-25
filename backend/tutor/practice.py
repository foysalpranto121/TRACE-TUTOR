"""Versioned practice checks and the meaning of a recorded practice success.

Practice completion is evidence of passing these checks, not independent authorship.
Only the code endpoint writes version 2 results; browser telemetry cannot assert them.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

METRIC_VERSION = 2
RESULT_SOURCE = 'server_runner'
CATALOG_PATH = Path(__file__).with_name('practice_tasks.json')
TASKS = json.loads(CATALOG_PATH.read_bytes())
# Formatting-only edits must not invalidate already earned completion credit.
CATALOG_SHA256 = hashlib.sha256(json.dumps(TASKS, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def is_verified_result(problem_id, payload):
    return (problem_id in TASKS
            and payload.get('source') == RESULT_SOURCE
            and payload.get('practice_metric_version') == METRIC_VERSION
            and payload.get('catalog_sha256') == CATALOG_SHA256)


def successful_tasks_by_user(user_id=None):
    """Distinct successful tasks over the full history, separated by provenance.

    Earlier CODE_RESULT events retain their original meaning; they are never
    retrospectively promoted to server-checked practice completions.
    """
    from logging_app.models import InteractionLog

    results = defaultdict(lambda: {'verified': set(), 'legacy': set()})
    logs = InteractionLog.objects.filter(event_type='CODE_RESULT', payload__status='SUCCESS', user__isnull=False)
    if user_id is not None:
        logs = logs.filter(user_id=user_id)
    for uid, pid, payload in logs.values_list('user_id', 'problem_id', 'payload').iterator():
        pid = pid or payload.get('problem_id')
        if not pid:
            continue
        kind = 'verified' if is_verified_result(pid, payload) else 'legacy'
        results[uid][kind].add(pid)
    return results
