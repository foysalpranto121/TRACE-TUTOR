"""Containment for student-submitted code.

The behavioural tests (fork bombs, memory hogs, file writes, network access) only mean
something under a tier that can actually stop them, so they skip unless that tier is
active. The policy tests - "refuse to execute when containment is required but absent" -
run everywhere, because that is the check that keeps a deployment from silently
executing untrusted code with no protection at all.
"""
import os
import shutil
import stat
import tempfile
import textwrap
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from tutor import runner, sandbox

C_AVAILABLE = bool(runner._find_c_compiler())


def active_tier():
    sandbox.reset_detection()
    tier, _ = sandbox.detect()
    return tier


class TierDetectionTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        sandbox.reset_detection()
        self.addCleanup(sandbox.reset_detection)

    def test_detection_reports_one_of_the_known_tiers(self):
        tier, _ = sandbox.detect()
        self.assertIn(tier, sandbox.TIER_ORDER)

    @override_settings(CODE_SANDBOX='none')
    def test_an_explicit_tier_is_honoured(self):
        self.assertEqual(active_tier(), sandbox.NONE)

    @override_settings(CODE_SANDBOX='docker', CODE_SANDBOX_IMAGE='definitely-not-an-image:0')
    def test_an_unavailable_tier_degrades_and_says_why(self):
        sandbox.reset_detection()
        tier, reason = sandbox.detect()
        self.assertEqual(tier, sandbox.NONE)
        self.assertIn('docker', reason)

    def test_status_describes_the_tier_for_the_api(self):
        sandbox.reset_detection()
        box = sandbox.status()
        self.assertIn(box['tier'], sandbox.TIER_ORDER)
        self.assertEqual(box['isolated'], box['tier'] == sandbox.DOCKER)
        self.assertIsInstance(box['enforced'], bool)
        self.assertTrue(box['label'])

    def test_detection_is_cached_until_reset(self):
        with patch('tutor.sandbox._rlimit_usable', return_value=(True, None)) as check:
            sandbox.reset_detection()
            sandbox.detect()
            sandbox.detect()
            sandbox.detect()
        self.assertLessEqual(check.call_count, 1, 'detection should probe at most once')

    @override_settings(CODE_SANDBOX='auto')
    def test_auto_prefers_the_strongest_available_tier(self):
        with patch('tutor.sandbox._docker_usable', return_value=(True, None)):
            self.assertEqual(active_tier(), sandbox.DOCKER)
        with patch('tutor.sandbox._docker_usable', return_value=(False, 'nope')), \
             patch('tutor.sandbox._rlimit_usable', return_value=(True, None)):
            self.assertEqual(active_tier(), sandbox.RLIMIT)
        with patch('tutor.sandbox._docker_usable', return_value=(False, 'nope')), \
             patch('tutor.sandbox._rlimit_usable', return_value=(False, 'nope')):
            self.assertEqual(active_tier(), sandbox.NONE)


