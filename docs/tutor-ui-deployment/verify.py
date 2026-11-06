from pathlib import Path
from urllib.request import urlopen
import json, hashlib, os, sys
root = Path('/srv/trace-tutor')
stage = sorted((root / 'deployment-backups').glob('tutor-availability-*'))[-1] / 'new-dist'
base = 'https://trace.musfiqurtuhin.me'
for route in ['/', '/workspace', '/assessment', '/api/health/']:
    with urlopen(base + route, timeout=30) as response:
        body = response.read()
        assert response.status == 200
    if route != '/api/health/':
        assert body == (stage / 'index.html').read_bytes()
    else:
        assert json.loads(body)['database'] == 'ok'
    print('PASS public route:', route)
for pattern in ['index-*.js', 'index-*.css', 'Workspace-*.js']:
    for path in (stage / 'assets').glob(pattern):
        asset = '/assets/' + path.name
        with urlopen(base + asset, timeout=30) as response:
            body = response.read()
        assert body == path.read_bytes(), asset
        print('PASS deployed asset:', asset, hashlib.sha256(body).hexdigest()[:12])
workspace = next((stage / 'assets').glob('Workspace-*.js')).read_text()
assert 'Tutor temporarily unavailable' in workspace
assert 'Please submit your paper before using the AI Tutor.' in workspace
assert 'Checking tutor availability' in workspace
assert 'Could not verify tutor availability' in workspace
assert 'tutor_availability' in workspace
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trace_backend.settings')
import django
django.setup()
from django.contrib.auth.models import User
from rest_framework.test import APIRequestFactory, force_authenticate
from assessment import sittings
from logging_app.views import dashboard_summary
users = list(User.objects.filter(is_active=True, profile__role='STUDENT').order_by('id')[:100])
assert users, 'No student account available for read-only endpoint verification'
user = next((u for u in users if sittings.blocking_paper(u)), users[0])
blocking = sittings.blocking_paper(user)
request = APIRequestFactory().get('/api/dashboard/')
force_authenticate(request, user=user)
response = dashboard_summary(request)
assert response.status_code == 200
assert response['Cache-Control'] == 'no-store'
assert response.data['tutor_availability'] == {
    'available': blocking is None,
    'reason': 'paper_in_progress' if blocking else None,
    'exam_type': blocking,
}
print('PASS deployed dashboard matches authoritative tutor policy; available=' + str(blocking is None))
print('PASS read-only verification: no account, sitting, submission, or AI request created.')
