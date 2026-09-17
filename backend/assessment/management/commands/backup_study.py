"""Back up everything the study depends on, and prove a backup can be restored.

    python manage.py backup_study                 # take one: BACKUP_DIR/<timestamp>/
    python manage.py backup_study --list          # what is there
    python manage.py backup_study --verify        # restore the newest into a scratch database
    python manage.py backup_study --verify <dir>  # restore a specific one

One backup folder holds a pg_dump of the database (custom format, compressed), copies of the
file-based stores the database does not contain - the transcription cache, the vector index and
the avatars - and a manifest.json with row counts, sizes, the code commit and the study manifest
at the time, so a restored copy can be checked against what was taken.

The database is the only copy of participant data. Schedule this daily (see README, "Backups")
and keep BACKUP_DIR on a different disk from the database.
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

COUNTED_TABLES = (
    'accounts_participantprofile', 'assessment_examsubmission', 'assessment_papersitting',
    'assessment_expertrating', 'logging_app_interactionlog', 'curriculum_curriculumpassage',
    'curriculum_ingestrun', 'curriculum_ocrpage',
)
FILE_STORES = {
    'ocr': lambda: Path(settings.BASE_DIR) / 'data' / 'ocr',
    'chroma_store': lambda: Path(settings.BASE_DIR) / 'chroma_store',
    'media': lambda: Path(settings.MEDIA_ROOT),
}
_SEARCH_DIRS = (
    r'M:\postgresql\bin', r'C:\Program Files\PostgreSQL\18\bin', r'C:\Program Files\PostgreSQL\17\bin',
    r'C:\Program Files\PostgreSQL\16\bin', '/usr/lib/postgresql/18/bin', '/usr/lib/postgresql/17/bin',
    '/usr/lib/postgresql/16/bin', '/usr/local/bin', '/opt/homebrew/opt/postgresql@18/bin',
)


def pg_tool(name):
    """Full path of a PostgreSQL client tool: PG_BIN, then PATH, then the usual install dirs."""
    exe = name + ('.exe' if os.name == 'nt' else '')
    if settings.PG_BIN:
        candidate = Path(settings.PG_BIN) / exe
        if candidate.exists():
            return str(candidate)
        raise CommandError(f'{exe} not found in PG_BIN={settings.PG_BIN}')
    found = shutil.which(name)
    if found:
        return found
    for folder in _SEARCH_DIRS:
        candidate = Path(folder) / exe
        if candidate.exists():
            return str(candidate)
    raise CommandError(f'{name} not found. Set PG_BIN to your PostgreSQL bin directory in backend/.env.')


def _db():
    return settings.DATABASES['default']


def _pg_env():
    env = dict(os.environ)
    env['PGPASSWORD'] = _db().get('PASSWORD') or ''
    return env


def _conn_args(database):
    db = _db()
    return ['-h', db.get('HOST') or 'localhost', '-p', str(db.get('PORT') or 5432), '-U', db.get('USER') or 'postgres',
            '-d', database]


def _run(argv, **kw):
    result = subprocess.run(argv, env=_pg_env(), capture_output=True, text=True, **kw)
    if result.returncode != 0:
        raise CommandError(f'{Path(argv[0]).name} failed ({result.returncode}): {result.stderr.strip()[:800]}')
    return result


def _dir_size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file()) if path.exists() else 0


def _row_counts(cursor=None):
    counts = {}
    own = cursor is None
    cur = cursor or connection.cursor()
    try:
        for table in COUNTED_TABLES:
            try:
                cur.execute(f'SELECT count(*) FROM "{table}"')
                counts[table] = cur.fetchone()[0]
            except Exception:
                counts[table] = None
    finally:
        if own:
            cur.close()
    return counts


class Command(BaseCommand):
    help = 'Back up the database and file stores into BACKUP_DIR, or verify a backup restores.'

    def add_arguments(self, parser):
        parser.add_argument('--list', action='store_true', help='List existing backups and exit')
        parser.add_argument('--verify', nargs='?', const='latest', metavar='DIR',
                            help='Restore a backup (default: the newest) into a scratch database, compare row '
                                 'counts with the manifest, then drop the scratch database')
        parser.add_argument('--keep', type=int, default=None,
                            help=f'How many newest backups to keep after this one (default BACKUP_KEEP={settings.BACKUP_KEEP}; 0 = all)')
        parser.add_argument('--no-files', action='store_true', help='Database only; skip the file stores')

    # ------------------------------------------------------------------ list
    def handle(self, *args, **opts):
        root = Path(settings.BACKUP_DIR)
        if opts['list']:
            return self._list(root)
        if opts['verify'] is not None:
            return self._verify(root, opts['verify'])
        return self._take(root, keep=settings.BACKUP_KEEP if opts['keep'] is None else opts['keep'],
                          with_files=not opts['no_files'])

    def _backups(self, root):
        if not root.exists():
            return []
        return sorted((p for p in root.iterdir() if p.is_dir() and (p / 'manifest.json').exists()), key=lambda p: p.name)

    def _list(self, root):
        backups = self._backups(root)
        if not backups:
            self.stdout.write(f'No backups in {root}')
            return
        for folder in backups:
            try:
                m = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
                size = m.get('total_bytes', 0) / 1024 ** 2
                verified = 'verified ' + m['verified_at'][:16] if m.get('verified_at') else 'unverified'
                self.stdout.write(f'{folder.name}  {size:8.1f} MB  {m.get("row_counts", {}).get("accounts_participantprofile", "?"):>5} participants  {verified}')
            except (OSError, ValueError):
                self.stdout.write(f'{folder.name}  (manifest unreadable)')

    # ------------------------------------------------------------------ take
    def _take(self, root, keep, with_files):
        root.mkdir(parents=True, exist_ok=True)
        stamp = timezone.now().strftime('%Y%m%d-%H%M%S')
        folder = root / stamp
        folder.mkdir()
        started = time.monotonic()
        db = _db()
        self.stdout.write(f'Backing up {db["NAME"]} -> {folder}')

        dump = folder / 'db.dump'
        _run([pg_tool('pg_dump'), *_conn_args(db['NAME']), '-Fc', '--no-owner', '--no-privileges', '-f', str(dump)])
        self.stdout.write(f'  database: {dump.stat().st_size / 1024 ** 2:.1f} MB')

        stores = {}
        if with_files:
            for name, locate in FILE_STORES.items():
                src = locate()
                if not src.exists():
                    stores[name] = {'present': False}
                    continue
                shutil.copytree(src, folder / name, dirs_exist_ok=True)
                stores[name] = {'present': True, 'bytes': _dir_size(folder / name)}
                self.stdout.write(f'  {name}: {stores[name]["bytes"] / 1024 ** 2:.1f} MB')

        manifest = {
            'taken_at': timezone.now().isoformat(),
            'database': db['NAME'],
            'row_counts': _row_counts(),
            'file_stores': stores,
            'dump_bytes': dump.stat().st_size,
            'total_bytes': _dir_size(folder),
            'seconds': round(time.monotonic() - started, 1),
            'study_manifest': self._study_manifest(),
        }
        (folder / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'Done in {manifest["seconds"]}s: {manifest["total_bytes"] / 1024 ** 2:.1f} MB, '
            f'{manifest["row_counts"].get("accounts_participantprofile")} participant rows'))

        if keep:
            for old in self._backups(root)[:-keep]:
                shutil.rmtree(old, ignore_errors=True)
                self.stdout.write(f'  pruned {old.name}')
        return str(folder)

    def _study_manifest(self):
        try:
            from assessment import manifest
            return manifest.build()
        except Exception as e:  # never let the study manifest stop a backup
            return {'error': f'study manifest unavailable: {e}'}

    # ------------------------------------------------------------------ verify
    def _verify(self, root, which):
        backups = self._backups(root)
        if which == 'latest':
            if not backups:
                raise CommandError(f'No backups in {root}')
            folder = backups[-1]
        else:
            folder = Path(which)
            if not folder.is_absolute():
                folder = root / folder
            if not (folder / 'manifest.json').exists():
                raise CommandError(f'{folder} is not a backup folder')
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        scratch = f'{_db()["NAME"]}_verify_{timezone.now().strftime("%H%M%S")}'
        self.stdout.write(f'Restoring {folder.name} into scratch database {scratch}')
        _run([pg_tool('createdb'), *_conn_args('postgres')[:-2], scratch])
        try:
            _run([pg_tool('pg_restore'), *_conn_args(scratch), '--no-owner', '--no-privileges', str(folder / 'db.dump')])
            import psycopg
            db = _db()
            with psycopg.connect(host=db.get('HOST') or 'localhost', port=int(db.get('PORT') or 5432),
                                 user=db.get('USER') or 'postgres', password=db.get('PASSWORD') or '',
                                 dbname=scratch) as conn:
                with conn.cursor() as cur:
                    restored = _row_counts(cur)
        finally:
            try:
                _run([pg_tool('dropdb'), *_conn_args('postgres')[:-2], scratch])
            except CommandError as e:
                self.stderr.write(f'scratch database {scratch} was not dropped: {e}')
        expected = manifest.get('row_counts', {})
        mismatches = {t: (expected.get(t), restored.get(t)) for t in COUNTED_TABLES if expected.get(t) != restored.get(t)}
        for table in COUNTED_TABLES:
            mark = 'OK ' if table not in mismatches else '!! '
            self.stdout.write(f'  {mark}{table:36s} taken={expected.get(table)!s:>6} restored={restored.get(table)!s:>6}')
        if mismatches:
            raise CommandError(f'{len(mismatches)} table(s) differ from the manifest - this backup is not trustworthy')
        manifest['verified_at'] = timezone.now().isoformat()
        (folder / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'{folder.name} restores cleanly: every counted table matches'))
