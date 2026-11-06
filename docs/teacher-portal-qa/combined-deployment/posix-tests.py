"""Run only unchanged mock-based POSIX tests, with no Docker socket or database."""
import sys
from django.conf import settings
settings.configure(SECRET_KEY='isolated-posix-tests', CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=False,
                   INSTALLED_APPS=[], DATABASES={}, USE_TZ=True)
import django
django.setup()
from django.test.runner import DiscoverRunner
labels = [
    'tutor.test_sandbox.KillTreeTests.test_it_kills_the_childs_own_group_when_that_is_not_ours',
    'tutor.test_sandbox.KillTreeTests.test_it_never_signals_the_web_servers_own_process_group',
    'tutor.test_sandbox.RlimitTests.test_a_limit_the_platform_rejects_does_not_break_the_run',
    'tutor.test_sandbox.RlimitTests.test_the_limit_set_covers_memory_cpu_processes_and_file_size',
]
sys.exit(bool(DiscoverRunner(verbosity=2).run_tests(labels)))
