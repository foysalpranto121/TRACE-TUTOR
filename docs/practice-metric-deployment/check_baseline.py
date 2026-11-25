"""Confirm the single platform-specific failure also occurs before this release."""
import base64, hashlib, json, os, subprocess
from pathlib import Path

ROOT = Path('/srv/trace-tutor')
STAGE = Path('/tmp/trace-practice-metric-v2-20261123')
candidate = STAGE / 'candidate'
release = json.loads((STAGE / 'release.json').read_text())
target = candidate / 'backend/tutor/runner.py'
tested = target.read_bytes()
before = (ROOT / 'backend/tutor/runner.py').read_bytes()
assert hashlib.sha256(before.replace(b'\r\n', b'\n')).hexdigest() == release['backend/tutor/runner.py']['before']
env = dict(os.environ, DEBUG='1', SECRET_KEY='isolated-staging-only', HTTPS_ONLY='0',
           OPENAI_API_KEY='', GEMINI_API_KEY='', GOOGLE_API_KEY='', LOG_FILE='',
           DB_HOST=str(STAGE / 'test-socket'), DB_USER='trace_practice_qa', DB_PORT='55439',
           CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED='0')
try:
    target.write_bytes(before)
    result = subprocess.run([str(ROOT / 'venv/bin/python'), 'manage.py', 'test',
                             'tutor.tests.DiagnosticFlagTests.test_a_windows_mingw_override_with_a_full_path',
                             '--settings=trace_backend.practice_release_qa', '--verbosity=2'],
                            cwd=candidate / 'backend', env=env, capture_output=True, text=True)
    output = result.stdout + result.stderr
    (STAGE / 'baseline-platform-test.log').write_text(output)
    assert result.returncode == 1 and 'FAILED (failures=1)' in output and 'fno-caret-diagnostics' in output, output
finally:
    target.write_bytes(tested)
assert hashlib.sha256(tested).hexdigest() == release['backend/tutor/runner.py']['after']
log = (STAGE / 'stage.log').read_text()
assert 'Ran 166 tests' in log and 'FAILED (failures=1)' in log
assert 'test_a_windows_mingw_override_with_a_full_path' in log
assert 'built in' in log
result = {'backend': '165 passed; 1 unchanged Windows path test fails on Linux in both baseline and candidate',
          'baseline_failure_confirmed': True, 'frontend': 'tests, lint, production build passed', 'files': len(release)}
(STAGE / 'STAGING_VERIFIED').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
for line in log.splitlines():
    if 'Test Files' in line or ('Tests ' in line and 'passed' in line) or 'tests ' in line or 'built in' in line:
        print(line)
