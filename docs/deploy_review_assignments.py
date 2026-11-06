"""Publish tested work queues and allocate the authorized ten-teacher roster."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path('/srv/trace-tutor')
STAGE = Path('/tmp/trace-assignments-20261106-6353185188ac')
manifest = json.loads((STAGE / 'release.json').read_text())
assert 'Ran 56 tests' in (STAGE / 'tests.log').read_text()
assert (STAGE / 'tests.log').read_text().rstrip().endswith('OK')
assert 'built in' in (STAGE / 'frontend-build.log').read_text()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


for relative, expected in manifest.items():
    assert digest(ROOT / relative) == expected['before'], f'Live file changed: {relative}'
    assert digest(STAGE / relative) == expected['after'], f'Candidate changed: {relative}'

backup = ROOT / 'deployment-backups' / ('review-assignments-20261106-' + uuid4().hex[:12])
backup.mkdir(mode=0o700)
for relative, hashes in manifest.items():
    if hashes['before']:
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
shutil.copy2(ROOT / 'frontend/dist/index.html', backup / 'index.html')
(backup / 'source-manifest.json').write_text(json.dumps(manifest, indent=2))

sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from django.contrib.auth.models import User
from django.core import serializers
from django.db import connection
from django.db.models import Q
from rest_framework.authtoken.models import Token
from assessment.models import ExamSubmission, ExpertGrade, ExpertRating

emails = (
    'aiyesha.cse@gmail.com', 'asique.iqbaldrmc@gmail.com', 'motaleb.fgc@gmail.com',
    'alamgirlm94@gmail.com', 'mdraihaniu@gmail.com', 'rokib.armc@gmail.com',
    'mamun.armc@gmail.com', 'shamim007.akanda@gmail.com', 'anisurict1@gmail.com',
    'kadirmd159@gmail.com',
)
condition = Q(pk__in=[])
for email in emails:
    condition |= Q(email__iexact=email)
teachers = list(User.objects.filter(condition).select_related('profile').order_by('pk'))
assert len(teachers) == 10
teacher_ids = [teacher.pk for teacher in teachers]
codes = [f'SIM-{number:03d}' for number in range(1, 61)]
cohort = ExamSubmission.objects.filter(student__profile__participant_code__in=codes).order_by('pk')
cohort_ids = set(cohort.values_list('pk', flat=True))
assert len(cohort_ids) == 237, 'Review changed cohort size before proceeding'
grades = ExpertGrade.objects.filter(expert_user_id__in=teacher_ids).order_by('pk')
ratings = ExpertRating.objects.filter(expert_user_id__in=teacher_ids).order_by('pk')
prior_grades, prior_ratings = list(grades), list(ratings)
review_rows = [*cohort, *prior_grades, *prior_ratings]
(backup / 'existing-target-review-data.json').write_text(serializers.serialize('json', review_rows))


def fingerprints():
    return {name: hashlib.sha256(serializers.serialize('json', rows).encode()).hexdigest()
            for name, rows in (('cohort_submissions', cohort), ('teacher_grades', grades), ('item_ratings', ratings))}


before = fingerprints()
(backup / 'data-fingerprints.json').write_text(json.dumps(before))
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))


def manage(*args):
    result = subprocess.run([str(ROOT / 'venv/bin/python'), 'manage.py', *args],
                            cwd=ROOT / 'backend', env=env, check=True,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.stdout


def get(path, token=None):
    headers = {'Authorization': 'Token ' + token.key} if token else {}
    with urlopen(Request('https://trace.musfiqurtuhin.me' + path, headers=headers), timeout=30) as response:
        assert response.status == 200, path
        return response.read(), response.headers.get('Content-Type', '')


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


new_tokens = []
migrated = False
try:
    for relative in manifest:
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(STAGE / relative, target)
    print(manage('check'), flush=True)
    print(manage('migrate', 'assessment', '--noinput'), flush=True)
    migrated = True
    preview = json.loads(manage('allocate_teacher_reviews'))
    assert preview['status'] == 'dry_run'
    assert preview['submission_count'] == 237 and preview['item_count'] == 60
    assert all(row['items_assigned'] == 6 for row in preview['teachers'])
    assert sorted(row['submissions_assigned'] for row in preview['teachers']) == [23] * 3 + [24] * 7
    (backup / 'allocation-preview.json').write_text(json.dumps(preview, ensure_ascii=False, indent=2))
    allocation = json.loads(manage('allocate_teacher_reviews', '--apply'))
    assert allocation['status'] == 'applied'

    # Publish all hashed assets before switching the index and restarting WhiteNoise.
    for source in (STAGE / 'frontend/dist').rglob('*'):
        if source.is_file() and source.name != 'index.html':
            target = ROOT / 'frontend/dist' / source.relative_to(STAGE / 'frontend/dist')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    temporary = ROOT / 'frontend/dist/index.html.assignment-new'
    shutil.copy2(STAGE / 'frontend/dist/index.html', temporary)
    temporary.replace(ROOT / 'frontend/dist/index.html')
    restart()

    with connection.cursor() as cursor:
        cursor.execute('SELECT item_key, expert_user_id FROM assessment_itemreviewassignment')
        item_owners = dict(cursor.fetchall())
        cursor.execute('SELECT submission_id, expert_user_id FROM assessment_submissionreviewassignment')
        submission_owners = dict(cursor.fetchall())
    assert len(item_owners) == 60 and set(submission_owners) == cohort_ids
    for grade in prior_grades:
        if grade.submission_id in cohort_ids and grade.is_graded:
            assert submission_owners[grade.submission_id] == grade.expert_user_id

    verified = []
    for teacher in teachers:
        token, created = Token.objects.get_or_create(user=teacher)
        if created:
            new_tokens.append(token)
        body, _ = get('/api/expert/reviews/', token)
        items = json.loads(body)['items_to_review']
        body, _ = get('/api/expert/submissions/', token)
        submissions = json.loads(body)['submissions']
        item_map = {row['id']: row for row in items}
        sub_map = {row['id']: row for row in submissions}
        assigned_items = {row['id'] for row in items if row['is_assigned']}
        assigned_subs = {row['id'] for row in submissions if row['is_assigned']}
        assert assigned_items == {key for key, owner in item_owners.items() if owner == teacher.pk}
        assert assigned_subs == {key for key, owner in submission_owners.items() if owner == teacher.pk}
        own_grades = {row.submission_id: row for row in prior_grades if row.expert_user_id == teacher.pk}
        for submission in submissions:
            own = own_grades.get(submission['id'])
            assert submission['my_grade_completed'] == bool(own and own.is_graded)
            if own:
                assert submission['assigned_marks'] == own.assigned_marks
                assert submission['feedback'] == (own.feedback_comments or '')
                assert submission['graded_by'] == teacher.username
            else:
                assert submission['assigned_marks'] is None and submission['feedback'] == ''
        for rating in prior_ratings:
            if rating.expert_user_id == teacher.pk and rating.item_key in item_map:
                assert item_map[rating.item_key]['my_rating']['feedback'] == (rating.feedback or '')
        verified.append({'teacher': teacher.username, 'items': len(assigned_items),
                         'submissions': len(assigned_subs),
                         'previous_own_grades_visible': sum(row['my_grade_completed'] for row in submissions)})
        print('TEACHER_QUEUE_VERIFIED', json.dumps(verified[-1]), flush=True)

    def verify_asset(source):
        path = '/' + source.relative_to(STAGE / 'frontend/dist').as_posix()
        body, content_type = get(path)
        assert not body.lstrip().lower().startswith(b'<!doctype'), path
        assert ('javascript' in content_type if source.suffix == '.js' else 'text/css' in content_type), path
        return path

    assets = [source for source in (STAGE / 'frontend/dist').rglob('*')
              if source.is_file() and source.suffix in {'.js', '.css'}]
    with ThreadPoolExecutor(max_workers=4) as pool:
        checked_assets = list(pool.map(verify_asset, assets))
    expected_entry = re.search(r'/assets/index-[^" ]+\.js', (STAGE / 'frontend/dist/index.html').read_text()).group()
    body, _ = get('/?review-assignments=20261106')
    assert expected_entry in body.decode()
    # Re-evaluate querysets to compare the actual current saved reviews.
    cohort._result_cache = grades._result_cache = ratings._result_cache = None
    assert fingerprints() == before, 'Existing submissions, grades or ratings changed during deployment'
    report = {'deployed_at': datetime.now(timezone.utc).isoformat(), 'backup': str(backup),
              'allocation': allocation, 'verified_queues': verified,
              'checked_assets': len(checked_assets), 'existing_reviews_unchanged': True,
              'backend_tests': 56, 'frontend_tests': 119, 'utility_tests': 6}
    (backup / 'PUBLISHED.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('REVIEW_ASSIGNMENTS_PUBLISHED', json.dumps(report, ensure_ascii=False), flush=True)
except Exception:
    if migrated:
        print(manage('migrate', 'assessment', '0009', '--noinput'), flush=True)
    for relative, hashes in manifest.items():
        if hashes['before']:
            shutil.copy2(backup / relative, ROOT / relative)
        else:
            (ROOT / relative).unlink(missing_ok=True)
    shutil.copy2(backup / 'index.html', ROOT / 'frontend/dist/index.html')
    restart()
    print('REVIEW_ASSIGNMENTS_ROLLED_BACK', str(backup), flush=True)
    raise
finally:
    for token in new_tokens:
        token.delete()
