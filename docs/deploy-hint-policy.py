from pathlib import Path
import shutil
import subprocess
import os
from datetime import datetime, timezone

root = Path('/srv/trace-tutor/backend')
path = root / 'tutor/views.py'
source = path.read_text()
changes = [
    ('from . import runner\n', 'from . import runner\nfrom .hint_policy import HINT_INSTRUCTION, is_hint_request, hint_response\n'),
    ("    prompt = (data.get('prompt') or '').strip()\n", "    prompt = (data.get('prompt') or '').strip()\n    hint_only = is_hint_request(prompt)\n"),
    ("            parsed, model = llm.generate_json(SYSTEM_INSTRUCTION.replace('{lang_name}', _lang_name(language)),", "            instruction = SYSTEM_INSTRUCTION.replace('{lang_name}', _lang_name(language))\n            if hint_only:\n                instruction += '\\n\\n' + HINT_INSTRUCTION\n            parsed, model = llm.generate_json(instruction,"),
    ("cache_key('tutor-answer', 'v4',", "cache_key('tutor-answer', 'v5-hint-policy',"),
    ("    parsed, model, ai_status, error = result['parsed'], result['model'], result['ai_status'], result['error']\n", "    parsed, model, ai_status, error = result['parsed'], result['model'], result['ai_status'], result['error']\n    if hint_only:\n        parsed = hint_response(parsed, language)\n"),
]
for old, new in changes:
    assert source.count(old) == 1, old
    source = source.replace(old, new, 1)
backup = Path('/srv/trace-tutor/deployment-backups') / ('hint-policy-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
backup.mkdir(parents=True)
shutil.copy2(path, backup / 'views.py')
for name in ['hint_policy.py', 'test_hint_policy.py']:
    if (root / 'tutor' / name).exists():
        shutil.copy2(root / 'tutor' / name, backup / name)
    shutil.copy2(Path('/tmp') / name, root / 'tutor' / name)
path.write_text(source)
try:
    subprocess.run(['/srv/trace-tutor/venv/bin/python', '-m', 'unittest', 'tutor.test_hint_policy'], cwd=root, check=True)
    subprocess.run(['/srv/trace-tutor/venv/bin/python', 'manage.py', 'check'], cwd=root, check=True)
except Exception:
    shutil.copy2(backup / 'views.py', path)
    raise
env = dict(os.environ)
env['PATH'] = '/home/shihab/bin:' + env.get('PATH', '')
subprocess.run(['pm2', 'restart', 'trace-tutor', '--update-env'], env=env, check=True)
subprocess.run(['pm2', 'save'], env=env, check=True)
print('Hint policy deployed. Backup:', backup)
