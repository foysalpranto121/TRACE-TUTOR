import os
import subprocess
from pathlib import Path

pid = subprocess.check_output(['pm2', 'pid', 'trace-tutor'], text=True).strip()
env = dict(entry.split('=', 1) for entry in Path(f'/proc/{pid}/environ').read_text().split('\0') if '=' in entry)
assert env['PATH'].split(':')[0] == '/home/shihab/bin'
os.environ['PATH'] = env['PATH']
print('Running backend PATH uses the restricted Docker wrapper.')
from tutor import sandbox
from tutor.runner import run_code
status = sandbox.status()
assert status['tier'] == 'docker' and status['allowed'], status
result = run_code('c', '#include <stdio.h>\nint main(){int n,sum=0;scanf("%d",&n);for(int i=1;i<=n;i++)sum+=i;printf("%d\\n",sum);return 0;}', [{'input': '5', 'expected': '15'}])
print(result)
assert result['status'] == 'SUCCESS', result
assert result['test_results'][0]['actual'].strip() == '15', result
print('PASS: Docker C execution with deployed backend PATH returns 15.')
