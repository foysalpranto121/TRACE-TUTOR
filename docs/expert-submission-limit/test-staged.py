"""Test the focused queue fix against disposable PostgreSQL, never the study DB."""
from pathlib import Path
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile

ROOT = Path('/srv/trace-tutor')
BUNDLE = Path(__file__).resolve().parent
OLD = ".order_by('-submitted_at')[:100])"
NEW = ".order_by('-submitted_at', '-pk'))"
source = ROOT / 'backend/assessment/views.py'
original = source.read_bytes()
text = original.decode()
assert text.count(OLD) == 1
candidate = text.replace(OLD, NEW).replace(
    'Real ExamSubmission rows for expert grading - students are named by participant_code.',
    'All submissions for expert grading, labelled by participant_code.', 1).encode()
(BUNDLE / 'views.py.candidate').write_bytes(candidate)
manifest = {'original_sha256': hashlib.sha256(original).hexdigest(),
            'candidate_sha256': hashlib.sha256(candidate).hexdigest()}
assert os.getuid() != 0
pgbin = Path('/usr/lib/postgresql/16/bin')

with tempfile.TemporaryDirectory(prefix='trace-queue-test-') as folder:
    private = Path(folder)
    stage = private / 'backend'
    shutil.copytree(ROOT / 'backend', stage, ignore=shutil.ignore_patterns(
        '.env', '.venv', 'venv', 'media', 'staticfiles', '__pycache__', '*.pyc',
        '*.sqlite3*', 'logs', 'chroma_store', 'data', '.cache'))
    (stage / 'assessment/views.py').write_bytes(candidate)
    shutil.copy2(BUNDLE / 'test_teacher_portal.py', stage / 'teacher_queue_regression.py')
    shutil.copy2(BUNDLE / 'test_utils.py', stage / 'trace_backend/test_utils.py')
    data, socket = private / 'pgdata', private / 'socket'
    socket.mkdir(mode=0o700)
    password = secrets.token_urlsafe(32)
    password_file = private / 'password'
    password_file.write_text(password + '\n')
    password_file.chmod(0o600)
    subprocess.run([str(pgbin / 'initdb'), '-D', str(data), '--username=queue_test_admin',
                    '--auth-local=scram-sha-256', '--auth-host=reject', '--encoding=UTF8',
                    '--no-locale', '--pwfile=' + str(password_file)],
                   check=True, stdout=subprocess.DEVNULL)
    password_file.unlink()
    with (data / 'postgresql.conf').open('a') as config:
        config.write("\nlisten_addresses = ''\nport = 15432\nunix_socket_directories = '" + str(socket) + "'\n")
    started = False
    try:
        subprocess.run([str(pgbin / 'pg_ctl'), '-D', str(data), '-l', str(private / 'postgres.log'),
                        '-w', 'start'], check=True)
        started = True
        import psycopg2
        from psycopg2 import sql
        admin = psycopg2.connect(host=str(socket), port=15432, dbname='postgres',
                                 user='queue_test_admin', password=password)
        admin.autocommit = True
        test_password = secrets.token_urlsafe(32)
        with admin.cursor() as cursor:
            cursor.execute('SHOW data_directory')
            assert Path(cursor.fetchone()[0]) == data
            cursor.execute(sql.SQL('CREATE ROLE queue_test LOGIN NOSUPERUSER CREATEDB PASSWORD {}')
                           .format(sql.Literal(test_password)))
            cursor.execute('CREATE DATABASE queue_test_base OWNER queue_test')
        admin.close()
        os.environ.update(DB_HOST=str(socket), DB_PORT='15432', DB_NAME='queue_test_base',
                          DB_USER='queue_test', DB_PASSWORD=test_password, DEBUG='1', HTTPS_ONLY='0',
                          OPENAI_API_KEY='', GEMINI_API_KEY='', GOOGLE_API_KEY='', LOG_FILE='',
                          DJANGO_SETTINGS_MODULE='trace_backend.settings')
        sys.path.insert(0, str(stage))
        os.chdir(stage)
        sys.argv.append('test')
        from django.conf import settings
        assert settings.DATABASES['default']['HOST'] == str(socket)
        assert settings.DATABASES['default']['NAME'] == 'queue_test_base'
        settings.DATABASES['default']['TEST'] = {'NAME': 'test_queue_regression'}
        settings.CACHES = {name: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                                  'LOCATION': 'queue-' + name} for name in ('default', 'persistent')}
        settings.MEDIA_ROOT = private / 'media'
        settings.BACKUP_DIR = private / 'backups'
        import django
        django.setup()
        from django.core.management import call_command
        call_command('test', 'teacher_queue_regression', interactive=False, verbosity=1)
        manifest['tests'] = 'PASS: teacher portal suite, including 105 submissions and tied timestamps'
        (BUNDLE / 'tested-manifest.json').write_text(json.dumps(manifest, indent=2))
    finally:
        if started:
            subprocess.run([str(pgbin / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'], check=True)
print(json.dumps(manifest), flush=True)
