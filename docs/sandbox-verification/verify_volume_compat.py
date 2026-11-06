"""Exercise the runner's explicit --volume compatibility against real Docker."""
import os
from pathlib import Path
import runpy
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
with tempfile.TemporaryDirectory(prefix='trace_shared_verify_') as root:
    os.environ['CODE_SANDBOX_WORKDIR_ROOT'] = root
    os.environ['CODE_SANDBOX_HOST_WORKDIR_ROOT'] = root
    os.environ['CODE_SANDBOX_MOUNT_STYLE'] = 'volume'
    os.environ['VERIFY_LEGACY_SETTINGS'] = '1'
    runpy.run_path(str(Path(__file__).with_name('verify.py')), run_name='__main__')
