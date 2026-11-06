"""Read-only audit of released sources, verified backup and production role security."""
from pathlib import Path
import hashlib
import json
import os
import sys

root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-header-search-release')
files = json.loads((bundle / 'release.json').read_text())
for rel, entry in files.items():
    assert (root / rel).read_text() == entry['content'], 'Released source differs: ' + rel
print('PASS all 5 production release files exactly match the verified header-search manifest')
backup = sorted((root / 'deployment-backups').glob('header-search-*'))[-1]
checksums = json.loads((backup / 'backup-checksums.json').read_text())
for rel, digest in checksums.items():
    assert hashlib.sha256((backup / rel).read_bytes()).hexdigest() == digest, 'Backup checksum differs'
manifest_path = next((backup / 'study-backup').glob('*/manifest.json'))
manifest = json.loads(manifest_path.read_text())
assert manifest['verified_at'] and manifest['verified_in'] == 'private disposable PostgreSQL 16 cluster'
print('PASS verified production backup checksums:', str(backup))
assert not list(Path('/tmp').glob('trace-release-pg-*')), 'Private test cluster directory still present'
print('PASS all disposable PostgreSQL directories removed')
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user')
    assert cursor.fetchone()[0] is False, 'Production role security changed'
print('PASS production database role still lacks CREATEDB')