class PolicyTests(SimpleTestCase):
    """Fail closed: no containment plus a policy that requires it means no execution."""

    def setUp(self):
        super().setUp()
        sandbox.reset_detection()
        self.addCleanup(sandbox.reset_detection)

    @override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=True)
    def test_execution_is_refused_when_containment_is_required_but_absent(self):
        sandbox.reset_detection()
        with self.assertRaises(sandbox.SandboxUnavailable):
            sandbox.ensure_allowed()

    @override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=True)
    def test_run_code_returns_a_refusal_rather_than_executing(self):
        sandbox.reset_detection()
        with patch('tutor.sandbox.execute') as executed:
            result = runner.run_code(language='c', code='int main(){return 0;}')
        executed.assert_not_called()
        self.assertEqual(result['status'], 'SANDBOX_UNAVAILABLE')
        self.assertIn('disabled', result['compile_output'])

    @override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=False)
    def test_execution_is_allowed_when_the_risk_is_explicitly_accepted(self):
        sandbox.reset_detection()
        self.assertEqual(sandbox.ensure_allowed(), sandbox.NONE)

    @override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=True)
    def test_compiler_status_reports_that_execution_is_blocked(self):
        sandbox.reset_detection()
        status = runner.compiler_status()
        self.assertFalse(status['ready'])
        self.assertIn('disabled', status['hint'])
        self.assertEqual(status['sandbox']['tier'], sandbox.NONE)

    def test_html_checking_never_needs_the_sandbox(self):
        """HTML is parsed in-process by html5lib, so it stays available regardless."""
        with override_settings(CODE_SANDBOX='none', CODE_SANDBOX_REQUIRED=True):
            sandbox.reset_detection()
            result = runner.run_code(language='html', code='<p>hi</p>', mode='check')
        self.assertNotEqual(result['status'], 'SANDBOX_UNAVAILABLE')

    @override_settings(CODE_SANDBOX='rlimit', CODE_SANDBOX_REQUIRED=True)
    def test_rlimit_is_refused_when_a_container_is_required(self):
        """rlimit caps memory and processes but leaves the host filesystem and network in
        reach; when the policy requires docker it must not be silently accepted."""
        sandbox.reset_detection()
        with patch('tutor.sandbox._rlimit_usable', return_value=(True, None)):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.ensure_allowed()

    @override_settings(CODE_SANDBOX='rlimit', CODE_SANDBOX_REQUIRED=True, CODE_SANDBOX_MIN_TIER='rlimit')
    def test_rlimit_is_accepted_only_when_explicitly_opted_into(self):
        sandbox.reset_detection()
        with patch('tutor.sandbox._rlimit_usable', return_value=(True, None)):
            self.assertEqual(sandbox.ensure_allowed(), sandbox.RLIMIT)

    @override_settings(CODE_SANDBOX='rlimit', CODE_SANDBOX_REQUIRED=True)
    def test_run_code_refuses_the_rlimit_tier_and_names_the_gap(self):
        sandbox.reset_detection()
        with patch('tutor.sandbox._rlimit_usable', return_value=(True, None)), \
             patch('tutor.sandbox.execute') as executed:
            result = runner.run_code(language='c', code='int main(){return 0;}')
        executed.assert_not_called()
        self.assertEqual(result['status'], 'SANDBOX_UNAVAILABLE')

    @override_settings(CODE_SANDBOX='docker', CODE_SANDBOX_REQUIRED=True, CODE_SANDBOX_REPROBE_SECONDS=0)
    def test_a_blocked_tier_is_reprobed_so_a_late_docker_start_heals(self):
        """A Docker daemon still starting when the first request lands must not disable
        code execution for the life of the process."""
        sandbox.reset_detection()
        with patch('tutor.sandbox._docker_usable', return_value=(False, 'daemon starting')), \
             patch('tutor.sandbox.time.monotonic', return_value=100):
            self.assertEqual(sandbox.detect()[0], sandbox.NONE)
        with patch('tutor.sandbox._docker_usable', return_value=(True, None)), \
             patch('tutor.sandbox.time.monotonic', return_value=101):
            self.assertEqual(sandbox.detect()[0], sandbox.DOCKER, 're-probed, not the cached NONE')

    @override_settings(CODE_SANDBOX='docker', CODE_SANDBOX_REQUIRED=True)
    def test_compiler_status_is_blocked_when_only_rlimit_is_available(self):
        sandbox.reset_detection()
        with patch('tutor.sandbox._docker_usable', return_value=(False, 'no daemon')), \
             patch('tutor.sandbox._rlimit_usable', return_value=(True, None)):
            # Explicit docker was requested and is unavailable, so detect lands on NONE and
            # the status is blocked; the point is that "ready" never lies.
            status = runner.compiler_status()
        self.assertFalse(status['ready'])
        self.assertIn('disabled', status['hint'])


class KillTreeTests(SimpleTestCase):
    """A timed-out run must be stopped without ever signalling the web server itself."""

    def test_a_timed_out_docker_run_is_stopped_by_container_name(self):
        proc = Mock()
        proc.pid = 2 ** 30  # a pid that does not exist, so the fallback path is harmless
        with patch('tutor.sandbox._docker_kill') as docker_kill, \
             patch('tutor.sandbox.subprocess.run'):
            sandbox._kill_tree(proc, container='trace-run-abc')
        docker_kill.assert_called_once_with('trace-run-abc')

    @unittest.skipUnless(os.name == 'posix', 'process groups are POSIX')
    def test_it_never_signals_the_web_servers_own_process_group(self):
        proc = Mock()
        proc.pid = 2 ** 30
        with patch('os.getpgid', return_value=os.getpgrp()), \
             patch('os.killpg') as killpg:
            sandbox._kill_tree(proc)
        killpg.assert_not_called()
        proc.kill.assert_called_once()

    @unittest.skipUnless(os.name == 'posix', 'process groups are POSIX')
    def test_it_kills_the_childs_own_group_when_that_is_not_ours(self):
        proc = Mock()
        proc.pid = 2 ** 30
        with patch('os.getpgid', return_value=2 ** 29), \
             patch('os.getpgrp', return_value=1), \
             patch('os.killpg') as killpg:
            sandbox._kill_tree(proc)
        killpg.assert_called_once()
        proc.kill.assert_not_called()


