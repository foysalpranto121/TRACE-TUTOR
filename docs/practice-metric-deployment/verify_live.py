"""Read-only production verification; executes safe code without recording practice credit."""
import hashlib, json, os, re, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path('/srv/trace-tutor')
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from tutor import practice, runner
from rest_framework.authtoken.models import Token

BASE = 'https://trace.musfiqurtuhin.me'
def get(path, token=None):
    req = Request(BASE + path, headers={'Authorization': 'Token ' + token.key} if token else {})
    with urlopen(req, timeout=30) as response:
        return response.read()

assert json.loads(get('/api/health/'))['database'] == 'ok'
dist = ROOT / 'frontend/dist'
index = (dist / 'index.html').read_text()
public_index = get('/?practice-metric-v2=20261123').decode()
assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', index)
assert assets
for asset in assets:
    assert asset in public_index
for p in dist.glob('assets/*'):
    # Only this release's emitted files are checked, not retained older assets.
    staged = Path('/tmp/trace-practice-metric-v2-20261123/candidate/frontend/dist/assets') / p.name
    if staged.is_file():
        assert hashlib.sha256(get('/assets/' + p.name)).digest() == hashlib.sha256(staged.read_bytes()).digest(), p.name
for route in ('/login', '/dashboard', '/workspace'):
    assert '/assets/' in get(route).decode()
token = Token.objects.select_related('user').order_by('pk').first()
assert token is not None, 'An existing token is needed for authenticated read-only verification'
dashboard = json.loads(get('/api/dashboard/', token))
assert dashboard['practice_metric_version'] == 2
assert 'practice_tasks_passed' in dashboard['stats']
assert 'legacy_tasks_successful' in dashboard['stats']
assert all('verified_passed' in p for p in dashboard['problems'])
req = Request(BASE + '/api/telemetry/log/', method='POST',
              headers={'Authorization': 'Token ' + token.key, 'Content-Type': 'application/json'},
              data=json.dumps({'event_type': 'CODE_RESULT', 'event_data': {'status': 'SUCCESS'}}).encode())
try:
    urlopen(req, timeout=30)
    raise AssertionError('Client-created verdict was accepted')
except HTTPError as error:
    assert error.code == 400, error.code
table = '<!DOCTYPE html><html><head><title>Marks</title></head><body><table><tr><th>Roll</th><th>Marks</th></tr><tr><td>101</td><td>85</td></tr></table></body></html>'
html = runner.run_code('html', table, practice.TASKS['prob_html_table_201']['test_cases'], strict_output=True)
assert html['status'] == 'SUCCESS', html['status']
c_code = '#include <stdio.h>\nint main(void){int n;if(scanf("%d",&n)!=1)return 1;printf("Sum = %d",n*(n+1)/2);return 0;}'
c = runner.run_code('c', c_code, practice.TASKS['prob_c_loop_101']['test_cases'], strict_output=True)
assert c['status'] == 'SUCCESS', c
print(json.dumps({'health': 'ok', 'public_assets': 'hash verified', 'routes': 'ok',
                  'metric_version': dashboard['practice_metric_version'], 'dashboard_fields': 'verified',
                  'forged_result': 'rejected', 'html_checks': html['status'], 'c_checks': c['status'],
                  'catalog_sha256': practice.CATALOG_SHA256}))
