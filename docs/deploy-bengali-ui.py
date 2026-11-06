from pathlib import Path
from datetime import datetime, timezone
import json, shutil, subprocess, os
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-bengali-ui')
backup = root / 'deployment-backups' / ('bengali-ui-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
changes = json.loads((bundle / 'bengali-ui-changes.json').read_text())
prepared = {}
for rel, replacements in changes.items():
    content = (root / rel).read_text()
    for old, new in replacements:
        if old not in content:
            raise RuntimeError(f'Original text not found: {rel}: {old[:80]}')
    for old, new in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        content = content.replace(old, new)
    prepared[rel] = content
backup.mkdir(parents=True)
for rel in prepared:
    destination = backup / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / rel, destination)
shutil.copytree(root / 'frontend/dist', backup / 'dist')
print(f'Rollback backup: {backup}', flush=True)
try:
    for rel, content in prepared.items():
        (root / rel).write_text(content)
    fonts = root / 'frontend/public/fonts'
    fonts.mkdir(exist_ok=True)
    for name in ['noto-sans-bengali-regular.ttf', 'OFL-NotoSansBengali.txt']:
        shutil.copy2(bundle / name, fonts / name)
    buildroot = backup / 'build-workspace'
    shutil.copytree(root / 'frontend', buildroot, ignore=shutil.ignore_patterns('node_modules', 'dist', '.git'))
    subprocess.run(['npm', 'ci', '--include=optional', '--no-audit', '--no-fund'], cwd=buildroot, check=True)
    sources = [rel.removeprefix('frontend/') for rel in changes if rel.endswith(('.jsx', '.js'))]
    subprocess.run(['node', 'node_modules/eslint/bin/eslint.js', *sources], cwd=buildroot, check=True)
    stage = backup / 'new-dist'
    subprocess.run(['node', 'node_modules/vite/bin/vite.js', 'build', '--outDir', str(stage)], cwd=buildroot, check=True)
except Exception:
    for rel in prepared:
        shutil.copy2(backup / rel, root / rel)
    raise
for path in stage.rglob('*'):
    if path.is_file() and path.name != 'index.html':
        destination = root / 'frontend/dist' / path.relative_to(stage)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
entry = root / 'frontend/dist/index.html.next'
shutil.copy2(stage / 'index.html', entry)
entry.replace(root / 'frontend/dist/index.html')
env = dict(os.environ)
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
subprocess.run(['pm2', 'restart', 'trace-tutor', '--update-env'], env=env, check=True)
subprocess.run(['pm2', 'save'], env=env, check=True)
print('Bengali UI and username changes deployed.', flush=True)
