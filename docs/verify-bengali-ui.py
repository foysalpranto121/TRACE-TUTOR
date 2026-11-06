from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
import json, re, hashlib
root = Path('/srv/trace-tutor/frontend/dist')
base = 'https://trace.musfiqurtuhin.me'
for route in ['/', '/register', '/login', '/profile', '/api/health/']:
    with urlopen(base + route, timeout=30) as response:
        body = response.read()
        assert response.status == 200
    if route != '/api/health/':
        assert body == (root / 'index.html').read_bytes()
    else:
        assert json.loads(body)['database'] == 'ok'
    print('PASS HTTP 200:', route)
backup = sorted((root.parent.parent / 'deployment-backups').glob('bengali-ui-*'))[-1]
stage = backup / 'new-dist'
files = [stage / 'fonts/noto-sans-bengali-regular.ttf']
files += list((stage / 'assets').glob('index-*.css'))
for pattern in ['index-*.js', 'Register-*.js', 'LandingPage-*.js', 'Login-*.js', 'Dashboard-*.js', 'Profile-*.js']:
    files += list((stage / 'assets').glob(pattern))
for path in files:
    asset = '/' + str(path.relative_to(stage))
    with urlopen(base + asset, timeout=30) as response:
        body = response.read()
        assert response.status == 200
    assert body == path.read_bytes(), asset
    print('PASS live build matches:', asset, hashlib.sha256(body).hexdigest()[:12])
register = next((stage / 'assets').glob('Register-*.js')).read_text()
assert 'choose your own' in register
assert 'autoComplete:"off"' in register
assert 'Math.random' not in register
css = next((stage / 'assets').glob('index-*.css')).read_text()
assert 'font-weight:100 900' in css
assert 'noto-sans-bengali-regular.ttf' in css
request = Request(base + '/api/accounts/register/', data=json.dumps({'email':'username-check@example.com','full_name':'Username validation check','password':'','consent_given':False}).encode(), headers={'Content-Type':'application/json'}, method='POST')
try:
    urlopen(request, timeout=30)
    raise AssertionError('Registration without a username should be rejected')
except HTTPError as e:
    assert e.code == 400
    assert 'username' in json.loads(e.read())['fields']
print('PASS registration requires an explicit username; no account created.')
