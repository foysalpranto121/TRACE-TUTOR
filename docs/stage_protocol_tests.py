"""Remote staging and disposable-schema tests; injected PAYLOAD contains reviewed files."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4
from dotenv import dotenv_values

root = Path('/srv/trace-tutor')
stage = Path('/tmp') / ('trace-protocol-20261025-' + uuid4().hex[:12])
stage.mkdir(mode=0o700)
source = stage / 'backend'
for current, dirs, files in os.walk(root / 'backend'):
    dirs[:] = [d for d in dirs if d not in {'.venv', '__pycache__', 'media', 'logs', 'data', 'chroma', 'rag_store', 'ocr', '.cache', 'node_modules'}]
    for name in files:
        if Path(name).suffix not in {'.py', '.json'}:
            continue
        original = Path(current) / name
        destination = source / original.relative_to(root / 'backend')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination)
baseline = {}
for relative, encoded in PAYLOAD['files'].items():
    original = root / relative
    baseline[relative] = hashlib.sha256(original.read_bytes()).hexdigest() if original.exists() else None
    destination = stage / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(base64.b64decode(encoded))
(stage / 'baseline.json').write_text(json.dumps(baseline))
schema = 'trace_protocol_qa_' + uuid4().hex[:12]
(source / 'trace_backend/protocol_schema_settings.py').write_text(
    'from .qa_settings import *\n'
    'import os\n'
    'from pathlib import Path\n'
    "DATABASES['default']['NAME'] = os.environ['DB_NAME']\n"
    f"DATABASES['default']['OPTIONS']['options'] = '-c search_path={schema}'\n"
    f"PROTOCOL_QA_SCHEMA = '{schema}'\n"
    "TEST_RUNNER = 'trace_backend.protocol_schema_runner.ProtocolSchemaRunner'\n"
)
env = dict(os.environ)
env.update({k: v for k, v in dotenv_values(root / 'backend/.env').items() if v is not None})
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
env['PYTHONUNBUFFERED'] = '1'
env['DJANGO_SETTINGS_MODULE'] = 'trace_backend.protocol_schema_settings'
print('PROTOCOL_STAGE', str(stage), flush=True)
labels = PAYLOAD.get('test_labels', ['assessment.tests.test_timing'])
command = [str(root / 'venv/bin/python'), 'manage.py', 'test', *labels,
           '--settings=trace_backend.protocol_schema_settings', '--noinput', '--verbosity=1']
result = subprocess.run(command, cwd=source, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(stage / 'tests.log').write_text(result.stdout)
print(result.stdout[-5000:], flush=True)
print('PROTOCOL_TEST_RESULT', json.dumps({'stage': str(stage), 'exit_code': result.returncode}), flush=True)
