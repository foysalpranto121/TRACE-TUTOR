"""Build a release from the server's current frontend plus the tested changes."""
import base64
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/srv/trace-tutor')
STAGE = Path('/tmp/trace-protocol-20261025-ef85a79ae54c')
assert (STAGE / 'tests.log').read_text().rstrip().endswith('OK')
baseline = json.loads((STAGE / 'baseline.json').read_text())
backend_files = [p for p in PAYLOAD['files'] if p.startswith('backend/')]
frontend = STAGE / 'frontend'
frontend.mkdir(exist_ok=True)
for current, dirs, files in os.walk(ROOT / 'frontend'):
    dirs[:] = [name for name in dirs if name not in {'node_modules', 'dist', '.git', '.cache'}]
    for name in files:
        src = Path(current) / name
        dst = frontend / src.relative_to(ROOT / 'frontend')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
manifest = {}
for relative, encoded in PAYLOAD['files'].items():
    src = ROOT / relative
    old = src.read_bytes() if src.exists() else None
    data = base64.b64decode(encoded)
    if relative in backend_files:
        assert baseline[relative] == (hashlib.sha256(old).hexdigest() if old is not None else None), 'Live source changed since testing'
        assert (STAGE / relative).read_bytes() == data, 'Backend candidate differs from tested source'
    dst = STAGE / relative
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    manifest[relative] = {'before':hashlib.sha256(old).hexdigest() if old is not None else None,
                          'after':hashlib.sha256(data).hexdigest()}
    if relative.startswith('frontend/') and old:
        diff = ''.join(difflib.unified_diff(old.decode().splitlines(True), data.decode('utf-8-sig').splitlines(True),
                                         fromfile=relative, tofile=relative+' (candidate)'))
        (STAGE / (Path(relative).name+'.diff')).write_text(diff)
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH',''))
modules = frontend / 'node_modules'
if modules.is_symlink():
    modules.unlink()
if not (modules/'@rollup/rollup-linux-x64-gnu').exists():
    installed = subprocess.run(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],
        cwd=frontend,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (STAGE/'frontend-install.log').write_text(installed.stdout)
    assert installed.returncode == 0, installed.stdout[-1500:]
result = subprocess.run(['node',str(frontend/'node_modules/vite/bin/vite.js'),'build'],cwd=frontend,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(STAGE / 'frontend-build.log').write_text(result.stdout)
print(result.stdout[-1500:])
assert result.returncode == 0
(STAGE / 'release.json').write_text(json.dumps(manifest,indent=2))
print('PROTOCOL_RELEASE_PREPARED',json.dumps({'stage':str(STAGE),'source_files':list(manifest)}),flush=True)
