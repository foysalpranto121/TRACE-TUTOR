from pathlib import Path
from datetime import datetime, timezone
import shutil
import os
import json
import subprocess

root = Path('/srv/trace-tutor/frontend')
backup = Path('/srv/trace-tutor/deployment-backups') / ('assessment-phase-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
changes = json.loads(Path('/tmp/trace-assessment-phase-changes.json').read_text(encoding='utf-8-sig'))
prepared = {}
for rel, replacements in changes.items():
    path = root / rel
    content = path.read_bytes().replace(bytes([13,10]), bytes([10]))
    for old, new in replacements:
        if content.count(old.encode()) != 1:
            raise RuntimeError(f'Expected exactly one original layout match: {rel}: {old}')
        content = content.replace(old.encode(), new.encode(), 1)
    prepared[rel] = content
backup.mkdir(parents=True)
for rel, content in prepared.items():
    target = backup / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / rel, target)
    (root / rel).write_bytes(content)
shutil.copytree(root / 'dist', backup / 'dist')
print(f'Rollback backup: {backup}', flush=True)
try:
    buildroot = backup / 'build-workspace'
    shutil.copytree(root, buildroot, ignore=shutil.ignore_patterns('node_modules', 'dist', '.git'))
    subprocess.run(['npm', 'ci', '--include=optional', '--no-audit', '--no-fund'], cwd=buildroot, check=True)
    subprocess.run(['node', 'node_modules/eslint/bin/eslint.js', *changes], cwd=buildroot, check=True)
    stage = backup / 'new-dist'
    subprocess.run(['node', 'node_modules/vite/bin/vite.js', 'build', '--outDir', str(stage)], cwd=buildroot, check=True)
except Exception:
    for rel in changes:
        shutil.copy2(backup / rel, root / rel)
    raise
# Retain old hashed assets for existing tabs; publish the entry point last.
for path in stage.rglob('*'):
    if path.is_file() and path.name != 'index.html':
        destination = root / 'dist' / path.relative_to(stage)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
entry = root / 'dist' / 'index.html.next'
shutil.copy2(stage / 'index.html', entry)
entry.replace(root / 'dist' / 'index.html')
restart_env = dict(os.environ)
restart_env['PATH'] = '/home/shihab/bin:' + restart_env.get('PATH', '')
subprocess.run(['pm2', 'restart', 'trace-tutor', '--update-env'], env=restart_env, check=True)
subprocess.run(['pm2', 'save'], env=restart_env, check=True)
print('Assessment phase refresh deployed successfully.', flush=True)
