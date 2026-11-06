"""Non-destructive live verification and explicitly scoped disposable smoke records."""
from pathlib import Path
import hashlib, json, os, secrets, subprocess, sys
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-combined-20261009')
backup = root / 'deployment-backups/combined-teacher-docker-20261009T175621Z'
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
process = next(p for p in json.loads(subprocess.check_output(['pm2', 'jlist'], env=env)) if p['name'] == 'trace-tutor')
assert process['pm2_env']['status'] == 'online'
live_env = dict(x.split('=', 1) for x in Path('/proc/' + str(process['pid']) + '/environ').read_text().split('\0') if '=' in x)
os.environ['PATH'] = live_env['PATH']
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
from django.conf import settings
settings.CACHES = {n: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'release-verify-' + n} for n in ['default', 'persistent']}
import django
django.setup()
from django.contrib.auth.models import User
from django.db import connection, transaction
from psycopg2 import sql
from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission, ExpertGrade, ExpertRating
from assessment import scoring
from tutor import sandbox
from tutor.views import run_code
from logging_app.views import dashboard_summary
from trace_backend import llm
from rest_framework.test import APIRequestFactory, force_authenticate
def record_hashes():
    result = {}
    with connection.cursor() as c:
        c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        for table, in c.fetchall():
            c.execute("SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema AND tc.table_name=kcu.table_name WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema='public' AND tc.table_name=%s ORDER BY kcu.ordinal_position", [table])
            columns = [row[0] for row in c.fetchall()]
            assert columns, 'Table lacks a primary key: ' + table
            c.execute(sql.SQL('SELECT row_to_json(t)::text FROM {} t').format(sql.Identifier('public', table)))
            rows = {}
            for row, in c.fetchall():
                values = json.loads(row)
                key = hashlib.sha256(json.dumps([values[col] for col in columns], sort_keys=True).encode()).hexdigest()
                rows[key] = hashlib.sha256(row.encode()).hexdigest()
            result[table] = rows
    return result
if '--baseline' in sys.argv:
    (backup / 'data-before.json').write_text(json.dumps(record_hashes()))
    print('PASS production row fingerprints recorded without exporting personal values')
    sys.exit(0)
old = json.loads((backup / 'pm2-private.json').read_text())
assert process['pm2_env'].get('env', {}) == old['pm2_env'].get('env', {}), 'PM2 configuration changed'
for name in ['.env', 'backend/.env']:
    if (backup / 'environment' / name).exists():
        assert (root / name).read_bytes() == (backup / 'environment' / name).read_bytes()
for rel, entry in json.loads((bundle / 'release.json').read_text()).items():
    assert hashlib.sha256((root / rel).read_bytes()).hexdigest() == entry['sha256']
base = 'https://trace.musfiqurtuhin.me'
stage = backup / 'new-dist'
for route in ['/', '/login', '/dashboard', '/expert', '/workspace', '/assessment', '/profile', '/api/health/']:
    with urlopen(base + route, timeout=30) as r:
        body = r.read()
        assert r.status == 200
    if route == '/api/health/':
        assert json.loads(body)['database'] == 'ok'
    else:
        assert body == (stage / 'index.html').read_bytes()
for file in (stage / 'assets').rglob('*'):
    if file.is_file():
        with urlopen(base + '/assets/' + file.relative_to(stage / 'assets').as_posix(), timeout=30) as r:
            assert r.read() == file.read_bytes(), 'Public release asset mismatch'
