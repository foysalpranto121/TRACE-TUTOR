"""Build and validate against production sources without modifying the live app."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tarfile

root = Path('/srv/trace-tutor/frontend')
stage = Path('/tmp/trace-expert-qa-20261026-a76f29')
with tarfile.open(stage / 'release.tar.gz') as archive:
    archive.extractall(stage / 'candidate', filter='data')
candidate = stage / 'candidate'
baseline = json.loads((candidate / 'baseline-hashes.json').read_text())
manifest = json.loads((candidate / 'release.json').read_text())
for rel, digest in baseline.items():
    assert hashlib.sha256((root / rel).read_bytes()).hexdigest() == digest, 'Production changed: ' + rel
for rel, entry in manifest.items():
    assert hashlib.sha256((candidate / 'runtime' / rel).read_bytes()).hexdigest() == entry['after']
    assert (hashlib.sha256((root / rel).read_bytes()).hexdigest() if (root / rel).exists() else None) == entry['before']
build = stage / 'build'
assert not build.exists(), 'Build staging already exists'
shutil.copytree(root, build, ignore=shutil.ignore_patterns('node_modules', 'dist', '.git', '.env*'))
for rel in manifest:
    target = build / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate / 'runtime' / rel, target)
(build / 'tests').mkdir(exist_ok=True)
for source in (candidate / 'validation-tests').iterdir():
    shutil.copy2(source, build / 'tests' / source.name)
for command in (
    ['npm', 'ci', '--include=optional', '--no-audit', '--no-fund'],
    ['npm', 'test'],
    ['npm', 'run', 'lint'],
    ['npm', 'run', 'build'],
):
    print('RUN:', ' '.join(command), flush=True)
    subprocess.run(command, cwd=build, check=True)
assert (build / 'dist/index.html').is_file()
(stage / 'STAGED.json').write_text(json.dumps({'runtime': manifest, 'baseline': baseline}, indent=2))
print('STAGED: tests, lint and build passed against production frontend plus four fixes.', flush=True)
