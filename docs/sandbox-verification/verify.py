import json
import os
import sys
import unittest

from django.conf import settings

settings.configure(
    DEBUG=False, SECRET_KEY='isolated-sandbox-test-only', INSTALLED_APPS=[],
    DATABASES={}, CODE_SANDBOX='docker', CODE_SANDBOX_REQUIRED=True,
    CODE_SANDBOX_MIN_TIER='docker',
    CODE_SANDBOX_WORKDIR_ROOT=os.environ.get('CODE_SANDBOX_WORKDIR_ROOT', ''),
    CODE_SANDBOX_HOST_WORKDIR_ROOT=os.environ.get('CODE_SANDBOX_HOST_WORKDIR_ROOT', ''),
)
if os.environ.get('VERIFY_LEGACY_SETTINGS') == '1':
    del settings.CODE_SANDBOX_WORKDIR_ROOT
    del settings.CODE_SANDBOX_HOST_WORKDIR_ROOT
import django
django.setup()
from tutor import sandbox, runner

if os.name == 'posix':
    os.umask(0o077)
print('Django:', django.get_version(), flush=True)
print('Runner identity:', sandbox.docker_identity(), flush=True)
print('Sandbox:', json.dumps(sandbox.status()), flush=True)
assert sandbox.ensure_allowed() == sandbox.DOCKER
source = '''#include <stdio.h>
int main() {
    int n, sum = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) sum += i;
    printf("%d\\n", sum);
    return 0;
}
'''
result = runner.run_code('c', source, [{'input': '5', 'output': '15'}])
print('C program:', json.dumps(result), flush=True)
assert result['status'] == 'SUCCESS', result
assert result['test_results'][0]['actual'] == '15', result
suite = unittest.defaultTestLoader.loadTestsFromNames(sys.argv[1:] or ['tutor.test_sandbox'])
outcome = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if outcome.wasSuccessful() else 1)
