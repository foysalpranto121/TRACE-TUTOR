"""Publish the validated frontend, with guarded source hashes and rollback."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import time
from urllib.request import Request, urlopen
from uuid import uuid4

root = Path('/srv/trace-tutor')
frontend = root / 'frontend'
stage = Path('/tmp/trace-profile-header-20261026-c8d420')
staged = json.loads((stage / 'STAGED.json').read_text())
manifest = staged['runtime']
new_dist = stage / 'build/dist'
origin = 'https://trace.musfiqurtuhin.me'
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

for rel, expected in staged['baseline'].items():
    assert digest(frontend / rel) == expected, 'Production changed since staging: ' + rel
for rel, entry in manifest.items():
    assert digest(stage / 'candidate/runtime' / rel) == entry['after']
    assert digest(frontend / rel) == entry['before']

backup = root / 'deployment-backups' / ('profile-header-20261026-' + uuid4().hex[:12])
backup.mkdir(mode=0o700)
for rel, entry in manifest.items():
    if entry['before'] is not None:
        destination = backup / 'frontend' / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(frontend / rel, destination)
        assert digest(destination) == entry['before']
shutil.copytree(frontend / 'dist', backup / 'dist')
for path in (frontend / 'dist').rglob('*'):
    if path.is_file():
        assert digest(backup / 'dist' / path.relative_to(frontend / 'dist')) == digest(path)
(backup / 'release.json').write_text(json.dumps(manifest, indent=2))
print('Verified rollback backup:', backup, flush=True)

def get(path):
    request = Request(origin + path, headers={'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity'})
    with urlopen(request, timeout=25) as response:
        return response.read(), response.headers.get('Content-Type', '')

def restart_and_health():
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

try:
    for rel in manifest:
        destination = frontend / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage / 'candidate/runtime' / rel, destination)
    # Preserve old hashed assets for already-open tabs. Switch the index last.
    for path in new_dist.rglob('*'):
        if path.is_file() and path.name != 'index.html':
            destination = frontend / 'dist' / path.relative_to(new_dist)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    temporary = frontend / 'dist/index.html.expert-new'
    shutil.copy2(new_dist / 'index.html', temporary)
    temporary.replace(frontend / 'dist/index.html')
    # WhiteNoise discovers new assets when the worker starts.
    restart_and_health()
    checks = []
    for path in new_dist.rglob('*'):
        if path.is_file() and path.suffix in {'.js', '.css'}:
            relative = path.relative_to(new_dist).as_posix()
            body, content_type = get('/' + relative)
            assert hashlib.sha256(body).hexdigest() == digest(path), 'Live asset mismatch: ' + relative
            assert ('javascript' in content_type if path.suffix == '.js' else 'text/css' in content_type), 'Wrong MIME: ' + relative
            checks.append(relative)
    for path in ('/', '/profile'):
        body, content_type = get(path + '?profile-header-release=20261026')
        assert body == (new_dist / 'index.html').read_bytes(), 'Live index mismatch: ' + path
        assert 'text/html' in content_type
    for rel, entry in manifest.items():
        assert digest(frontend / rel) == entry['after']
    for rel, expected in staged['baseline'].items():
        if rel not in manifest:
            assert digest(frontend / rel) == expected, 'Unrelated frontend file changed: ' + rel
    result = {
        'status': 'published', 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'site': origin + '/profile', 'backup': str(backup), 'runtime_files': manifest,
        'verified_assets': checks, 'database_health': 'ok',
        'production_database_writes': False, 'browser_interaction_verified': False,
    }
    (backup / 'PUBLISHED.json').write_text(json.dumps(result, indent=2))
    (stage / 'PUBLISHED.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2), flush=True)
except Exception:
    for rel, entry in manifest.items():
        target = frontend / rel
        if entry['before'] is not None:
            shutil.copy2(backup / 'frontend' / rel, target)
        elif target.exists():
            assert target.resolve().is_relative_to(frontend.resolve())
            target.unlink()
    for path in (backup / 'dist').rglob('*'):
        if path.is_file() and path.name != 'index.html':
            target = frontend / 'dist' / path.relative_to(backup / 'dist')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    temporary = frontend / 'dist/index.html.expert-rollback'
    shutil.copy2(backup / 'dist/index.html', temporary)
    temporary.replace(frontend / 'dist/index.html')
    restart_and_health()
    print('ROLLED BACK: restored previous frontend sources and index.', flush=True)
    raise