print('PASS HTTPS, frontend routes and every generated asset match release', flush=True)
status = sandbox.status()
assert status['tier'] == 'docker' and status['isolated'] and status['enforced'] and status['allowed'], status
assert not (bundle / 'fixture.json').exists(), 'Disposable fixture already created; verify IDs before reuse'
password = secrets.token_urlsafe(32)
prefix = 'qa-release-20261009-'
assert not User.objects.filter(username__startswith=prefix).exists()
with transaction.atomic():
    def account(name, role, code):
        user = User.objects.create_user(username=prefix + name, password=password)
        ParticipantProfile.objects.create(user=user, role=role, participant_code=code,
            full_name='Disposable release smoke account', school_name='QA only', preferred_language='en',
            assigned_arm='REASONING_VISIBLE', consent_given=True)
        return user
    teacher = account('teacher', 'EXPERT_TEACHER', 'QA-R261009-T')
    student = account('student', 'STUDENT', 'QA-R261009-S')
    other = account('other', 'EXPERT_TEACHER', 'QA-R261009-O')
    zero = ExamSubmission.objects.create(student=student, exam_type='post', score_pct=0)
    missing = ExamSubmission.objects.create(student=student, exam_type='pre', score_pct=None)
    grade = ExpertGrade.objects.create(submission=zero, expert_user=other, assigned_marks=31, feedback_comments='Preserved QA fixture grade')
    rating = ExpertRating.objects.create(expert_user=other, item_key=scoring.all_items()[0][1]['id'], feedback='Preserved QA fixture rating')
fixture = {'password': password, 'teacher': teacher.username, 'student': student.username,
           'user_ids': [teacher.pk, student.pk, other.pk], 'missing_id': missing.pk, 'zero_id': zero.pk,
           'student_code': student.profile.participant_code, 'preserved_grade_id': grade.pk, 'preserved_rating_id': rating.pk}
(bundle / 'fixture.json').write_text(json.dumps(fixture))
(bundle / 'fixture.json').chmod(0o600)
with transaction.atomic():
    request = APIRequestFactory().get('/api/dashboard/')
    force_authenticate(request, user=student)
    response = dashboard_summary(request)
    assert response.status_code == 200 and response.data['tutor_model'] == llm.public_metadata()
    assert response.data['assessments']['pre']['best_score'] is None
    assert response.data['assessments']['post']['best_score'] == 0
    print('PASS production metadata and missing/zero scores:', json.dumps(response.data['tutor_model']), flush=True)
    transaction.set_rollback(True)
results = []
for code, expected in [('#include <stdio.h>\nint main(){printf("15\\n");return 0;}', 'SUCCESS'),
                       ('int main(){this is not C;}', 'COMPILE_ERROR')]:
    request = APIRequestFactory().post('/api/code/run/', {'language': 'c', 'code': code}, format='json')
    force_authenticate(request, user=teacher)
    response = run_code(request)
    assert response.status_code == 200
    data = response.data
    assert data['status'] == expected, data
    assert data['sandbox'] == 'docker'
    if expected == 'SUCCESS':
        assert data['test_results'][0]['actual'].strip() == '15'
    else:
        assert data['diagnostics']
    results.append({'status': data['status'], 'sandbox': data['sandbox'], 'actual': data.get('test_results', [])})
before = json.loads((backup / 'data-before.json').read_text())
after = record_hashes()
assert all(after[table].get(pk) == digest for table, rows in before.items() for pk, digest in rows.items()), 'Existing production records changed unexpectedly'
log_data = json.loads((backup / 'log-baseline.json').read_text())
log = Path(log_data['path'])
if log.exists():
    with log.open('rb') as f:
        f.seek(min(log_data['offset'], log.stat().st_size))
        new = f.read().decode(errors='replace')
    assert not any(m in new for m in ['Traceback (most recent call last)', 'ModuleNotFoundError', 'SyntaxError', 'Worker failed to boot'])
result = {'health': 'healthy', 'sandbox': status, 'limits': {'run': sandbox.limits('run'), 'compile': sandbox.limits('compile')},
          'safe_compiler_results': results, 'metadata': llm.public_metadata(), 'existing_records_unchanged': True,
          'actual_paid_generation': 'unverified; no request made'}
(backup / 'production-verification.json').write_text(json.dumps(result, indent=2))
print('PASS safe real C stdout/compile diagnostics, strict Docker caps, existing records and logs', flush=True)