@override_settings(CODE_SANDBOX_WORKDIR_ROOT='', CODE_SANDBOX_HOST_WORKDIR_ROOT='', CODE_SANDBOX_MOUNT_STYLE='bind')
class DockerCommandTests(SimpleTestCase):
    """The container flags are the containment, so assert on them directly."""

    def command(self, **kwargs):
        kwargs.setdefault('kind', 'run')
        kwargs.setdefault('writable', False)
        return sandbox._docker_command(['./main.out'], '/tmp/work', **kwargs)

    def test_the_container_has_no_network(self):
        argv = self.command()
        self.assertIn('--network', argv)
        self.assertEqual(argv[argv.index('--network') + 1], 'none')

    def test_memory_and_swap_are_both_capped(self):
        with override_settings(CODE_RUN_MEMORY_MB=128):
            argv = self.command()
        self.assertEqual(argv[argv.index('--memory') + 1], '128m')
        self.assertEqual(argv[argv.index('--memory-swap') + 1], '128m',
                         'an uncapped swap would defeat the memory limit')

    def test_process_count_is_capped_against_fork_bombs(self):
        with override_settings(CODE_RUN_MAX_PROCESSES=32):
            argv = self.command()
        self.assertEqual(argv[argv.index('--pids-limit') + 1], '32')

    def test_all_capabilities_are_dropped_and_privileges_cannot_be_regained(self):
        argv = self.command()
        self.assertEqual(argv[argv.index('--cap-drop') + 1], 'ALL')
        self.assertIn('no-new-privileges', argv)

    def test_the_run_step_mounts_the_workdir_read_only(self):
        argv = self.command()
        self.assertIn('--mount', argv)
        self.assertTrue(any(a.endswith('target=/work,readonly') for a in argv))
        self.assertNotIn('--volume', argv)
        self.assertIn('--read-only', argv)

    def test_the_compile_step_gets_a_writable_workdir(self):
        argv = self.command(kind='compile', writable=True)
        self.assertTrue(any(a.endswith('target=/work') for a in argv))
        self.assertNotIn('--read-only', argv)

    def test_compiling_gets_a_larger_memory_cap_than_running(self):
        compile_argv = self.command(kind='compile', writable=True)
        run_argv = self.command()
        as_mb = lambda argv: int(argv[argv.index('--memory') + 1].rstrip('m'))  # noqa: E731
        self.assertGreater(as_mb(compile_argv), as_mb(run_argv))

    def test_the_container_is_removed_after_the_run(self):
        self.assertIn('--rm', self.command())

    def test_a_named_container_can_be_killed_on_timeout(self):
        argv = sandbox._docker_command(['./main.out'], '/tmp/work', 'run', False, name='trace-run-xyz')
        self.assertIn('--name', argv)
        self.assertEqual(argv[argv.index('--name') + 1], 'trace-run-xyz')

    def test_cpu_time_backstop_is_applied_when_given(self):
        argv = sandbox._docker_command(['./main.out'], '/tmp/work', 'run', False,
                                       name='x', cpu_hardcap=48)
        ulimits = [argv[i + 1] for i, a in enumerate(argv) if a == '--ulimit']
        self.assertTrue(any(u.startswith('cpu=48') for u in ulimits),
                        'a container CPU-time ulimit stops an orphaned loop by itself')

    def test_the_configured_image_is_used(self):
        with override_settings(CODE_SANDBOX_IMAGE='my-runner:7'):
            self.assertIn('my-runner:7', self.command())

    def test_the_container_always_has_an_explicit_non_root_identity(self):
        argv = self.command()
        self.assertEqual(argv[argv.index('--user') + 1],
                         ':'.join(map(str, sandbox.docker_identity())))
        self.assertNotEqual(sandbox.docker_identity()[0], 0)


