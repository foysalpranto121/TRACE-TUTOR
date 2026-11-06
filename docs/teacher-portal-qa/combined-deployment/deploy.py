"""Existing guarded PM2/asset publication, adapted to one verified combined release."""
from pathlib import Path
from datetime import datetime, timezone
import base64, hashlib, json, os, shutil, subprocess, sys, time
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-combined-20261009')
backup = root / 'deployment-backups/combined-teacher-docker-20261009T175621Z'
files = json.loads((bundle / 'release.json').read_text())
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
def health():
    error = None
    for _ in range(8):
        try:
            with urlopen('https://trace.musfiqurtuhin.me/api/health/', timeout=15) as r:
                assert json.loads(r.read())['database'] == 'ok'
            return
        except Exception as e:
            error = e
            time.sleep(1)
    raise error
def restart():
    subprocess.run(['pm2', 'restart', 'trace-tutor'], env=env, check=True)
def rollback():
    for rel, entry in files.items():
        target = root / rel
        if entry['expected_sha256'] is not None:
            saved = backup / 'sources' / rel
            assert hashlib.sha256(saved.read_bytes()).hexdigest() == entry['expected_sha256']
            shutil.copy2(saved, target)
        elif target.exists():
            assert hashlib.sha256(target.read_bytes()).hexdigest() == entry['sha256'], 'Unexpected source change; refusing delete'
            target.unlink()
    for file in (backup / 'dist').rglob('*'):
        if file.is_file() and file.name != 'index.html':
            destination = root / 'frontend/dist' / file.relative_to(backup / 'dist')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
    temporary = root / 'frontend/dist/index.html.rollback'
    shutil.copy2(backup / 'dist/index.html', temporary)
    temporary.replace(root / 'frontend/dist/index.html')
    restart()
    health()
    (backup / 'ROLLED_BACK').write_text(datetime.now(timezone.utc).isoformat())
    print('ROLLED BACK previous application; production database not restored or reset', flush=True)
if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
    assert (backup / 'PUBLISHED').exists()
    rollback()
    sys.exit(0)
assert (backup / 'BACKUP_VERIFIED').is_file() and (backup / 'STAGING_VERIFIED').is_file()
assert not (backup / 'PUBLISHED').exists(), 'This single release was already published'
manifest = json.loads((backup / 'backup-manifest.json').read_text())
for rel, digest in manifest['files'].items():
    assert hashlib.sha256((backup / rel).read_bytes()).hexdigest() == digest, 'Rollback backup altered'
for rel, entry in files.items():
    target = root / rel
    assert (hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None) == entry['expected_sha256'], 'Source changed since audit: ' + rel
for rel, digest in json.loads((bundle / 'dependencies.json').read_text()).items():
    p = root / rel
    data = p.read_bytes()
    if p.suffix in {'.py', '.js', '.jsx', '.json', '.txt', '.css', '.mjs', '.html'}:
        data = data.replace(b'\r\n', b'\n')
    assert hashlib.sha256(data).hexdigest() == digest, 'Dependency changed: ' + rel
process = next(p for p in json.loads(subprocess.check_output(['pm2', 'jlist'], env=env)) if p['name'] == 'trace-tutor')
log = Path(process['pm2_env']['pm_err_log_path'])
(backup / 'log-baseline.json').write_text(json.dumps({'path': str(log), 'offset': log.stat().st_size if log.exists() else 0}))
health()
subprocess.run([str(root / 'venv/bin/python'), str(bundle / 'verify.py'), '--baseline'], check=True)
try:
    for rel, entry in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(entry['base64'])
        assert hashlib.sha256(data).hexdigest() == entry['sha256']
        target.write_bytes(data)
    subprocess.run([str(root / 'venv/bin/python'), 'manage.py', 'check'], cwd=root / 'backend', check=True)
    restart()
    health()
    stage = backup / 'new-dist'
    for file in stage.rglob('*'):
        if file.is_file() and file.name != 'index.html':
            destination = root / 'frontend/dist' / file.relative_to(stage)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, destination)
    temporary = root / 'frontend/dist/index.html.next'
    shutil.copy2(stage / 'index.html', temporary)
    temporary.replace(root / 'frontend/dist/index.html')
    restart()
    health()
    subprocess.run([str(root / 'venv/bin/python'), str(bundle / 'verify.py')], check=True)
    subprocess.run(['pm2', 'save'], env=env, check=True)
    (backup / 'PUBLISHED').write_text(datetime.now(timezone.utc).isoformat())
except Exception:
    rollback()
    raise
print('PUBLISHED one combined release; application and safe sandbox checks passed', flush=True)
