import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from django.conf import settings
settings.configure(DEBUG=False,
    CODE_SANDBOX_WORKDIR_ROOT=os.environ['CODE_SANDBOX_WORKDIR_ROOT'],
    CODE_SANDBOX_HOST_WORKDIR_ROOT=os.environ['CODE_SANDBOX_HOST_WORKDIR_ROOT'])
from tutor import sandbox
os.umask(0o077)
path = Path(tempfile.mkdtemp(prefix='trace_original_', dir=settings.CODE_SANDBOX_WORKDIR_ROOT))
try:
    (path / 'probe.txt').write_text('ok')
    result = subprocess.run(sandbox._docker_command(['cat', 'probe.txt'], path, 'run', False),
                            capture_output=True, text=True, timeout=60)
    print('Original root-owned 0700 workdir:', result.returncode, result.stderr.strip(), flush=True)
    assert result.returncode != 0 and 'Permission denied' in result.stderr
finally:
    shutil.rmtree(path)
print('Fixed shared workdir probe:', sandbox._docker_usable(), flush=True)
assert sandbox._docker_usable() == (True, None)
settings.CODE_SANDBOX_HOST_WORKDIR_ROOT = '/trace-verification-path-does-not-exist'
ok, reason = sandbox._docker_usable()
print('Incorrect host mapping fails closed:', ok, reason, flush=True)
assert not ok and 'bind source path does not exist' in reason
