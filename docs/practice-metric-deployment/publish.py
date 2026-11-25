"""Publish a tested release using the existing PM2 service, with guarded rollback."""
import base64, hashlib, json, os, shutil, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path('/srv/trace-tutor')
STAGE = Path('/tmp/trace-practice-metric-v2-20261123')
assert (STAGE / 'STAGING_VERIFIED').exists()
assert not (STAGE / 'PUBLISHED.json').exists()
release = json.loads((STAGE / 'release.json').read_text())
backup = ROOT / 'deployment-backups' / ('practice-metric-v2-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
def digest(p):
    return hashlib.sha256(p.read_bytes().replace(b'\r\n', b'\n')).hexdigest() if p.exists() else None
for rel, entry in release.items():
    assert digest(ROOT / rel) == entry['before'], 'Production changed since audit: ' + rel
backup.mkdir(mode=0o700)
for rel, entry in release.items():
    if entry['before'] is not None:
        saved = backup / 'sources' / rel
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, saved)
        assert digest(saved) == entry['before']
shutil.copytree(ROOT / 'frontend/dist', backup / 'dist')
(backup / 'release.json').write_text(json.dumps(release))
protected = {str(p): digest(p) for p in (ROOT / '.env', ROOT / 'backend/.env')}
def restart():
    subprocess.run(['pm2', 'restart', 'trace-tutor'], env=env, check=True, stdout=subprocess.DEVNULL)
    for attempt in range(12):
        try:
            with urlopen('https://trace.musfiqurtuhin.me/api/health/', timeout=10) as r:
                assert json.loads(r.read())['database'] == 'ok'
            return
        except Exception:
            if attempt == 11:
                raise
            time.sleep(1)
try:
    for rel, entry in release.items():
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(entry['content']))
    subprocess.run([str(ROOT / 'venv/bin/python'), 'manage.py', 'check'], cwd=ROOT / 'backend', env=env, check=True)
    dist = STAGE / 'candidate/frontend/dist'
    for p in dist.rglob('*'):
        if p.is_file() and p.name != 'index.html':
            target = ROOT / 'frontend/dist' / p.relative_to(dist)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
    temporary = ROOT / 'frontend/dist/index.html.practice-next'
    shutil.copy2(dist / 'index.html', temporary)
    temporary.replace(ROOT / 'frontend/dist/index.html')
    restart()
    verification = subprocess.check_output([str(ROOT / 'venv/bin/python'), str(STAGE / 'verify_live.py')], cwd=ROOT / 'backend', env=env, text=True)
    assert all(digest(Path(p)) == expected for p, expected in protected.items()), 'Protected configuration changed'
    assert all(digest(ROOT / rel) == entry['after'] for rel, entry in release.items())
    subprocess.run(['pm2', 'save'], env=env, check=True, stdout=subprocess.DEVNULL)
    result = {'completed_at': datetime.now(timezone.utc).isoformat(), 'backup': str(backup), 'files': len(release), 'verification': verification.strip()}
    (backup / 'PUBLISHED.json').write_text(json.dumps(result, indent=2))
    (STAGE / 'PUBLISHED.json').write_text(json.dumps(result, indent=2))
    print('PUBLISHED', json.dumps(result), flush=True)
except Exception:
    for rel, entry in release.items():
        target = ROOT / rel
        if entry['before'] is not None:
            shutil.copy2(backup / 'sources' / rel, target)
        elif target.exists():
            assert target.resolve().is_relative_to(ROOT.resolve())
            assert digest(target) == entry['after']
            target.unlink()
    temporary = ROOT / 'frontend/dist/index.html.practice-rollback'
    shutil.copy2(backup / 'dist/index.html', temporary)
    temporary.replace(ROOT / 'frontend/dist/index.html')
    restart()
    (backup / 'ROLLED_BACK').write_text(datetime.now(timezone.utc).isoformat())
    print('ROLLED_BACK', str(backup), flush=True)
    raise
