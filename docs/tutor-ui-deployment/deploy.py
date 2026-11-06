from pathlib import Path
from datetime import datetime, timezone
import json, shutil, subprocess, os, time
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-ui-release')
files = json.loads((bundle / 'release.json').read_text())
backup = root / 'deployment-backups' / ('tutor-availability-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
for rel, entry in files.items():
    path = root / rel
    if entry['expected'] is None:
        if path.exists():
            raise RuntimeError('Unexpected existing file: ' + rel)
    elif not path.exists() or path.read_text() != entry['expected']:
        raise RuntimeError('Server source changed since review: ' + rel)
backup.mkdir(parents=True)
print('Rollback backup: ' + str(backup), flush=True)
buildroot = backup / 'build-workspace'
shutil.copytree(root / 'frontend', buildroot, ignore=shutil.ignore_patterns('node_modules', 'dist', '.git'))
for rel, entry in files.items():
    if rel.startswith('frontend/'):
        path = buildroot / rel.removeprefix('frontend/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry['content'])
subprocess.run(['npm', 'ci', '--include=optional', '--no-audit', '--no-fund'], cwd=buildroot, check=True)
for command in [['npm', 'test'], ['npm', 'run', 'lint']]:
    subprocess.run(command, cwd=buildroot, check=True)
stage = backup / 'new-dist'
subprocess.run(['node', 'node_modules/vite/bin/vite.js', 'build', '--outDir', str(stage)], cwd=buildroot, check=True)
for rel, entry in files.items():
    if entry['expected'] is not None:
        path = backup / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, path)
shutil.copytree(root / 'frontend/dist', backup / 'dist')
env = dict(os.environ)
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
def restart():
    subprocess.run(['pm2', 'restart', 'trace-tutor', '--update-env'], env=env, check=True)
def health():
    last_error = None
    for _ in range(5):
        try:
            with urlopen('https://trace.musfiqurtuhin.me/api/health/', timeout=10) as response:
                assert json.loads(response.read())['database'] == 'ok'
            return
        except Exception as error:
            last_error = error
            time.sleep(1)
    raise last_error
try:
    for rel, entry in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry['content'])
    subprocess.run([str(root / 'venv/bin/python'), 'manage.py', 'check'], cwd=root / 'backend', check=True)
    restart()
    health()
    # Publish new assets first; retain old hashed assets for existing tabs.
    for path in stage.rglob('*'):
        if path.is_file() and path.name != 'index.html':
            destination = root / 'frontend/dist' / path.relative_to(stage)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    entry = root / 'frontend/dist/index.html.next'
    shutil.copy2(stage / 'index.html', entry)
    entry.replace(root / 'frontend/dist/index.html')
    restart()
    health()
    subprocess.run(['pm2', 'save'], env=env, check=True)
except Exception:
    for rel, entry in files.items():
        path = root / rel
        if entry['expected'] is not None:
            shutil.copy2(backup / rel, path)
        elif path.exists():
            path.unlink()
    shutil.copy2(backup / 'dist/index.html', root / 'frontend/dist/index.html')
    restart()
    raise
print('DEPLOYED: tutor availability and draft preservation.', flush=True)
