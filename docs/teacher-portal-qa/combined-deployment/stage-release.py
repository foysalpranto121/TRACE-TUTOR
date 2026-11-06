from pathlib import Path
import base64, hashlib, json, os, subprocess, tarfile
root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-combined-20261009')
backup = root / 'deployment-backups/combined-teacher-docker-20261009T175621Z'
assert (backup / 'BACKUP_VERIFIED').is_file()
saved = json.loads((backup / 'backup-manifest.json').read_text())
for rel, digest in saved['files'].items():
    assert hashlib.sha256((backup / rel).read_bytes()).hexdigest() == digest, 'Backup altered: ' + rel
release = json.loads((bundle / 'release.json').read_text())
for rel, entry in release.items():
    p = root / rel
    assert (hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None) == entry['expected_sha256'], 'Source changed: ' + rel
    assert hashlib.sha256(base64.b64decode(entry['base64'])).hexdigest() == entry['sha256']
for rel, digest in json.loads((bundle / 'dependencies.json').read_text()).items():
    p = root / rel
    assert p.is_file(), 'Required dependency missing: ' + rel
    data = p.read_bytes()
    if p.suffix in {'.py', '.js', '.jsx', '.json', '.txt', '.css', '.mjs', '.html'}:
        data = data.replace(b'\r\n', b'\n')
    assert hashlib.sha256(data).hexdigest() == digest, 'Unreviewed dependency difference: ' + rel
candidate = bundle / 'candidate'
assert not candidate.exists()
candidate.mkdir(mode=0o700)
manifest = json.loads((bundle / 'candidate-manifest.json').read_text())
with tarfile.open(bundle / 'candidate.tar.gz') as archive:
    members = archive.getmembers()
    assert {m.name for m in members} == set(manifest)
    assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
    archive.extractall(candidate, members=members, filter='data')
for rel, digest in manifest.items():
    assert hashlib.sha256((candidate / rel).read_bytes()).hexdigest() == digest
print('PASS exact frozen candidate, production baseline and unchanged runtime dependencies', flush=True)
frontend = candidate / 'frontend'
subprocess.run(['npm', 'ci', '--include=optional', '--no-audit', '--no-fund'], cwd=frontend, check=True)
for command in [['npm', 'test'], ['npm', 'run', 'lint']]:
    subprocess.run(command, cwd=frontend, check=True)
subprocess.run(['node', 'node_modules/vite/bin/vite.js', 'build', '--outDir', str(backup / 'new-dist')], cwd=frontend, check=True)
subprocess.run([str(root / 'venv/bin/python'), str(bundle / 'test-release.py'), str(backup)], check=True)
subprocess.run([str(root / 'venv/bin/python'), 'manage.py', 'showmigrations', '--plan'], cwd=root / 'backend', check=True)
(backup / 'STAGING_VERIFIED').write_text((bundle / 'candidate-identity.json').read_text())
print('PASS combined staging complete; no production application files changed', flush=True)
