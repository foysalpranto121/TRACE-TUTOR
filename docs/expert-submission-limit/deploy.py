"""Publish only the tested submission-query fix, with backup and rollback."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path('/srv/trace-tutor')
BUNDLE = Path(__file__).resolve().parent
ORIGIN = 'https://trace.musfiqurtuhin.me'
source = ROOT / 'backend/assessment/views.py'
manifest = json.loads((BUNDLE / 'tested-manifest.json').read_text())
original = source.read_bytes()
candidate = (BUNDLE / 'views.py.candidate').read_bytes()
assert hashlib.sha256(original).hexdigest() == manifest['original_sha256'], 'Source changed since tests'
assert hashlib.sha256(candidate).hexdigest() == manifest['candidate_sha256']

sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from django.db import connection
from accounts.models import STAFF_ROLES
from assessment.models import ExamSubmission, ExpertGrade, ExpertRating
from rest_framework.authtoken.models import Token

with connection.cursor() as cursor:
    cursor.execute('SET default_transaction_read_only = on')
token = Token.objects.filter(user__profile__role__in=STAFF_ROLES).first()
assert token is not None, 'An existing staff token is required for authenticated HTTP verification'

def get(path, authenticated=False):
    headers = {'Authorization': 'Token ' + token.key} if authenticated else {}
    with urlopen(Request(ORIGIN + path, headers=headers), timeout=15) as response:
        return json.loads(response.read())

def fingerprints():
    result = {}
    for model in (ExamSubmission, ExpertGrade, ExpertRating):
        rows = list(model.objects.order_by('pk').values())
        result[model.__name__] = {'count': len(rows), 'sha256': hashlib.sha256(
            json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()}
    return result

before = fingerprints()
expected_ids = list(ExamSubmission.objects.order_by('-submitted_at', '-pk').values_list('pk', flat=True))
baseline = get('/api/expert/submissions/', True)
assert get('/api/health/')['database'] == 'ok'
backup = ROOT / 'deployment-backups' / ('expert-queue-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
shutil.copy2(source, backup / 'views.py')
(backup / 'before.json').write_text(json.dumps({'tests': manifest, 'tables': before,
                                               'http_count': baseline['count']}, indent=2))

def restart():
    subprocess.run(['pm2', 'restart', 'trace-tutor'], check=True, stdout=subprocess.DEVNULL)
    for attempt in range(8):
        try:
            assert get('/api/health/')['database'] == 'ok'
            return
        except Exception:
            if attempt == 7:
                raise
            time.sleep(1)

def replace(data):
    temporary = source.with_name('views.py.queue-next')
    temporary.write_bytes(data)
    shutil.copymode(source, temporary)
    temporary.replace(source)

try:
    assert source.read_bytes() == original, 'Source drift immediately before publication'
    replace(candidate)
    subprocess.run([str(ROOT / 'venv/bin/python'), 'manage.py', 'check'],
                   cwd=ROOT / 'backend', check=True)
    restart()
    live = get('/api/expert/submissions/', True)
    assert live['count'] == len(expected_ids)
    assert [row['id'] for row in live['submissions']] == expected_ids
    codes = sorted({row['participant_code'] for row in live['submissions'] if row['participant_code']})
    assert source.read_bytes() == candidate
    after = fingerprints()
    report = {'status': 'DEPLOYED', 'backup': str(backup), 'before_count': baseline['count'],
              'after_count': live['count'], 'participants': len(codes),
              'first_participant': codes[0] if codes else None,
              'last_participant': codes[-1] if codes else None,
              'participants_below_SIM_035': sum(code.startswith('SIM-') and code < 'SIM-035' for code in codes),
              'research_rows_unchanged': before == after,
              'health': get('/api/health/'), 'candidate_sha256': manifest['candidate_sha256']}
    (backup / 'deployed.json').write_text(json.dumps(report, indent=2))
    (BUNDLE / 'deployed.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
except Exception:
    assert source.read_bytes() in (original, candidate), 'Refusing to overwrite unexpected concurrent source change'
    replace(original)
    restart()
    print('Rolled back the application file; no study database writes were performed.', flush=True)
    raise
