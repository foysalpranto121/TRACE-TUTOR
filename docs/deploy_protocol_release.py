"""Publish tested timing feature, with source/index rollback and data fingerprints."""
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from uuid import uuid4

ROOT = Path('/srv/trace-tutor')
STAGE = Path('/tmp/trace-protocol-20261025-ef85a79ae54c')
manifest = json.loads((STAGE / 'release.json').read_text())
backup = ROOT / 'deployment-backups' / ('protocol-20261025-' + uuid4().hex[:12])
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH',''))
for relative, hashes in manifest.items():
    target = ROOT / relative
    assert (hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None) == hashes['before']
    assert hashlib.sha256((STAGE/relative).read_bytes()).hexdigest() == hashes['after']
backup.mkdir(mode=0o700)
for relative, hashes in manifest.items():
    if hashes['before']:
        destination=backup/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,destination)
shutil.copy2(ROOT/'frontend/dist/index.html',backup/'index.html')
sys.path.insert(0,str(ROOT/'backend'))
os.environ['DJANGO_SETTINGS_MODULE']='trace_backend.settings'
import django
django.setup()
from django.core import serializers
from django.contrib.auth.models import User
from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission,ExpertGrade,ExpertRating,PaperSitting
from logging_app.models import InteractionLog
from rest_framework.authtoken.models import Token
models=(User,ParticipantProfile,ExamSubmission,ExpertGrade,ExpertRating,PaperSitting,InteractionLog)
def fingerprints():
    return {m._meta.label_lower:hashlib.sha256(serializers.serialize('json',m.objects.order_by('pk')).encode()).hexdigest() for m in models}
before=fingerprints()
all_rows=[row for model in models for row in model.objects.order_by('pk')]
(backup/'existing-data.json').write_text(serializers.serialize('json',all_rows))
(backup/'manifest.json').write_text(json.dumps({'release':manifest,'fingerprints':before},indent=2))
token=Token.objects.filter(user__profile__role__in=['EXPERT_TEACHER','RESEARCHER_ADMIN']).first()
assert token, 'Existing staff token required for HTTP verification'
def get(path,auth=False):
    request=Request('https://trace.musfiqurtuhin.me'+path,headers={'Authorization':'Token '+token.key} if auth else {})
    with urlopen(request,timeout=20) as response:
        return json.loads(response.read())
def restart():
    subprocess.run(['pm2','restart','trace-tutor'],env=env,check=True,stdout=subprocess.DEVNULL)
    for attempt in range(10):
        try:
            assert get('/api/health/')['database']=='ok'
            return
        except Exception:
            if attempt==9: raise
            time.sleep(1)
try:
    for relative in manifest:
        destination=ROOT/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(STAGE/relative,destination)
    subprocess.run([str(ROOT/'venv/bin/python'),'manage.py','check'],cwd=ROOT/'backend',env=env,check=True)
    subprocess.run([str(ROOT/'venv/bin/python'),'manage.py','migrate','assessment','--noinput'],cwd=ROOT/'backend',env=env,check=True)
    for src in (STAGE/'frontend/dist').rglob('*'):
        if src.is_file() and src.name!='index.html':
            destination=ROOT/'frontend/dist'/src.relative_to(STAGE/'frontend/dist')
            destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,destination)
    temporary=ROOT/'frontend/dist/index.html.protocol-new'
    shutil.copy2(STAGE/'frontend/dist/index.html',temporary)
    temporary.replace(ROOT/'frontend/dist/index.html')
    # WhiteNoise indexes files when the worker starts. Restart only after every
    # emitted asset and the new index have been published, or fresh hashes 404.
    restart()
    schedule=get('/api/assessment/schedule/',True)
    assert schedule['late_submission_allowed'] and schedule['phases']['post']['wait_days']==7
    assert schedule['phases']['transfer']['wait_days']==14
    queue=get('/api/expert/submissions/',True)
    assert all('timing' in row for row in queue['submissions'])
    for asset in (STAGE/'frontend/dist').rglob('*'):
        if asset.is_file() and asset.suffix in {'.js','.css'}:
            url='https://trace.musfiqurtuhin.me/'+asset.relative_to(STAGE/'frontend/dist').as_posix()
            with urlopen(url,timeout=20) as response:
                body=response.read()
                assert response.status==200 and not body.lstrip().startswith(b'<!DOCTYPE'), url
    expected_index=(STAGE/'frontend/dist/index.html').read_text()
    expected_entry=re.search(r'/assets/index-[^" ]+\.js',expected_index).group()
    with urlopen('https://trace.musfiqurtuhin.me/?protocol-release=20261025',timeout=20) as response:
        assert expected_entry in response.read().decode(), 'Published frontend entry not served'
    assert fingerprints()==before, 'Existing data changed during publication'
    (backup/'PUBLISHED.json').write_text(json.dumps({'completed_at':datetime.now(timezone.utc).isoformat(),'staff_queue_count':queue['count']}))
    print('PROTOCOL_PUBLISHED',json.dumps({'backup':str(backup),'staff_queue_count':queue['count'],'existing_data_unchanged':True}),flush=True)
except Exception:
    for relative, hashes in manifest.items():
        target=ROOT/relative
        if hashes['before']:
            shutil.copy2(backup/relative,target)
        elif target.exists():
            assert target.resolve().is_relative_to(ROOT.resolve())
            target.unlink()
    shutil.copy2(backup/'index.html',ROOT/'frontend/dist/index.html')
    restart()
    print('PROTOCOL_ROLLED_BACK; additive empty timeline table may remain',flush=True)
    raise
