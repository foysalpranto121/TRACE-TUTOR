from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil, subprocess, os, time
from urllib.request import urlopen
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-model-release')
files = json.loads((bundle / 'release.json').read_text())
backup = root / 'deployment-backups' / ('tutor-model-labels-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
for rel, entry in files.items():
    path = root / rel
    if entry['expected'] is None:
        if path.exists():
            raise RuntimeError('Unexpected existing file: ' + rel)
    elif not path.exists() or path.read_text() != entry['expected']:
        raise RuntimeError('Server source changed since review: ' + rel)
backup.mkdir(parents=True)
print('Release staging/backup directory: ' + str(backup), flush=True)
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
subprocess.run([str(root / 'venv/bin/python'), str(bundle / 'test-release.py'), str(backup)], check=True)
for rel, entry in files.items():
    if entry['expected'] is not None:
        assert (root / rel).read_text() == entry['expected'], 'Production source changed during staging: ' + rel
        path = backup / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, path)
        assert path.read_bytes() == (root / rel).read_bytes(), 'Source backup differs: ' + rel
shutil.copytree(root / 'frontend/dist', backup / 'dist')
for original in (root / 'frontend/dist').rglob('*'):
    if original.is_file():
        saved = backup / 'dist' / original.relative_to(root / 'frontend/dist')
        assert hashlib.sha256(saved.read_bytes()).digest() == hashlib.sha256(original.read_bytes()).digest(), 'Frontend backup differs'
subprocess.run([str(root / 'venv/bin/python'), str(bundle / 'backup-release.py'), str(backup)], check=True)
env = dict(os.environ)
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
def restart():
    # Keep the existing PM2 environment; this release changes no configuration.
    subprocess.run(['pm2', 'restart', 'trace-tutor'], env=env, check=True)
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
    subprocess.run([str(root / 'venv/bin/python'), str(bundle / 'verify.py')], check=True)
    subprocess.run(['pm2', 'save'], env=env, check=True)
except Exception:
    for rel, entry in files.items():
        path = root / rel
        if entry['expected'] is not None:
            shutil.copy2(backup / rel, path)
        elif path.exists():
            path.unlink()
    # Restore original non-hashed files too, keeping the old entry point last.
    for original in (backup / 'dist').rglob('*'):
        if original.is_file() and original.name != 'index.html':
            destination = root / 'frontend/dist' / original.relative_to(backup / 'dist')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
    rollback_entry = root / 'frontend/dist/index.html.rollback'
    shutil.copy2(backup / 'dist/index.html', rollback_entry)
    rollback_entry.replace(root / 'frontend/dist/index.html')
    restart()
    health()
    print('ROLLED BACK: previous sources and frontend restored.', flush=True)
    raise
print('DEPLOYED: authoritative tutor model labels.', flush=True)
