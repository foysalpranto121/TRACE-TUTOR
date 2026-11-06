"""Read production frontend sources into a secret-free deployment baseline."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import tarfile
from urllib.request import urlopen

root = Path('/srv/trace-tutor')
stage = Path('/tmp/trace-expert-qa-20261026-a76f29')
frontend = root / 'frontend'
paths = []
for directory in ('src', 'tests', 'public'):
    if (frontend / directory).is_dir():
        paths.extend(p for p in (frontend / directory).rglob('*') if p.is_file() and not p.is_symlink())
for name in ('package.json', 'package-lock.json', 'index.html', 'vite.config.js', 'vitest.config.js', 'eslint.config.js', 'tailwind.config.js', 'postcss.config.js'):
    if (frontend / name).is_file():
        paths.append(frontend / name)
assert all(not p.name.startswith('.env') for p in paths)
hashes = {p.relative_to(frontend).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(stage / 'baseline-hashes.json').write_text(json.dumps(hashes, indent=2))
with tarfile.open(stage / 'baseline.tar.gz', 'w:gz') as archive:
    for path in paths:
        archive.add(path, arcname=path.relative_to(frontend).as_posix(), recursive=False)
    archive.add(stage / 'baseline-hashes.json', arcname='baseline-hashes.json')
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
processes = json.loads(subprocess.check_output(['pm2', 'jlist'], env=env))
print(json.dumps({'processes': [{'name': p['name'], 'status': p['pm2_env']['status'], 'cwd': p['pm2_env'].get('pm_cwd')} for p in processes], 'source_files': len(paths), 'node_modules': (frontend / 'node_modules').is_dir(), 'baseline': str(stage / 'baseline.tar.gz')}, indent=2))
with urlopen('https://trace.musfiqurtuhin.me/api/health/', timeout=20) as response:
    print('Health:', response.read().decode())
