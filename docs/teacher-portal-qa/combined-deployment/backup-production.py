"""Consistent production backup and isolated restore; streamed over SSH before uploads."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, os, secrets, shutil, subprocess, sys, tempfile
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
assert root.resolve() == root and root.is_dir() and os.getuid() != 0
with urlopen('https://trace.musfiqurtuhin.me/api/health/', timeout=15) as r:
    assert json.loads(r.read())['database'] == 'ok'
assert shutil.disk_usage(root).free > 5 * 1024**3
backup = root / 'deployment-backups' / ('combined-teacher-docker-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(mode=0o700)
print('BACKUP_DIRECTORY=' + str(backup), flush=True)
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from django.conf import settings
import psycopg2
from psycopg2 import sql
db = settings.DATABASES['default']
pgbin = Path('/usr/lib/postgresql/16/bin')
assert all((pgbin / n).is_file() for n in ['pg_dump', 'pg_restore', 'initdb', 'pg_ctl'])
def digest(file):
    h = hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()
ignore = shutil.ignore_patterns('node_modules', 'dist', '__pycache__', '*.pyc', '.env*', '*.log', 'media', 'staticfiles', 'backups', '.cache', 'chroma_store', 'data')
for folder in ['backend', 'frontend']:
    shutil.copytree(root / folder, backup / 'sources' / folder, ignore=ignore)
shutil.copytree(root / 'frontend/dist', backup / 'dist')
for name in ['.env', 'backend/.env']:
    source = root / name
    if source.exists():
        target = backup / 'environment' / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(source, target)
        target.chmod(0o600)
        assert digest(source) == digest(target)
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
pm2 = json.loads(subprocess.check_output(['pm2', 'jlist'], env=env))
process = next(p for p in pm2 if p['name'] == 'trace-tutor')
assert process['pm2_env']['status'] == 'online'
(backup / 'pm2-private.json').write_text(json.dumps(process))
(backup / 'pm2-private.json').chmod(0o600)
stores = {'media': Path(settings.MEDIA_ROOT), 'ocr': root / 'backend/data/ocr',
          'chroma_store': root / 'backend/chroma_store', 'backend-data': root / 'backend/data',
          'RAG': root / 'RAG'}
for name, source in stores.items():
    if source.exists():
        assert source.is_dir()
        shutil.copytree(source, backup / 'persistent' / name)
snapshot = psycopg2.connect(dbname=db['NAME'], user=db['USER'], password=db.get('PASSWORD'),
                           host=db.get('HOST') or 'localhost', port=db.get('PORT') or 5432)
try:
    snapshot.set_session(isolation_level='REPEATABLE READ', readonly=True)
    with snapshot.cursor() as c:
        c.execute('SELECT pg_export_snapshot()')
        snapshot_id = c.fetchone()[0]
        c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        tables = [row[0] for row in c.fetchall()]
        counts = {}
        for table in tables:
            c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('public', table)))
            counts[table] = c.fetchone()[0]
        subprocess.run([str(pgbin / 'pg_dump'), '-h', db.get('HOST') or 'localhost', '-p', str(db.get('PORT') or 5432),
                        '-U', db['USER'], '-d', db['NAME'], '-Fc', '--no-owner', '--no-privileges',
                        '--snapshot=' + snapshot_id, '-f', str(backup / 'db.dump')],
                       env=dict(os.environ, PGPASSWORD=db.get('PASSWORD') or ''), check=True)
finally:
    snapshot.rollback()
    snapshot.close()
assert (backup / 'db.dump').stat().st_size > 0
with tempfile.TemporaryDirectory(prefix='trace-combined-restore-') as private_name:
    private = Path(private_name).resolve()
    assert private.parent == Path('/tmp') and private.stat().st_mode & 0o077 == 0
    data, socket = private / 'data', private / 'socket'
    socket.mkdir(mode=0o700)
    password = secrets.token_urlsafe(32)
    pwfile = private / 'password'
    pwfile.write_text(password + '\n')
    pwfile.chmod(0o600)
    subprocess.run([str(pgbin / 'initdb'), '-D', str(data), '--username=trace_restore_admin', '--auth-local=scram-sha-256',
                    '--auth-host=reject', '--encoding=UTF8', '--no-locale', '--pwfile=' + str(pwfile)], check=True, stdout=subprocess.DEVNULL)
    pwfile.unlink()
    with (data / 'postgresql.conf').open('a') as f:
        f.write("\nlisten_addresses = ''\nport = 15432\nunix_socket_directories = '" + str(socket) + "'\n")
    started = False
    try:
        subprocess.run([str(pgbin / 'pg_ctl'), '-D', str(data), '-l', str(private / 'postgres.log'), '-w', 'start'], check=True)
        started = True
        admin = psycopg2.connect(host=str(socket), port=15432, dbname='postgres', user='trace_restore_admin', password=password)
        admin.autocommit = True
        try:
            with admin.cursor() as c:
                c.execute('SHOW data_directory')
                assert Path(c.fetchone()[0]).resolve() == data
                c.execute("CREATE ROLE trace_restore_test LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %s", (password,))
                c.execute('CREATE DATABASE trace_restore_verification OWNER trace_restore_test')
        finally:
            admin.close()
        subprocess.run([str(pgbin / 'pg_restore'), '-h', str(socket), '-p', '15432', '-U', 'trace_restore_test',
                        '-d', 'trace_restore_verification', '--no-owner', '--no-privileges', '--exit-on-error', str(backup / 'db.dump')],
                       env=dict(os.environ, PGPASSWORD=password), check=True)
        with psycopg2.connect(host=str(socket), port=15432, dbname='trace_restore_verification', user='trace_restore_test', password=password) as restored:
            with restored.cursor() as c:
                c.execute('SELECT current_database(), current_user, inet_server_addr()')
                assert c.fetchone() == ('trace_restore_verification', 'trace_restore_test', None)
                for table, expected in counts.items():
                    c.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier('public', table)))
                    assert c.fetchone()[0] == expected, 'Restored count mismatch: ' + table
                c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
                assert [row[0] for row in c.fetchall()] == tables
        print('PASS isolated restore: every public table and snapshot count match', flush=True)
    finally:
        if started:
            subprocess.run([str(pgbin / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'], check=True)
checksums = {p.relative_to(backup).as_posix(): digest(p) for p in backup.rglob('*') if p.is_file()}
for rel, value in checksums.items():
    assert digest(backup / rel) == value
for folder, destination in [('backend', backup / 'sources/backend'), ('frontend', backup / 'sources/frontend')]:
    for file in destination.rglob('*'):
        if file.is_file():
            assert digest(file) == digest(root / folder / file.relative_to(destination)), 'Source changed during backup'
manifest = {'verified_at': datetime.now(timezone.utc).isoformat(), 'root': str(root), 'backup': str(backup),
            'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'row_counts': counts, 'consistent_snapshot': True, 'restored_in': 'private socket-only PostgreSQL 16 cluster',
            'files': checksums, 'affected_service': 'PM2 trace-tutor', 'automatic_database_restore': False}
(backup / 'backup-manifest.json').write_text(json.dumps(manifest, indent=2))
(backup / 'BACKUP_VERIFIED').write_text(manifest['verified_at'])
print('BACKUP_VERIFIED=' + str(backup), flush=True)
print('PASS database, application sources/dist, protected environment and persistent stores preserved', flush=True)
