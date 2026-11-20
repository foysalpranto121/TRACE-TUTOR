"""Read-only deployment diagnostics; pipe to the deployment's python3 over SSH."""
from pathlib import Path
import subprocess


pid = subprocess.check_output(['pm2', 'pid', 'trace-tutor'], text=True).strip()
env = dict(entry.split('=', 1) for entry in
           Path(f'/proc/{pid}/environ').read_text().split('\0') if '=' in entry)
print('Backend PID:', pid, flush=True)
print('Backend PATH:', env.get('PATH'), flush=True)
for key, value in sorted(env.items()):
    if key.startswith('CODE_SANDBOX'):
        print(f'{key}={value}', flush=True)
wrapper = Path('/home/shihab/bin/docker')
print('Restricted wrapper exists:', wrapper.exists(), flush=True)
if wrapper.exists():
    print(wrapper.read_text(), flush=True)
subprocess.run(['sudo', '-n', '-l'], check=False)
subprocess.run(['docker', 'image', 'inspect', 'trace-tutor-runner:1'],
               env=env, check=False)
for line in Path('/srv/trace-tutor/backend/.env').read_text().splitlines():
    if line.strip().startswith('CODE_SANDBOX'):
        print('Backend .env:', line, flush=True)
subprocess.run([
    '/srv/trace-tutor/venv/bin/python', 'manage.py', 'shell', '-c',
    'from tutor import sandbox; print(sandbox.status())',
], cwd='/srv/trace-tutor/backend', env=env, check=False)
