"""Verify existing records, remove only known disposable fixtures, recheck health."""
from pathlib import Path
import ast, hashlib, json, os, subprocess, sys
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-combined-20261009')
backup = root / 'deployment-backups/combined-teacher-docker-20261009T175621Z'
assert (backup / 'PUBLISHED').exists() and not (backup / 'ROLLED_BACK').exists()
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
from django.conf import settings
settings.CACHES = {n: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'release-cleanup-' + n} for n in ['default', 'persistent']}
import django
django.setup()
from django.contrib.auth.models import User
from django.db import connection, transaction
from psycopg2 import sql
from assessment.models import ExamSubmission, ExpertGrade, ExpertRating
from accounts.models import ParticipantProfile
from rest_framework.authtoken.models import Token
from logging_app.models import InteractionLog
source = ast.parse((bundle / 'verify.py').read_text())
function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'record_hashes')
exec(compile(ast.Module(body=[function], type_ignores=[]), 'reviewed-record-fingerprints', 'exec'))
before = json.loads((backup / 'data-before.json').read_text())
def integrity():
    after = record_hashes()
    assert all(after[table].get(pk) == digest for table, rows in before.items() for pk, digest in rows.items()), 'Existing record modified or removed'
    return {table: len(rows) for table, rows in after.items()}
integrity()
fixture = json.loads((bundle / 'fixture.json').read_text())
ids = fixture['user_ids']
users = list(User.objects.filter(pk__in=ids).order_by('pk'))
assert len(users) == 3 and all(u.username.startswith('qa-release-20261009-') for u in users)
teacher = User.objects.get(username=fixture['teacher'], pk__in=ids)
student = User.objects.get(username=fixture['student'], pk__in=ids)
assert student.profile.participant_code == fixture['student_code']
assert set(ExamSubmission.objects.filter(student_id__in=ids).values_list('pk', flat=True)) == {fixture['missing_id'], fixture['zero_id']}
assert not ExpertGrade.objects.filter(submission_id__in=[fixture['missing_id'], fixture['zero_id']]).exclude(expert_user_id__in=ids).exists(), 'Real reviewer touched fixture; preserve and request decision'
grade = ExpertGrade.objects.get(pk=fixture['preserved_grade_id'])
assert grade.assigned_marks == 31 and grade.feedback_comments == 'Preserved QA fixture grade'
rating = ExpertRating.objects.get(pk=fixture['preserved_rating_id'])
assert rating.alignment_score == 4 and rating.feedback == 'Preserved QA fixture rating'
assert ExpertGrade.objects.get(expert_user=teacher, submission_id=fixture['missing_id']).assigned_marks == 88
assert ExpertRating.objects.filter(expert_user=teacher).count() == 1
assert ExamSubmission.objects.get(pk=fixture['missing_id']).score_pct is None
assert ExamSubmission.objects.get(pk=fixture['zero_id']).score_pct == 0
with transaction.atomic():
    deleted, per_model = User.objects.filter(pk__in=ids, username__startswith='qa-release-20261009-').delete()
    assert not User.objects.filter(pk__in=ids).exists()
    assert not ParticipantProfile.objects.filter(user_id__in=ids).exists()
    assert not ExamSubmission.objects.filter(student_id__in=ids).exists()
    assert not ExpertGrade.objects.filter(expert_user_id__in=ids).exists()
    assert not ExpertRating.objects.filter(expert_user_id__in=ids).exists()
    assert not InteractionLog.objects.filter(user_id__in=ids).exists()
    assert not Token.objects.filter(user_id__in=ids).exists()
    counts = integrity()
print('PASS removed only designated disposable accounts and their dependent QA records', flush=True)
assert all(counts[table] >= len(rows) for table, rows in before.items())
new_counts = {table: counts[table] - len(rows) for table, rows in before.items() if counts[table] != len(rows)}
assert not new_counts, 'Unattributed new production records require review: ' + str(new_counts)
manifest = json.loads((backup / 'backup-manifest.json').read_text())
for rel, digest in manifest['files'].items():
    assert hashlib.sha256((backup / rel).read_bytes()).hexdigest() == digest
for name in ['.env', 'backend/.env']:
    saved = backup / 'environment' / name
    if saved.exists():
        assert saved.read_bytes() == (root / name).read_bytes()
for rel, entry in json.loads((bundle / 'release.json').read_text()).items():
    assert hashlib.sha256((root / rel).read_bytes()).hexdigest() == entry['sha256']
with connection.cursor() as c:
    c.execute('SELECT rolcreatedb, rolsuper FROM pg_roles WHERE rolname=current_user')
    assert c.fetchone() == (False, False)
connection.close()
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
process = next(p for p in json.loads(subprocess.check_output(['pm2', 'jlist'], env=env)) if p['name'] == 'trace-tutor')
assert process['pm2_env']['status'] == 'online'
assert process['pm2_env'].get('env', {}) == json.loads((backup / 'pm2-private.json').read_text())['pm2_env'].get('env', {})
log_data = json.loads((backup / 'log-baseline.json').read_text())
log = Path(log_data['path'])
if log.exists():
    with log.open('rb') as f:
        f.seek(min(log_data['offset'], log.stat().st_size))
        new = f.read().decode(errors='replace')
    assert not any(m in new for m in ['Traceback (most recent call last)', 'ModuleNotFoundError', 'SyntaxError', 'Worker failed to boot'])
with urlopen('https://trace.musfiqurtuhin.me/api/health/', timeout=20) as r:
    assert json.loads(r.read())['database'] == 'ok'
assert subprocess.run(['systemctl', 'is-active', 'nginx'], capture_output=True).returncode == 0
assert not list(Path('/tmp').glob('trace-release-pg-*')) and not list(Path('/tmp').glob('trace-combined-restore-*'))
result = {'healthy': True, 'original_records_unchanged': True, 'table_counts': counts, 'qa_cleanup': per_model,
          'backup_verified': str(backup), 'environment_unchanged': True, 'database_permissions_unchanged': True,
          'source_hashes_match': True, 'private_clusters_removed': True, 'critical_log_errors': False}
(backup / 'final-audit.json').write_text(json.dumps(result, indent=2))
(backup / 'RELEASE_COMPLETE').write_text('All safe live checks passed; original database rows and counts preserved; no paid AI request')
(bundle / 'fixture.json').unlink()
print(json.dumps(result, indent=2), flush=True)
print('PASS complete combined release: rollback available; no database restore/reset; no paid generation', flush=True)
