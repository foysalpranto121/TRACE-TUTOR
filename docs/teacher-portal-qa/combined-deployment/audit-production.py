"""Read-only production audit; never prints environment values or credentials."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, shutil
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
assert root.is_dir()
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
processes = json.loads(subprocess.check_output(['pm2', 'jlist'], env=env))
matches = [p for p in processes if p['name'] == 'trace-tutor']
assert len(matches) == 1
p = matches[0]
assert p['pm2_env']['status'] == 'online'
assert Path(p['pm2_env']['pm_cwd']).resolve() == root / 'backend'
live_env = dict(x.split('=', 1) for x in Path('/proc/' + str(p['pid']) + '/environ').read_text().split('\0') if '=' in x)
os.environ['PATH'] = live_env['PATH']
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.settings'
import django
django.setup()
from django.conf import settings
from django.db import connection
from tutor import sandbox
from trace_backend import llm
with urlopen('https://trace.musfiqurtuhin.me/api/health/', timeout=15) as r:
    health = json.loads(r.read())
assert health['database'] == 'ok'
with connection.cursor() as c:
    c.execute('SELECT current_database(), current_user, version()')
    database = c.fetchone()
    c.execute('SELECT rolcreatedb, rolsuper FROM pg_roles WHERE rolname = current_user')
    privileges = c.fetchone()
connection.close()
files = {}
for folder in ['backend', 'frontend/src', 'frontend/public', 'frontend/tests']:
    for file in (root / folder).rglob('*'):
        if not file.is_file() or any(x in {'__pycache__', 'media', 'staticfiles', 'backups', '.cache', 'node_modules', 'chroma_store', 'data'} for x in file.relative_to(root).parts):
            continue
        if file.name.startswith('.env') or file.suffix in {'.log', '.pyc'}:
            continue
        if folder == 'backend' and file.suffix not in {'.py', '.json', '.txt', '.Dockerfile'}:
            continue
        files[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
for name in ['package.json', 'package-lock.json', 'index.html', 'vite.config.js', 'vitest.config.js', 'eslint.config.js', 'tailwind.config.js', 'postcss.config.js']:
    f = root / 'frontend' / name
    files['frontend/' + name] = hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None
result = {'target': 'shihab@89.167.59.65', 'root': str(root), 'health': health,
          'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
          'pm2': {k: p['pm2_env'].get(k) for k in ['pm_cwd', 'pm_exec_path', 'exec_interpreter', 'status']},
          'database': {'name': database[0], 'role': database[1], 'version': database[2], 'privileges': privileges},
          'sandbox': sandbox.status(), 'sandbox_mount': getattr(settings, 'CODE_SANDBOX_MOUNT_STYLE', os.environ.get('CODE_SANDBOX_MOUNT_STYLE', 'bind')),
          'provider': llm.public_metadata(), 'disk_free': shutil.disk_usage(root).free,
          'writable': os.access(root, os.W_OK), 'files': files,
          'sources': {rel: (root / rel).read_text() for rel in files if files[rel] is not None and Path(rel).suffix in {'.py', '.jsx', '.js', '.json', '.mjs', '.css', '.html', '.txt'}},
          'environment_hashes': {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest() for f in [root / '.env', root / 'backend/.env'] if f.exists()},
          'proxy_active': subprocess.run(['systemctl', 'is-active', 'nginx'], capture_output=True, text=True).stdout.strip()}
print(json.dumps(result, indent=2))
