"""Freeze current application sources and QA files; never includes secrets/data."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
candidate = out / 'candidate'
assert not candidate.exists(), 'Candidate already frozen; do not silently replace it'
paths = []
for directory in ['backend', 'frontend/src', 'frontend/public', 'frontend/tests']:
    for file in (root / directory).rglob('*'):
        if not file.is_file():
            continue
        rel = file.relative_to(root)
        if any(part in {'__pycache__', 'media', 'staticfiles', 'backups', '.cache', 'node_modules'} for part in rel.parts):
            continue
        if directory == 'backend' and file.suffix not in {'.py', '.json', '.txt', '.Dockerfile'}:
            continue
        if file.name.startswith('.env') or file.name.endswith('.log'):
            continue
        paths.append(rel)
for name in ['package.json', 'package-lock.json', 'index.html', 'vite.config.js', 'vitest.config.js', 'eslint.config.js', 'tailwind.config.js', 'postcss.config.js']:
    paths.append(Path('frontend') / name)
manifest = {}
for rel in sorted(set(paths)):
    source = root / rel
    assert source.is_file(), str(rel)
    destination = candidate / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    manifest[rel.as_posix()] = hashlib.sha256(destination.read_bytes()).hexdigest()
encoded = json.dumps(manifest, sort_keys=True, indent=2)
(out / 'candidate-manifest.json').write_text(encoded, encoding='utf-8')
identity = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
            'source_sha256': hashlib.sha256(encoded.encode()).hexdigest(), 'files': len(manifest),
            'source': 'current combined uncommitted working tree', 'production_files': 'explicit reviewed subset only'}
(out / 'candidate-identity.json').write_text(json.dumps(identity, indent=2), encoding='utf-8')
print(json.dumps(identity, indent=2))
