"""Package only the reviewed practice metric changes; no environment or data files."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
paths = subprocess.check_output(['git', 'diff', '--name-only'], cwd=ROOT, text=True).splitlines()
paths += [
    'backend/tutor/practice.py', 'backend/tutor/practice_tasks.json',
    'backend/tutor/test_practice.py', 'frontend/tests/practice-catalog.test.mjs',
    'frontend/tests/practice-editor.test.jsx', 'frontend/tests/practice-progress.test.js',
]
release = {}
for rel in paths:
    assert rel == 'README.md' or rel.startswith(('backend/', 'frontend/')), rel
    previous = subprocess.run(['git', 'show', 'HEAD:' + rel], cwd=ROOT, capture_output=True)
    before = previous.stdout.replace(b'\r\n', b'\n') if previous.returncode == 0 else None
    after = (ROOT / rel).read_bytes().replace(b'\r\n', b'\n')
    release[rel] = {
        'before': hashlib.sha256(before).hexdigest() if before is not None else None,
        'after': hashlib.sha256(after).hexdigest(),
        'content': base64.b64encode(after).decode(),
    }
(OUT / 'release.json').write_text(json.dumps(release), encoding='utf-8')
print('Packaged', len(release), 'reviewed files')