@override_settings(CODE_SANDBOX_WORKDIR_ROOT='', CODE_SANDBOX_HOST_WORKDIR_ROOT='', CODE_SANDBOX_MOUNT_STYLE='bind')
class WorkdirTests(SimpleTestCase):
    def test_volume_compatibility_preserves_read_only_and_writable_mounts(self):
        with tempfile.TemporaryDirectory() as root, \
             override_settings(CODE_SANDBOX_WORKDIR_ROOT=root,
                               CODE_SANDBOX_HOST_WORKDIR_ROOT=root,
                               CODE_SANDBOX_MOUNT_STYLE='volume'):
            path = sandbox.create_workdir()
            try:
                self.assertEqual(sandbox.docker_mount(path, False), ['--volume', f'{path.resolve()}:/work:ro'])
                self.assertEqual(sandbox.docker_mount(path, True), ['--volume', f'{path.resolve()}:/work'])
            finally:
                shutil.rmtree(path)

    @override_settings(CODE_SANDBOX_MOUNT_STYLE='volume')
    def test_volume_compatibility_requires_an_explicit_shared_root(self):
        with self.assertRaises(sandbox.SandboxUnavailable):
            sandbox.docker_mount('/tmp/work', False)

    def test_volume_compatibility_refuses_a_different_host_path(self):
        with tempfile.TemporaryDirectory() as root, \
             override_settings(CODE_SANDBOX_WORKDIR_ROOT=root,
                               CODE_SANDBOX_HOST_WORKDIR_ROOT=str(Path(root) / 'host'),
                               CODE_SANDBOX_MOUNT_STYLE='volume'):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.docker_mount(Path(root) / 'work', False)

    def test_volume_compatibility_refuses_a_missing_directory(self):
        with tempfile.TemporaryDirectory() as root, \
             override_settings(CODE_SANDBOX_WORKDIR_ROOT=root, CODE_SANDBOX_MOUNT_STYLE='volume'):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.docker_mount(Path(root) / 'missing', False)

    def test_a_non_root_backend_identity_is_preserved(self):
        with patch('tutor.sandbox.os.name', 'posix'), \
             patch('tutor.sandbox.os.geteuid', return_value=1001, create=True), \
             patch('tutor.sandbox.os.getegid', return_value=1002, create=True):
            self.assertEqual(sandbox.docker_identity(), (1001, 1002))

    def test_a_root_backend_uses_the_unprivileged_image_identity(self):
        with patch('tutor.sandbox.os.name', 'posix'), \
             patch('tutor.sandbox.os.geteuid', return_value=0, create=True):
            self.assertEqual(sandbox.docker_identity(), (65532, 65532))

    def test_workdirs_use_the_configured_shared_root_and_are_cleanable(self):
        with tempfile.TemporaryDirectory() as root, \
             override_settings(CODE_SANDBOX_WORKDIR_ROOT=root):
            path = sandbox.create_workdir()
            self.assertEqual(path.parent, Path(root))
            sandbox.write_workfile(path / 'main.c', 'int main(){return 0;}')
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE((path / 'main.c').stat().st_mode), 0o600)
                self.assertEqual(path.stat().st_uid, sandbox.docker_identity()[0])
                self.assertEqual((path / 'main.c').stat().st_uid, sandbox.docker_identity()[0])
            shutil.rmtree(path)
            self.assertFalse(path.exists())

    def test_host_mapping_preserves_the_private_directory_name(self):
        with tempfile.TemporaryDirectory() as root, \
             override_settings(CODE_SANDBOX_WORKDIR_ROOT=root,
                               CODE_SANDBOX_HOST_WORKDIR_ROOT=str(Path(root) / 'host')):
            path = Path(root) / 'trace_run_abc'
            self.assertEqual(sandbox.docker_workdir(path), str(Path(root) / 'host' / path.name))

    def test_host_mapping_refuses_a_directory_outside_the_shared_root(self):
        with tempfile.TemporaryDirectory() as root, \
             override_settings(CODE_SANDBOX_WORKDIR_ROOT=str(Path(root) / 'shared'),
                               CODE_SANDBOX_HOST_WORKDIR_ROOT=root):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.docker_workdir(Path(root) / 'unshared')

    def test_host_mapping_requires_the_backend_root(self):
        with override_settings(CODE_SANDBOX_WORKDIR_ROOT='',
                               CODE_SANDBOX_HOST_WORKDIR_ROOT='/host/shared'):
            with self.assertRaises(sandbox.SandboxUnavailable):
                sandbox.docker_workdir('/tmp/work')

    def test_probe_checks_reads_writes_and_backend_visibility(self):
        calls = []

        def docker_run(argv, **kwargs):
            calls.append(argv)
            if argv[1:3] == ['image', 'inspect']:
                return Mock(returncode=0)
            mount = argv[argv.index('--mount') + 1]
            source = mount.split('source=', 1)[1].split(',target=', 1)[0]
            path = Path(source)
            token = (path / 'probe.txt').read_text()
            if argv[-2:] == ['cat', 'probe.txt']:
                return Mock(returncode=0, stdout=token, stderr='')
            (path / 'written.txt').write_text(token)
            return Mock(returncode=0, stdout='', stderr='')

        with patch('tutor.sandbox.shutil.which', return_value='docker'), \
             patch('tutor.sandbox.subprocess.run', side_effect=docker_run):
            self.assertEqual(sandbox._docker_usable(), (True, None))
        self.assertEqual(len(calls), 3)

    def test_probe_rejects_a_readable_but_unwritable_mount(self):
        # Reuse the real workspace/token while simulating Docker's permission error.
        def docker_run(argv, **kwargs):
            if argv[1:3] == ['image', 'inspect']:
                return Mock(returncode=0)
            if argv[-2:] == ['cat', 'probe.txt']:
                mount = argv[argv.index('--mount') + 1]
                source = mount.split('source=', 1)[1].split(',target=', 1)[0]
                return Mock(returncode=0, stdout=(Path(source) / 'probe.txt').read_text(), stderr='')
            return Mock(returncode=1, stdout='', stderr='Permission denied')

        with patch('tutor.sandbox.shutil.which', return_value='docker'), \
             patch('tutor.sandbox.subprocess.run', side_effect=docker_run):
            ok, reason = sandbox._docker_usable()
        self.assertFalse(ok)
        self.assertIn('could not write', reason)


