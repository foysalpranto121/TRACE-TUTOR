from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

root = Path('/srv/trace-tutor')
bundle = Path('/tmp/trace-tutor-header-search-release')
files = json.loads((bundle / 'release.json').read_text())
assert len(files) == 5
for rel, digest in json.loads((bundle / 'dependencies.json').read_text()).items():
    assert hashlib.sha256((root / rel).read_text().encode()).hexdigest() == digest, 'Undeployed/mismatched dependency: ' + rel
print('PASS all 15 required dependencies already deployed; no dependency or backend release needed')
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
print('Confirmed PM2 target:', json.dumps({key: process['pm2_env'].get(key) for key in ['pm_cwd', 'pm_exec_path', 'exec_interpreter', 'status']}))
error_log = Path(process['pm2_env']['pm_err_log_path'])
(bundle / 'log-baseline.json').write_text(json.dumps({'path': str(error_log), 'offset': error_log.stat().st_size if error_log.exists() else 0}))
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
