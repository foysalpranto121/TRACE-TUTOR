from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-model-release')
files = json.loads((bundle / 'release.json').read_text())
assert len(files) == 11
for rel, entry in files.items():
    path = root / rel
    assert (not path.exists()) if entry['expected'] is None else (path.exists() and path.read_text() == entry['expected']), 'Production baseline mismatch: ' + rel
    print('PASS production baseline:', rel)
env = dict(os.environ)
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
processes = json.loads(subprocess.check_output(['pm2', 'jlist'], env=env))
process = next(p for p in processes if p['name'] == 'trace-tutor')
assert process['pm2_env']['status'] == 'online'
assert process['pm2_env']['pm_cwd'].startswith(str(root))
fingerprints = {}
for rel in ['.env', 'backend/.env']:
    path = root / rel
    if path.exists():
        fingerprints[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
assert fingerprints, 'Expected environment file missing'
fingerprints['pm2_environment'] = hashlib.sha256(json.dumps(process['pm2_env'].get('env', {}), sort_keys=True).encode()).hexdigest()
(bundle / 'environment-fingerprints.json').write_text(json.dumps(fingerprints))
sys.path.insert(0, str(root / 'backend'))
os.chdir(root / 'backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'trace_backend.settings')
import django
django.setup()
from trace_backend import llm
print('PASS production process online; environment fingerprints saved without revealing values')
print('Confirmed configuration:', json.dumps({'provider': llm.provider(), 'primary_model': llm.model_name(), 'fallback_chain': llm.model_chain(), 'configured': llm.configured()}))