@unittest.skipUnless(active_tier() == sandbox.DOCKER, 'needs the docker tier')
class DockerSumTests(SimpleTestCase):
    def test_sum_of_first_five_natural_numbers(self):
        result = runner.run_code(language='c', code=textwrap.dedent('''\
            #include <stdio.h>
            int main() {
                int n, sum = 0;
                scanf("%d", &n);
                for (int i = 1; i <= n; i++) sum += i;
                printf("%d\\n", sum);
                return 0;
            }
        '''), test_cases=[{'input': '5', 'output': '15'}])
        self.assertEqual(result['sandbox'], sandbox.DOCKER)
        self.assertEqual(result['status'], 'SUCCESS', result)
        self.assertEqual(result['test_results'][0]['actual'], '15')
        self.assertEqual(result['test_results'][0]['exit_code'], 0)


@unittest.skipUnless(os.name == 'posix', 'rlimit caps are POSIX-only')
class RlimitTests(SimpleTestCase):
    def test_the_limit_set_covers_memory_cpu_processes_and_file_size(self):
        import resource
        applied = {}

        def record(res, pair):
            applied[res] = pair

        with patch('resource.setrlimit', side_effect=record), \
             patch('os.setsid'):
            sandbox._rlimit_preexec('run')()

        for res in (resource.RLIMIT_AS, resource.RLIMIT_CPU,
                    resource.RLIMIT_NPROC, resource.RLIMIT_FSIZE):
            self.assertIn(res, applied)
        self.assertEqual(applied[resource.RLIMIT_CORE], (0, 0))

    def test_a_limit_the_platform_rejects_does_not_break_the_run(self):
        with patch('resource.setrlimit', side_effect=OSError('unsupported')), \
             patch('os.setsid'):
            sandbox._rlimit_preexec('run')()  # must not raise


@unittest.skipUnless(C_AVAILABLE and active_tier() == sandbox.DOCKER,
                     'resource exhaustion tests require the isolated Docker tier')
