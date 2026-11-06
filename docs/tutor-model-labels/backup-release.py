"""Use the existing read-only study backup; restore-verify only in a private cluster."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-model-release')
backup = Path(sys.argv[1]).resolve()
assert backup.parent == root / 'deployment-backups' and backup.name.startswith('tutor-model-labels-')
backup.chmod(0o700)
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
settings.BACKUP_DIR = backup / 'study-backup'
folder = Path(call_command('backup_study', keep=0)).resolve()
assert folder.is_relative_to(backup)
subprocess.run([str(root / 'venv/bin/python'), str(bundle / 'test-release.py'), str(backup), '--verify-backup', str(folder)], check=True)
for rel in ['.env', 'backend/.env']:
    source = root / rel
    if source.exists():
        destination = backup / 'environment' / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        destination.chmod(0o600)
        assert source.read_bytes() == destination.read_bytes()
checksums = {}
for location in ['dist', 'backend', 'frontend', 'study-backup', 'environment']:
    for path in (backup / location).rglob('*'):
        if path.is_file():
            checksums[str(path.relative_to(backup))] = hashlib.sha256(path.read_bytes()).hexdigest()
for relative, digest in checksums.items():
    assert hashlib.sha256((backup / relative).read_bytes()).hexdigest() == digest
(backup / 'backup-checksums.json').write_text(json.dumps(checksums, indent=2))
print('PASS verified production backup: sources, frontend build, environment, database dump and file stores', flush=True)
