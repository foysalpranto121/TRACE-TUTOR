"""Existing guarded PM2/asset publication, adapted to one verified combined release."""
from pathlib import Path
from datetime import datetime, timezone
import base64, hashlib, json, os, shutil, subprocess, sys, time
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
bundle = Path(__file__).resolve().parent
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
assert sys.argv[1:] == ['--rollback'], 'Explicit --rollback required'
assert (backup / 'BACKUP_VERIFIED').exists() and (backup / 'PUBLISHED').exists()
for rel, entry in files.items():
    target = root / rel
    digest = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
    assert digest in {entry['expected_sha256'], entry['sha256']}, 'A later release changed this file; review before rollback: ' + rel
rollback()