class ResourceExhaustionTests(SimpleTestCase):
    """Programs that try to take the host down. These run under whatever tier is active;
    the assertions are about the platform surviving and reporting, not about the tier."""

    def setUp(self):
        super().setUp()
        sandbox.reset_detection()
        self.addCleanup(sandbox.reset_detection)

    def run_c(self, source, timeout_note=''):
        return runner.run_code(language='c', code=textwrap.dedent(source),
                               test_cases=[{'input': '', 'output': 'never'}])

    def test_an_infinite_loop_is_stopped_and_reported(self):
        result = self.run_c('int main(){ while(1){} return 0; }')
        self.assertEqual(result['status'], 'RUNTIME_ERROR')
        self.assertTrue(result['test_results'][0]['timed_out'])
        self.assertIn('Time limit exceeded', result['test_results'][0]['stderr'])

    def test_a_program_blocked_on_input_does_not_hang_the_request(self):
        result = self.run_c("""
            #include <stdio.h>
            int main(){ int x; while(scanf("%d",&x)==1){} while(1){} return 0; }
        """)
        self.assertTrue(result['test_results'][0]['timed_out'])

    def test_a_runaway_allocation_does_not_take_the_host_down(self):
        result = self.run_c("""
            #include <stdlib.h>
            #include <string.h>
            int main(){
                while(1){ void *p = malloc(64*1024*1024); if(!p) return 1; memset(p,1,1024); }
                return 0;
            }
        """)
        # Either the allocation fails (capped) or the wall clock stops it; what must not
        # happen is the request never returning.
        self.assertIn(result['status'], ('RUNTIME_ERROR', 'WRONG_ANSWER'))

    @unittest.skipUnless(active_tier() != sandbox.NONE, 'needs a containment tier')
    def test_a_fork_bomb_is_contained(self):
        result = self.run_c("""
            #include <unistd.h>
            int main(){ while(1){ fork(); } return 0; }
        """)
        self.assertIn(result['status'], ('RUNTIME_ERROR', 'WRONG_ANSWER'))


@unittest.skipUnless(active_tier() == sandbox.DOCKER, 'needs the docker tier')
class ContainerIsolationTests(SimpleTestCase):
    """What only a container can actually guarantee."""

    def run_c(self, source):
        return runner.run_code(language='c', code=textwrap.dedent(source),
                               test_cases=[{'input': '', 'output': ''}])

    def test_the_program_cannot_reach_the_network(self):
        result = self.run_c("""
            #include <stdio.h>
            #include <sys/socket.h>
            #include <netinet/in.h>
            #include <arpa/inet.h>
            int main(){
                int s = socket(AF_INET, SOCK_STREAM, 0);
                struct sockaddr_in a = {0};
                a.sin_family = AF_INET; a.sin_port = htons(80);
                inet_pton(AF_INET, "1.1.1.1", &a.sin_addr);
                printf("%s\\n", connect(s,(struct sockaddr*)&a,sizeof a)==0 ? "REACHED" : "BLOCKED");
                return 0;
            }
        """)
        self.assertNotIn('REACHED', result['test_results'][0]['actual'])

    def test_the_program_cannot_write_outside_its_workdir(self):
        result = self.run_c("""
            #include <stdio.h>
            int main(){
                FILE *f = fopen("/etc/trace-tutor-escape", "w");
                printf("%s\\n", f ? "WROTE" : "DENIED");
                if (f) fclose(f);
                return 0;
            }
        """)
        self.assertIn('DENIED', result['test_results'][0]['actual'])

    def test_the_program_cannot_overwrite_its_own_source_tree(self):
        result = self.run_c("""
            #include <stdio.h>
            int main(){
                FILE *f = fopen("main.c", "w");
                printf("%s\\n", f ? "WROTE" : "DENIED");
                if (f) fclose(f);
                return 0;
            }
        """)
        self.assertIn('DENIED', result['test_results'][0]['actual'],
                      'the workdir is mounted read-only for the run step')

    def test_the_program_does_not_run_as_root(self):
        result = self.run_c("""
            #include <stdio.h>
            #include <unistd.h>
            int main(){ printf("%d\\n", (int)getuid()); return 0; }
        """)
        self.assertNotEqual(result['test_results'][0]['actual'].strip(), '0')
