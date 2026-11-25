"""Build and test a candidate without loading production credentials or databases."""
import base64, hashlib, json, os, secrets, shutil, subprocess
from pathlib import Path

ROOT = Path('/srv/trace-tutor')
STAGE = Path('/tmp/trace-practice-metric-v2-20261123')
CANDIDATE = STAGE / 'candidate'
release = json.loads((STAGE / 'release.json').read_text())
if not CANDIDATE.exists():
    CANDIDATE.mkdir()
    for name in ('backend', 'frontend'):
        shutil.copytree(ROOT / name, CANDIDATE / name, ignore=shutil.ignore_patterns(
            '.env', '.env.*', '.git', 'node_modules', 'dist', '.venv', 'venv', '__pycache__',
            'media', 'logs', '*.log', '*.sqlite3', 'chroma_db', 'ocr_cache', '.cache'))
for rel, entry in release.items():
    target = ROOT / rel
    actual = hashlib.sha256(target.read_bytes().replace(b'\r\n', b'\n')).hexdigest() if target.exists() else None
    assert actual == entry['before'], 'Production source changed: ' + rel
    target = CANDIDATE / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    content = base64.b64decode(entry['content'])
    assert hashlib.sha256(content).hexdigest() == entry['after']
    target.write_bytes(content)
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
modules = CANDIDATE / 'frontend/node_modules'
if modules.is_symlink():
    modules.unlink()
for filename in ('package.json', 'package-lock.json', 'vitest.config.js', 'eslint.config.js'):
    shutil.copy2(STAGE / filename, CANDIDATE / 'frontend' / filename)
subprocess.run(['npm', 'ci', '--include=dev', '--include=optional', '--no-audit', '--no-fund'], cwd=CANDIDATE / 'frontend', env=env, check=True)
for command in (['npm', 'test'], ['npm', 'run', 'lint'], ['npm', 'run', 'build']):
    subprocess.run(command, cwd=CANDIDATE / 'frontend', env=env, check=True)

pg = Path('/usr/lib/postgresql/16/bin')
cluster = STAGE / 'test-postgres'
socket = STAGE / 'test-socket'
socket.mkdir(mode=0o700)
subprocess.run([str(pg / 'initdb'), '-D', str(cluster), '--auth-local=trust', '--auth-host=reject', '-U', 'trace_practice_qa'], check=True, stdout=subprocess.DEVNULL)
subprocess.run([str(pg / 'pg_ctl'), '-D', str(cluster), '-l', str(STAGE / 'test-postgres.log'), '-o', "-h '' -k " + str(socket) + ' -p 55439', '-w', 'start'], check=True)
try:
    env.update(DEBUG='1', SECRET_KEY=secrets.token_hex(32), HTTPS_ONLY='0',
               DB_HOST=str(socket), DB_PORT='55439', DB_USER='trace_practice_qa', DB_PASSWORD='',
               DB_NAME='postgres', CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED='0',
               OPENAI_API_KEY='', GEMINI_API_KEY='', GOOGLE_API_KEY='', LOG_FILE='',
               GEMINI_TEMPERATURE='0', OPENAI_TEMPERATURE='0')
    (CANDIDATE / 'backend/trace_backend/practice_release_qa.py').write_text(
        "from .settings import *\n"
        "assert DATABASES['default']['HOST'] == " + repr(str(socket)) + "\n"
        "assert DATABASES['default']['USER'] == 'trace_practice_qa'\n"
        "DATABASES['default']['TEST'] = {'NAME': 'test_practice_release'}\n"
        "CACHES = {name: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'practice-release-' + name} for name in ('default', 'persistent')}\n")
    subprocess.run([str(ROOT / 'venv/bin/python'), 'manage.py', 'test',
                    'tutor.test_practice', 'tutor.tests', 'logging_app',
                    'assessment.tests.test_analytics', 'assessment.tests.test_access', 'tests.test_journey',
                    '--settings=trace_backend.practice_release_qa', '--noinput', '--verbosity=1'],
                   cwd=CANDIDATE / 'backend', env=env, check=True)
finally:
    subprocess.run([str(pg / 'pg_ctl'), '-D', str(cluster), '-m', 'fast', '-w', 'stop'], check=True)
(STAGE / 'STAGING_VERIFIED').write_text(json.dumps({'files': len(release), 'frontend': 'tests, lint, build passed', 'backend': 'isolated PostgreSQL tests passed'}))
print('STAGING_VERIFIED', flush=True)
