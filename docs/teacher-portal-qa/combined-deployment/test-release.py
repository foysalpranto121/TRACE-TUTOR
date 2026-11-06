"""Run staged regressions in a private, unprivileged PostgreSQL 16 cluster."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import shutil
import sys
import secrets
import subprocess
import tempfile
from unittest.mock import patch

root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-combined-20261009')
verify_backup = len(sys.argv) > 2 and sys.argv[2] == '--verify-backup'
stage = Path(sys.argv[1]) / ('backend-backup-verification' if verify_backup else 'backend-test-workspace-r2')
shutil.copytree(bundle / 'candidate/backend', stage, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copy2(root / 'backend/trace_backend/settings.py', stage / 'trace_backend/settings.py')
live_process = json.loads(subprocess.check_output(['pm2', 'jlist'], env=dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))))
live_process = next(p for p in live_process if p['name'] == 'trace-tutor')
live_env = dict(x.split('=', 1) for x in Path('/proc/' + str(live_process['pid']) + '/environ').read_text().split('\0') if '=' in x)
os.environ['PATH'] = live_env['PATH']
from dotenv import load_dotenv
load_dotenv(root / 'backend/.env')
load_dotenv(root / '.env')
production = {key: os.environ.get(key, default) for key, default in
              [('DB_HOST', 'localhost'), ('DB_PORT', '5432'),
               ('DB_NAME', 'trace_tutor_db'), ('DB_USER', 'postgres')]}
pgbin = Path('/usr/lib/postgresql/16/bin')
assert os.getuid() != 0, 'Private cluster must run as the unprivileged deployment user'
assert all((pgbin / name).is_file() for name in ['initdb', 'pg_ctl']), 'PostgreSQL 16 binaries missing'
try:
    import psycopg2 as pg
    from psycopg2 import sql
except ImportError:
    import psycopg as pg
    from psycopg import sql

with tempfile.TemporaryDirectory(prefix='trace-release-pg-') as private:
    private = Path(private).resolve()
    assert private.parent == Path('/tmp') and private.name.startswith('trace-release-pg-')
    assert private.stat().st_uid == os.getuid() and private.stat().st_mode & 0o077 == 0
    data, socket = private / 'data', private / 'socket'
    socket.mkdir(mode=0o700)
    admin_password, test_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    pwfile = private / 'init-password'
    pwfile.write_text(admin_password + '\n')
    pwfile.chmod(0o600)
    subprocess.run([str(pgbin / 'initdb'), '-D', str(data), '--username=trace_release_admin',
                    '--auth-local=scram-sha-256', '--auth-host=reject', '--encoding=UTF8',
                    '--no-locale', '--pwfile=' + str(pwfile)], check=True, stdout=subprocess.DEVNULL)
    pwfile.unlink()
    with (data / 'postgresql.conf').open('a') as config:
        config.write("\nlisten_addresses = ''\nport = 15432\nunix_socket_directories = '" + str(socket) + "'\n")
    started = False
    try:
        subprocess.run([str(pgbin / 'pg_ctl'), '-D', str(data), '-l', str(private / 'postgres.log'), '-w', 'start'], check=True)
        started = True
        assert str(socket) != production['DB_HOST'] and str(data).startswith(str(private) + '/')
        admin = pg.connect(host=str(socket), port=15432, dbname='postgres', user='trace_release_admin', password=admin_password)
        admin.autocommit = True
        try:
            with admin.cursor() as cursor:
                cursor.execute('SHOW data_directory')
                assert Path(cursor.fetchone()[0]).resolve() == data, 'Provisioning connection is not the private cluster'
                cursor.execute(sql.SQL('CREATE ROLE trace_release_test LOGIN NOSUPERUSER CREATEDB NOCREATEROLE PASSWORD {}').format(sql.Literal(test_password)))
                cursor.execute('CREATE DATABASE trace_release_base OWNER trace_release_test')
        finally:
            admin.close()
        os.environ.update(DB_HOST=str(socket), DB_PORT='15432', DB_NAME='trace_release_base',
                          DB_USER='trace_release_test', DB_PASSWORD=test_password,
                          OPENAI_API_KEY='', GEMINI_API_KEY='', GOOGLE_API_KEY='')
        os.environ['AGENT_API_KEY'] = ''
        os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
        sys.path.insert(0, str(stage))
        sys.argv.append('test')
        os.chdir(stage)
        from django.conf import settings
        resolved = settings.DATABASES['default']
        assert resolved['ENGINE'] == 'django.db.backends.postgresql'
        assert resolved['HOST'] == str(socket) and str(resolved['PORT']) == '15432'
        assert resolved['NAME'] == 'trace_release_base' and resolved['USER'] == 'trace_release_test'
        assert resolved['HOST'] != production['DB_HOST'] and resolved['NAME'] != production['DB_NAME']
        assert resolved['USER'] != production['DB_USER'], 'Test credentials must differ from production'
        resolved['TEST'] = {'NAME': 'test_trace_release_regression'}
        assert resolved['TEST']['NAME'] != production['DB_NAME']
        settings.CACHES = {name: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'combined-release-' + name} for name in ['default', 'persistent']}
        settings.QA_ARTIFACTS = stage / 'qa-artifacts'
        settings.MEDIA_ROOT = settings.QA_ARTIFACTS / 'media'
        settings.BACKUP_DIR = settings.QA_ARTIFACTS / 'backups'
        settings.TEST_RUNNER = 'trace_backend.qa_runner.TeacherQARunner'
        settings.DATABASES['default']['CONN_MAX_AGE'] = 0
        settings.LOGGING['handlers'].pop('file', None)
        for config in settings.LOGGING['loggers'].values():
            config['handlers'] = [name for name in config.get('handlers', []) if name != 'file']
        import django
        django.setup()
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user, inet_server_addr()')
            assert cursor.fetchone() == ('trace_release_base', 'trace_release_test', None)
        connection.close()
        print('PASS test isolation: private PostgreSQL 16 cluster, dedicated test role, socket-only connection', flush=True)
        from django.core.management import call_command
        call_command('check')
        if verify_backup:
            folder = Path(sys.argv[3]).resolve()
            assert folder.is_relative_to(Path(sys.argv[1]).resolve()), 'Backup escaped release directory'
            manifest = json.loads((folder / 'manifest.json').read_text())
            restore_env = dict(os.environ, PGPASSWORD=test_password)
            subprocess.run([str(pgbin / 'pg_restore'), '-h', str(socket), '-p', '15432',
                            '-U', 'trace_release_test', '-d', 'trace_release_base',
                            '--no-owner', '--no-privileges', '--exit-on-error', str(folder / 'db.dump')],
                           env=restore_env, check=True)
            with connection.cursor() as cursor:
                for table, expected in manifest['row_counts'].items():
                    assert table in {'accounts_participantprofile', 'assessment_examsubmission',
                                     'assessment_papersitting', 'assessment_expertrating',
                                     'logging_app_interactionlog', 'curriculum_curriculumpassage',
                                     'curriculum_ingestrun', 'curriculum_ocrpage'}
                    cursor.execute('SELECT count(*) FROM ' + connection.ops.quote_name(table))
                    assert expected is not None and cursor.fetchone()[0] == expected, 'Backup row count mismatch: ' + table
            connection.close()
            manifest['verified_at'] = datetime.now(timezone.utc).isoformat()
            manifest['verified_in'] = 'private disposable PostgreSQL 16 cluster'
            (folder / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
            print('PASS production dump restored in private cluster; all manifest row counts match', flush=True)
        else:
            with patch('httpx.Client.send', side_effect=RuntimeError('External model HTTP disabled for release tests')), patch('httpx.AsyncClient.send', side_effect=RuntimeError('External model HTTP disabled for release tests')):
                call_command('test', 'tutor.test_model_metadata', 'tutor.tests.LlmProviderTests',
                             'tutor.tests.ModelConfigTests', 'logging_app.test_tutor_availability',
                             'logging_app.tests', 'assessment.tests.test_sittings.SittingLifecycleTests',
                             'tutor.test_hint_policy', 'curriculum.tests.CorpusAccessTests',
                             'assessment.tests.test_access.ExamPaperAccessTests',
                             'assessment.tests.test_access.EndpointPermissionTests',
                             'assessment.tests.test_teacher_portal', 'logging_app.test_dashboard_scores',
                             'tutor.test_code_api.RealCodeApiTests.test_valid_c_uses_real_stdin_and_stdout',
                             'tutor.test_code_api.RealCodeApiTests.test_compile_error_has_diagnostics',
                             'tutor.test_code_api.RealCodeApiTests.test_nonzero_program_exit_is_a_runtime_error',
                             'tutor.test_code_api.RealCodeApiTests.test_malformed_requests_return_validation_errors',
                             'tutor.test_code_api.RealCodeApiTests.test_anonymous_code_execution_is_denied',
                             'tutor.test_sandbox.KillTreeTests.test_it_kills_the_childs_own_group_when_that_is_not_ours',
                             'tutor.test_sandbox.KillTreeTests.test_it_never_signals_the_web_servers_own_process_group',
                             'tutor.test_sandbox.RlimitTests.test_a_limit_the_platform_rejects_does_not_break_the_run',
                             'tutor.test_sandbox.RlimitTests.test_the_limit_set_covers_memory_cpu_processes_and_file_size',
                             interactive=False, verbosity=2)
    finally:
        if started:
            subprocess.run([str(pgbin / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'], check=True)
        print('Private test cluster stopped; temporary credentials/data removed on exit', flush=True)
