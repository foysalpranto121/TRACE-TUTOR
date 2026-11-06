"""Read-only confirmation following an aborted pre-publication release."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
from urllib.request import urlopen

root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-model-release')
for rel, entry in json.loads((bundle / 'release.json').read_text()).items():
    path = root / rel
    assert (not path.exists()) if entry['expected'] is None else (path.exists() and path.read_text() == entry['expected']), rel
print('PASS all production source files unchanged; new release files absent')
fingerprints = json.loads((bundle / 'environment-fingerprints.json').read_text())
for rel, digest in fingerprints.items():
    if rel != 'pm2_environment':
        assert hashlib.sha256((root / rel).read_bytes()).hexdigest() == digest
env = dict(os.environ)
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
process = next(p for p in json.loads(subprocess.check_output(['pm2', 'jlist'], env=env)) if p['name'] == 'trace-tutor')
assert process['pm2_env']['status'] == 'online'
assert hashlib.sha256(json.dumps(process['pm2_env'].get('env', {}), sort_keys=True).encode()).hexdigest() == fingerprints['pm2_environment']
print('PASS production process online and environment unchanged')
base = 'https://trace.musfiqurtuhin.me'
for route in ['/', '/dashboard', '/workspace', '/assessment', '/api/health/']:
    with urlopen(base + route, timeout=30) as response:
        body = response.read()
        assert response.status == 200
    if route == '/api/health/':
        assert json.loads(body)['database'] == 'ok'
    else:
        assert body == (root / 'frontend/dist/index.html').read_bytes()
    print('PASS previous production version:', route)
