from pathlib import Path
from urllib.request import urlopen
import hashlib, json, os, subprocess, sys
root = Path('/srv/trace-tutor')
stage = sorted((root / 'deployment-backups').glob('header-search-*'))[-1] / 'new-dist'
base = 'https://trace.musfiqurtuhin.me'
bundle = Path('/tmp/trace-tutor-header-search-release')
fingerprints = json.loads((bundle / 'environment-fingerprints.json').read_text())
for rel, digest in fingerprints.items():
    if rel != 'pm2_environment':
        assert hashlib.sha256((root / rel).read_bytes()).hexdigest() == digest, 'Environment file changed: ' + rel
env = dict(os.environ)
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
processes = json.loads(subprocess.check_output(['pm2', 'jlist'], env=env))
process = next(p for p in processes if p['name'] == 'trace-tutor')
assert process['pm2_env']['status'] == 'online'
assert hashlib.sha256(json.dumps(process['pm2_env'].get('env', {}), sort_keys=True).encode()).hexdigest() == fingerprints['pm2_environment'], 'PM2 environment changed'
print('PASS environment files and PM2 environment unchanged')
for route in ['/', '/profile', '/dashboard', '/workspace', '/workspace?problem=prob_c_loop_101', '/assessment', '/api/health/']:
    with urlopen(base + route, timeout=30) as response:
        body = response.read()
        assert response.status == 200
    if route == '/api/health/':
        assert json.loads(body)['database'] == 'ok'
    else:
        assert body == (stage / 'index.html').read_bytes()
    print('PASS public route:', route)
for pattern in ['index-*.js', 'index-*.css', 'Workspace-*.js', 'Dashboard-*.js', 'Profile-*.js', 'AssessmentPage-*.js', 'tutorModel-*.js']:
    matches = list((stage / 'assets').glob(pattern))
    assert matches, 'Required release asset missing: ' + pattern
    for path in matches:
        with urlopen(base + '/assets/' + path.name, timeout=30) as response:
            assert response.read() == path.read_bytes()
        print('PASS asset matches release:', path.name)
for rel, entry in json.loads((bundle / 'release.json').read_text()).items():
    assert (root / rel).read_text() == entry['content'], 'Published source mismatch: ' + rel
search_script = """import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const original=await readFile('frontend/src/services/learningSearch.js','utf8');
const source=original.replace("'../data/problems'",JSON.stringify(pathToFileURL(resolve('frontend/src/data/problems.js')).href));
if(source===original) throw Error('Catalogue import verification mismatch');
const {loadLearningCatalog,searchLearningCatalog}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const catalog=await loadLearningCatalog();
const results=searchLearningCatalog(catalog,'  LoOp  ');
if(!results.some(x=>x.type==='Topic') || !results.some(x=>x.id==='prob_c_loop_101')) throw Error('Loop search failed');
if(searchLearningCatalog(catalog,'no-such-topic-xyzzzz').length) throw Error('Empty result failed');
if(!results.every(x=>x.destination.startsWith('/workspace?problem=') && !x.locked)) throw Error('Unsafe navigation');
console.log(JSON.stringify(results.map(({title,type,destination})=>({title,type,destination}))));"""
search_results = subprocess.check_output(['node', '--input-type=module', '-e', search_script], cwd=root, text=True)
print('PASS deployed catalogue loop matching, destinations and no-results behavior:', search_results.strip())
log_baseline = json.loads((bundle / 'log-baseline.json').read_text())
log_path = Path(log_baseline['path'])
if log_path.exists():
    with log_path.open('rb') as log:
        log.seek(min(log_baseline['offset'], log_path.stat().st_size))
        new_logs = log.read().decode(errors='replace')
    assert not any(marker in new_logs for marker in ['Traceback (most recent call last)', 'ModuleNotFoundError', 'SyntaxError', 'Worker failed to boot']), 'New critical application log error'
print('PASS PM2 online; no new critical Python/startup log errors')
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trace_backend.settings')
import django
django.setup()
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.test import APIRequestFactory, force_authenticate
from trace_backend import llm
from assessment import sittings
from logging_app.views import dashboard_summary
from tutor.views import query_tutor
from unittest.mock import patch
students = User.objects.filter(is_active=True, profile__role='STUDENT').order_by('id')
user = students.first()
assert user is not None, 'No student available for backend metadata verification'
# Keep verification telemetry/cache writes out of the study's persistent data.
# Exceptions automatically roll back; successful checks explicitly roll back too.
with transaction.atomic():
    request = APIRequestFactory().get('/api/dashboard/')
    force_authenticate(request, user=user)
    response = dashboard_summary(request)
    assert response.status_code == 200
    assert response['Cache-Control'] == 'no-store'
    assert response.data['tutor_model'] == llm.public_metadata()
    assert set(response.data['tutor_model']) == {'provider', 'primary_model', 'fallback_models', 'configured'}
    assert response.data['tutor_availability']['available'] == (sittings.blocking_paper(user) is None)
    print('PASS safe dashboard metadata:', json.dumps(response.data['tutor_model']))
    label_script = "import {configuredTutorLabel, describeTutorModel} from './frontend/src/services/tutorModel.js'; const metadata=JSON.parse(process.argv[1]); const dashboard=configuredTutorLabel(metadata); const workspace=describeTutorModel(metadata,null).label; if(dashboard!==workspace) throw Error('Labels disagree'); console.log(dashboard);"
    label = subprocess.check_output(['node', '--input-type=module', '-e', label_script, json.dumps(response.data['tutor_model'])], cwd=root, text=True).strip()
    print('PASS shared Dashboard/Workspace label from production metadata:', label)
    locked_user = next((student for student in students.iterator() if sittings.blocking_paper(student)), None)
    if locked_user is not None:
        request = APIRequestFactory().post('/api/tutor/query/', {'prompt': 'Deployment policy check', 'language': 'en'}, format='json')
        force_authenticate(request, user=locked_user)
        with patch('tutor.views.llm.generate_json', side_effect=AssertionError('Paid generation forbidden during verification')) as generate, patch('tutor.views.rag_engine_instance.retrieve', side_effect=AssertionError('Embedding retrieval forbidden during policy verification')):
            response = query_tutor(request)
        assert response.status_code == 403 and response.data['reason'] == 'paper_in_progress'
        generate.assert_not_called()
        print('PASS active production paper rejects generation')
    else:
        print('INFO no currently locked student; active pre-test scenario verified by isolated regression tests')
    transaction.set_rollback(True)
print('PASS verification data transaction rolled back; existing student data preserved')
print('PASS no paid generation requested; generation behavior covered by isolated mocked regressions')
