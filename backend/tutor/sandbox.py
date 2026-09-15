"""Containment for student-submitted code.

`POST /api/code/run/` compiles and executes whatever a participant typed. Authentication
stops strangers; it does not stop a logged-in participant from writing a fork bomb, a
`while(1)` allocation loop, an `fopen("../../db.sqlite3","w")`, or a socket to somewhere
outside. That is what this module is for.

Three tiers, in descending order of containment:

  docker  Full. Compile and execution both happen inside a throwaway container with no
          network, a memory cap, a process cap and a read-only root. Nothing the program
          does can reach the host.
  rlimit  Partial, POSIX only. The process runs on the host under setrlimit caps and in
          its own process group, so runaway memory, fork bombs and orphaned children are
          contained - but the filesystem and the network are NOT.
  none    No containment. Wall-clock timeout and a process-tree kill, nothing more.

`CODE_SANDBOX` selects a tier ('auto' picks the best available). `CODE_SANDBOX_REQUIRED`
- which defaults to "on whenever DEBUG is off" - refuses to execute at all when only the
'none' tier is available, so a deployment cannot silently end up running unprotected.

To enable the docker tier, build the runner image once:

    docker build -f backend/tutor/sandbox.Dockerfile -t trace-tutor-runner:1 backend/tutor
"""
import logging
import os
import platform
import shutil
import signal
import subprocess
import time

from django.conf import settings

logger = logging.getLogger(__name__)

DOCKER = 'docker'
RLIMIT = 'rlimit'
NONE = 'none'
TIER_ORDER = (DOCKER, RLIMIT, NONE)

TIER_LABELS = {
    DOCKER: 'docker (no network, memory and process caps, read-only root)',
    RLIMIT: 'rlimit (memory and process caps; filesystem and network NOT isolated)',
    NONE: 'none (timeout only - not suitable for untrusted code)',
}

_detected = {}


class SandboxUnavailable(RuntimeError):
    """Raised when policy requires containment that this host cannot provide."""


# --------------------------------------------------------------------------- config
def _conf(name, default):
    return getattr(settings, name, default)


def image_name():
    return _conf('CODE_SANDBOX_IMAGE', 'trace-tutor-runner:1')


def required():
    return _conf('CODE_SANDBOX_REQUIRED', not settings.DEBUG)


def limits(kind):
    """Resource caps. Compiling legitimately needs more room than running."""
    if kind == 'compile':
        return {
            'memory_mb': _conf('CODE_COMPILE_MEMORY_MB', 1024),
            'cpu_seconds': _conf('CODE_COMPILE_CPU_SECONDS', 60),
            'max_processes': _conf('CODE_COMPILE_MAX_PROCESSES', 128),
            'max_file_mb': _conf('CODE_COMPILE_MAX_FILE_MB', 64),
        }
    return {
        'memory_mb': _conf('CODE_RUN_MEMORY_MB', 256),
        'cpu_seconds': _conf('CODE_RUN_CPU_SECONDS', 5),
        'max_processes': _conf('CODE_RUN_MAX_PROCESSES', 64),
        'max_file_mb': _conf('CODE_RUN_MAX_FILE_MB', 4),
    }


