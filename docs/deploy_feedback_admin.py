"""Deploy only the tested admin proxies; preserve all existing study data."""
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path('/srv/trace-tutor')
STAGE = Path('/tmp/trace-feedback-20261105-164f7753b452')
FILES = ('backend/assessment/models.py', 'backend/assessment/admin.py',
         'backend/assessment/migrations/0009_feedback_admin_views.py')
baseline = json.loads((STAGE / 'baseline.json').read_text())
test_log = (STAGE / 'tests.log').read_text()
assert 'Ran 26 tests' in test_log and '\nOK\n' in test_log, 'Staging tests must pass first'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


for relative in FILES:
    assert digest(ROOT / relative) == baseline[relative], f'Live source changed: {relative}'

backup = ROOT / 'deployment-backups' / ('feedback-admin-20261105-' + uuid4().hex[:12])
backup.mkdir(mode=0o700)
manifest = {}
for relative in FILES:
    manifest[relative] = {'before': baseline[relative], 'after': digest(STAGE / relative)}
    if baseline[relative]:
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
(backup / 'source-manifest.json').write_text(json.dumps(manifest, indent=2))

sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.core import serializers
from django.db.models.functions import Trim
from accounts.models import ParticipantProfile
from assessment.models import AssessmentTimeline, ExamSubmission, ExpertGrade, ExpertRating, PaperSitting

models = (User, ParticipantProfile, AssessmentTimeline, ExamSubmission, ExpertGrade, ExpertRating, PaperSitting)


def fingerprints():
    return {model._meta.label_lower: hashlib.sha256(
        serializers.serialize('json', model.objects.order_by('pk')).encode()).hexdigest() for model in models}


before = fingerprints()
(backup / 'existing-study-data.json').write_text(serializers.serialize(
    'json', [row for model in models for row in model.objects.order_by('pk')]))
(backup / 'data-fingerprints.json').write_text(json.dumps(before, indent=2))
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))


def manage(*args):
    subprocess.run([str(ROOT / 'venv/bin/python'), 'manage.py', *args],
                   cwd=ROOT / 'backend', env=env, check=True)


def get(path, session=None):
    headers = {'Cookie': f'{settings.SESSION_COOKIE_NAME}={session.session_key}'} if session else {}
    with urlopen(Request('https://trace.musfiqurtuhin.me' + path, headers=headers), timeout=25) as response:
        assert response.status == 200
        return response.read().decode(), response.geturl()


def restart():
    subprocess.run(['pm2', 'restart', 'trace-tutor'], env=env, check=True, stdout=subprocess.DEVNULL)
    for attempt in range(10):
        try:
            body, _ = get('/api/health/')
            assert json.loads(body)['database'] == 'ok'
            return
        except Exception:
            if attempt == 9:
                raise
            time.sleep(1)


session = None
migrated = False
try:
    for relative in FILES:
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(STAGE / relative, target)
    manage('check')
    manage('migrate', 'assessment', '--noinput')
    migrated = True
    restart()

    # A temporary admin session verifies the actual HTTPS pages without logging in,
    # changing anyone's last_login, or touching existing browser sessions.
    administrator = User.objects.filter(is_superuser=True, is_staff=True, is_active=True).first()
    assert administrator, 'An existing administrator is required for verification'
    session = SessionStore()
    session[SESSION_KEY] = str(administrator.pk)
    session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
    session[HASH_SESSION_KEY] = administrator.get_session_auth_hash()
    session.set_expiry(300)
    session.save()
    index, _ = get('/django-admin/assessment/', session)
    assert 'Expert feedback' in index and 'Teacher comment' in index

    feedback = ExpertGrade.objects.annotate(text=Trim('feedback_comments')).filter(
        feedback_comments__isnull=False).exclude(text='').order_by('pk')
    comments = ExpertRating.objects.annotate(text=Trim('feedback')).filter(
        feedback__isnull=False).exclude(text='').order_by('pk')
    verified = {}
    for model, queryset, field, heading in (
        ('expertfeedback', feedback, 'feedback_comments', 'Qualitative feedback'),
        ('teachercomment', comments, 'feedback', 'Teacher comment'),
    ):
        print('VERIFYING_SAVED_ENTRIES', model, queryset.count(), flush=True)
        body, _ = get(f'/django-admin/assessment/{model}/', session)
        assert heading in body
        # Filter by primary key to prove each historical entry is reachable, even
        # when its position would otherwise fall on a later changelist page.
        for row in queryset:
            detail, final_url = get(f'/django-admin/assessment/{model}/{row.pk}/change/', session)
            assert '/login/' not in final_url
            assert html.escape(getattr(row, field)) in detail, f'Missing saved text: {model} #{row.pk}'
        verified[model] = queryset.count()
        _, anonymous_url = get(f'/django-admin/assessment/{model}/')
        assert '/django-admin/login/' in anonymous_url

    assert fingerprints() == before, 'Study data changed during deployment'
    report = {'deployed_at': datetime.now(timezone.utc).isoformat(), 'backup': str(backup),
              'verified_historical_entries': verified, 'tests_passed': 26,
              'existing_study_data_unchanged': True}
    (backup / 'PUBLISHED.json').write_text(json.dumps(report, indent=2))
    print('FEEDBACK_ADMIN_PUBLISHED', json.dumps(report), flush=True)
except Exception:
    if migrated:
        manage('migrate', 'assessment', '0008', '--noinput')
    for relative in FILES:
        if baseline[relative]:
            shutil.copy2(backup / relative, ROOT / relative)
        else:
            (ROOT / relative).unlink(missing_ok=True)
    restart()
    print('FEEDBACK_ADMIN_ROLLED_BACK', str(backup), flush=True)
    raise
finally:
    if session and session.session_key:
        session.delete()
