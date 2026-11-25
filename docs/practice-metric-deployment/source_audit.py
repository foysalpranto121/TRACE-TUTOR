import base64, hashlib, json, os, subprocess
from pathlib import Path

root = Path('/srv/trace-tutor')
stage = Path('/tmp/trace-practice-metric-v2-20261123')
release = json.loads((stage / 'release.json').read_text())
conflicts = []
for rel, entry in release.items():
    p = root / rel
    content = p.read_bytes().replace(b'\r\n', b'\n') if p.exists() else None
    actual = hashlib.sha256(content).hexdigest() if content is not None else None
    state = 'baseline' if actual == entry['before'] else ('already-current' if actual == entry['after'] else 'CONFLICT')
    print(rel, state)
    if state == 'CONFLICT':
        conflicts.append({'path': rel, 'content': base64.b64encode(content).decode() if content is not None else None})
(stage / 'conflicts.json').write_text(json.dumps(conflicts))
env = dict(os.environ, PATH='/home/shihab/bin:' + os.environ.get('PATH', ''))
processes = json.loads(subprocess.check_output(['pm2', 'jlist'], env=env))
print('Runtime:', json.dumps([{'name': p['name'], 'status': p['pm2_env']['status'], 'cwd': p['pm2_env'].get('pm_cwd')} for p in processes]))
print('Conflicts:', len(conflicts))