# ------------------------------------------------------------------------ detection
def _docker_usable():
    """Docker counts as available only if it can actually run our image with a mount.

    Checking `docker --version` is not enough: the daemon may be stopped, the image may
    not be built, and on Windows the drive holding the temp directory may not be shared
    with the engine. So probe with the real thing once and cache the answer.
    """
    if not shutil.which('docker'):
        return False, 'docker executable not found'
    try:
        probe = subprocess.run(['docker', 'image', 'inspect', image_name()],
                               capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f'docker not responding: {exc}'
    if probe.returncode != 0:
        return False, (f'image {image_name()} is not built - see '
                       'backend/tutor/sandbox.Dockerfile')

    import tempfile
    from pathlib import Path
    probe_dir = Path(tempfile.mkdtemp(prefix='trace_probe_'))
    try:
        (probe_dir / 'probe.txt').write_text('ok', encoding='utf-8')
        result = subprocess.run(
            _docker_command(['cat', 'probe.txt'], probe_dir, 'run', writable=False),
            capture_output=True, text=True, timeout=60)
        if result.returncode != 0 or 'ok' not in (result.stdout or ''):
            return False, f'container could not read the mounted workdir: {(result.stderr or "").strip()[:200]}'
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f'probe container failed: {exc}'
    finally:
        shutil.rmtree(probe_dir, ignore_errors=True)
    return True, None


def _rlimit_usable():
    if os.name != 'posix':
        return False, 'setrlimit is POSIX-only (this host is %s)' % platform.system()
    try:
        import resource  # noqa: F401
    except ImportError:
        return False, 'the resource module is unavailable'
    return True, None


def detect(refresh=False):
    """(tier, reason) for the tier that will actually be used."""
    if _detected and not refresh:
        return _detected['tier'], _detected['reason']

    configured = str(_conf('CODE_SANDBOX', 'auto')).lower()
    checks = {DOCKER: _docker_usable, RLIMIT: _rlimit_usable, NONE: lambda: (True, None)}
    notes = {}

    if configured in TIER_ORDER:
        ok, why = checks[configured]()
        tier = configured if ok else NONE
        reason = None if ok else f'{configured} requested but unavailable: {why}'
    else:
        tier, reason = NONE, None
        for candidate in TIER_ORDER:
            ok, why = checks[candidate]()
            if ok:
                tier = candidate
                break
            notes[candidate] = why
        reason = '; '.join(f'{k}: {v}' for k, v in notes.items()) or None

    _detected.update(tier=tier, reason=reason)
    if tier == NONE:
        logger.warning('Code execution is running UNSANDBOXED. %s', reason or '')
    return tier, reason


def reset_detection():
    """Forget the cached tier. Detection probes Docker, so it is cached for the life of
    the process; call this after changing configuration (tests do)."""
    _detected.clear()


def status():
    tier, reason = detect()
    return {
        'tier': tier,
        'label': TIER_LABELS[tier],
        'isolated': tier == DOCKER,
        'enforced': required(),
        'detail': reason,
        'image': image_name() if tier == DOCKER else None,
    }


def ensure_allowed():
    """Refuse to execute unprotected when policy says containment is mandatory."""
    tier, reason = detect()
    if tier == NONE and required():
        raise SandboxUnavailable(
            'Code execution is disabled: no sandbox is available on this host '
            f'({reason or "no containment backend"}). Build the runner image, or set '
            'CODE_SANDBOX_REQUIRED=0 to accept the risk on a closed network.')
    return tier


# ----------------------------------------------------------------------- docker tier
def _docker_command(inner_argv, workdir, kind, writable):
    """A throwaway container: no network, capped memory and processes, all capabilities
    dropped, and the workdir mounted read-only unless the step has to write output."""
    caps = limits(kind)
    mount = f'{os.path.abspath(str(workdir))}:/work' + ('' if writable else ':ro')
    argv = [
        'docker', 'run', '--rm', '--interactive',
        '--network', 'none',                       # no outbound sockets, no LAN
        '--memory', f'{caps["memory_mb"]}m',
        '--memory-swap', f'{caps["memory_mb"]}m',  # no swap as an escape hatch
        '--pids-limit', str(caps['max_processes']),
        '--cpus', str(_conf('CODE_SANDBOX_CPUS', '1.0')),
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges',
        '--workdir', '/work',
        '--volume', mount,
    ]
    if not writable:
        argv += ['--read-only', '--tmpfs', '/tmp:rw,size=16m']
    argv += [image_name()]
    argv += list(inner_argv)
    return argv


# ----------------------------------------------------------------------- rlimit tier
def _rlimit_preexec(kind):
    caps = limits(kind)

    def apply():
        import resource
        os.setsid()  # own process group, so a timeout kills the whole tree
        mem = caps['memory_mb'] * 1024 * 1024
        for res, value in (
            (resource.RLIMIT_AS, mem),
            (resource.RLIMIT_DATA, mem),
            (resource.RLIMIT_CPU, caps['cpu_seconds']),
            (resource.RLIMIT_NPROC, caps['max_processes']),
            (resource.RLIMIT_FSIZE, caps['max_file_mb'] * 1024 * 1024),
            (resource.RLIMIT_CORE, 0),
        ):
            try:
                resource.setrlimit(res, (value, value))
            except (ValueError, OSError):
                pass  # a limit the platform will not accept must not break the run

    return apply


# ------------------------------------------------------------------------ execution
def _kill_tree(proc):
    """Kill the child AND everything it spawned; a fork bomb outlives a plain kill()."""
    try:
        if os.name == 'posix':
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                return
            except (ProcessLookupError, PermissionError, OSError):
                pass
        else:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, timeout=10)
            return
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def execute(host_argv, container_argv, workdir, *, kind='run', stdin_text='',
            timeout=10, writable=False):
    """Run one command under the active tier and return a uniform result dict.

    host_argv      what to run directly on this machine (rlimit / none tiers)
    container_argv what to run inside the image (docker tier), where the workdir is /work
    """
    tier = ensure_allowed()
    start = time.time()

    if tier == DOCKER:
        argv = _docker_command(container_argv, workdir, kind, writable)
        popen_kwargs = {}
        # Docker adds its own startup cost; give the wall clock a little headroom so a
        # slow cold start is not reported to the student as an infinite loop.
        timeout = timeout + _conf('CODE_SANDBOX_STARTUP_GRACE', 15)
    else:
        argv = host_argv
        popen_kwargs = {'cwd': str(workdir)}
        if tier == RLIMIT:
            popen_kwargs['preexec_fn'] = _rlimit_preexec(kind)
        elif os.name == 'posix':
            popen_kwargs['start_new_session'] = True
        elif os.name == 'nt':
            popen_kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', **popen_kwargs)
    except OSError as exc:
        return {'stdout': '', 'stderr': f'Could not start the program: {exc}',
                'exit_code': -1, 'timed_out': False,
                'time_ms': int((time.time() - start) * 1000), 'tier': tier}

    try:
        stdout, stderr = proc.communicate(input=stdin_text or '', timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.SubprocessError:
            stdout, stderr = '', ''
        timed_out = True
        stderr = (f'Time limit exceeded ({timeout}s). Check for an infinite loop, or a '
                  'scanf waiting for input that never arrives.')

    return {
        'stdout': stdout or '',
        'stderr': stderr or '',
        'exit_code': -1 if timed_out else proc.returncode,
        'timed_out': timed_out,
        'time_ms': int((time.time() - start) * 1000),
        'tier': tier,
    }
