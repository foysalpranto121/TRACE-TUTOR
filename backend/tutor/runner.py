"""Compile and run student programs with real compiler diagnostics.

Execution goes through tutor/sandbox.py, which contains it as well as the host allows
(container > rlimits > timeout only). Nothing in this module should call subprocess on
student-derived input directly.
"""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import sandbox

RUN_TIMEOUT_SEC = 3
COMPILE_TIMEOUT_SEC = 60
MAX_OUTPUT_CHARS = 10000

_compiler_cache = {}

DIAG_RE = re.compile(r'^(?P<file>[^:\n]+?):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>fatal error|error|warning|note):\s*(?P<msg>.*)$', re.M)
IGNORED_WARNINGS = ('argument unused during compilation',)


def _find_c_compiler():
    if 'c' in _compiler_cache:
        return _compiler_cache['c']
    found = None
    override = os.environ.get('C_COMPILER')
    if override and shutil.which(override):
        found = (override, [override])
    elif shutil.which('gcc'):
        found = ('gcc', ['gcc'])
    elif shutil.which('clang'):
        found = ('clang', ['clang'])
    else:
        try:
            import ziglang  # noqa: F401
            found = ('zig cc (clang)', [sys.executable, '-m', 'ziglang', 'cc'])
        except ImportError:
            found = None
    _compiler_cache['c'] = found
    return found


def _cxx_argv(c_prefix):
    if c_prefix[-1] == 'cc':
        return c_prefix[:-1] + ['c++']
    if c_prefix[-1] == 'gcc':
        return ['g++'] if shutil.which('g++') else c_prefix
    if c_prefix[-1] == 'clang':
        return ['clang++'] if shutil.which('clang++') else c_prefix
    return c_prefix


def compiler_status():
    box = sandbox.status()
    containerised = box['tier'] == sandbox.DOCKER
    c = _find_c_compiler()
    # In the docker tier the container supplies gcc, so a host toolchain is not needed.
    label = 'gcc (sandboxed container)' if containerised else (c[0] if c else None)
    blocked = box['tier'] == sandbox.NONE and box['enforced']
    if blocked:
        hint = ('Code execution is disabled because no sandbox is available. '
                'Build the runner image (backend/tutor/sandbox.Dockerfile) or set '
                'CODE_SANDBOX_REQUIRED=0 on a closed network.')
    elif not (containerised or c):
        hint = 'No C compiler found. Install gcc/clang or run: pip install ziglang'
    elif box['tier'] != sandbox.DOCKER:
        hint = f'Running with limited containment ({box["tier"]}). {box["label"]}'
    else:
        hint = None
    return {
        'c': label,
        'cpp': label,
        'python': 'python3 (container)' if containerised else f'python {sys.version.split()[0]}',
        'html': 'html5lib (HTML5 validator)',
        'ready': bool(containerised or c) and not blocked,
        'hint': hint,
        'sandbox': box,
    }


def parse_diagnostics(stderr):
    diags = []
    for m in DIAG_RE.finditer(stderr or ''):
        msg = m.group('msg').strip()
        if any(s in msg for s in IGNORED_WARNINGS):
            continue
        sev = m.group('sev')
        diags.append({
            'line': int(m.group('line')),
            'column': int(m.group('col')),
            'severity': 'error' if sev in ('error', 'fatal error') else sev,
            'message': msg,
        })
    return diags


def _clip(text):
    text = text or ''
    return text if len(text) <= MAX_OUTPUT_CHARS else text[:MAX_OUTPUT_CHARS] + '\n... [output truncated]'


def _normalize(s):
    return ' '.join((s or '').split())


def judge_output(expected, actual):
    """Does `actual` satisfy `expected`?

    Whitespace is normalised, and the expected output may sit inside surrounding prose
    ("The answer is 7") - but it has to match whole tokens. A plain substring test
    graded a printed 17 as correct when the expected answer was 7, which quietly
    inflated scores on every numeric task.
    """
    expected_tokens = _normalize(expected).split()
    actual_tokens = _normalize(actual).split()
    if not expected_tokens:
        return True
    if expected_tokens == actual_tokens:
        return True
    span = len(expected_tokens)
    return any(actual_tokens[i:i + span] == expected_tokens
               for i in range(len(actual_tokens) - span + 1))


def _run_process(argv, stdin_text, cwd, timeout=RUN_TIMEOUT_SEC, container_argv=None):
    result = sandbox.execute(
        host_argv=argv,
        container_argv=container_argv or argv,
        workdir=cwd,
        kind='run',
        stdin_text=stdin_text,
        timeout=timeout,
    )
    result['stdout'] = _clip(result['stdout'])
    result['stderr'] = _clip(result['stderr'])
    return result


def _compile_c_family(language, code, workdir):
    """Compile the submission.

    Compilation is itself untrusted work - `#include "/etc/passwd"` and `#pragma` tricks
    are reachable from source text - so it runs under the sandbox too, and in the docker
    tier it uses the container's own gcc rather than the host toolchain.
    """
    tier, _ = sandbox.detect()
    src_name = 'main.c' if language == 'c' else 'main.cpp'
    # In a container the binary is Linux/ELF; on the host it must match the host.
    exe_name = 'main.out' if (tier == sandbox.DOCKER or os.name != 'nt') else 'main.exe'
    exe = workdir / exe_name
    (workdir / src_name).write_text(code, encoding='utf-8')
    flags = ['-fno-caret-diagnostics', '-fno-color-diagnostics', '-Wall', src_name, '-o', exe_name]

    container_argv = ['gcc' if language == 'c' else 'g++'] + flags

    if tier == sandbox.DOCKER:
        label = 'gcc (sandboxed container)'
        host_argv = container_argv
    else:
        comp = _find_c_compiler()
        if not comp:
            return {'ok': False, 'compiler': None, 'output': compiler_status()['hint'],
                    'diagnostics': [], 'exe': None}
        label, prefix = comp
        host_argv = (list(prefix) if language == 'c' else _cxx_argv(list(prefix))) + flags

    result = sandbox.execute(
        host_argv=host_argv, container_argv=container_argv, workdir=workdir,
        kind='compile', timeout=COMPILE_TIMEOUT_SEC,
        writable=True,  # the compiler has to write the binary into the workdir
    )
    if result['timed_out']:
        return {'ok': False, 'compiler': label, 'output': 'Compiler timed out.',
                'diagnostics': [], 'exe': None}

    stderr = result['stderr']
    diags = parse_diagnostics(stderr)
    ok = result['exit_code'] == 0 and exe.exists()
    if not ok and not any(d['severity'] == 'error' for d in diags):
        last = (stderr or 'Compilation failed').strip().splitlines()
        diags.append({'line': 1, 'column': 1, 'severity': 'error',
                      'message': (last[-1] if last else 'Compilation failed')[:300]})
    return {'ok': ok, 'compiler': label, 'output': _clip(stderr), 'diagnostics': diags,
            'exe': exe if ok else None, 'exe_name': exe_name}


def _check_python(code, workdir):
    (workdir / 'main.py').write_text(code, encoding='utf-8')
    try:
        # Parsing is not execution, so this is safe to do in-process.
        ast.parse(code, filename='main.py')
    except SyntaxError as e:
        return {'ok': False, 'compiler': 'python', 'output': f'main.py:{e.lineno}:{e.offset or 1}: error: {e.msg}',
                'diagnostics': [{'line': e.lineno or 1, 'column': e.offset or 1, 'severity': 'error', 'message': e.msg}], 'exe': None}
    return {'ok': True, 'compiler': 'python', 'output': '', 'diagnostics': [],
            'exe': workdir / 'main.py', 'exe_name': 'main.py'}


def _run_html(code, checks, mode):
    from . import html_checker
    diagnostics = html_checker.check_html(code)
    errors = [d for d in diagnostics if d['severity'] == 'error']
    result = {
        'compiler': 'html5lib (HTML5 validator)',
        'diagnostics': diagnostics,
        'compile_output': html_checker.format_output(diagnostics),
        'test_results': [],
    }
    if mode == 'check':
        result['status'] = 'COMPILE_ERROR' if errors else 'OK'
        return result
    checks = [c for c in (checks or []) if isinstance(c, dict) and c.get('selector')]
    if checks:
        result['test_results'] = html_checker.run_checks(code, checks)
    else:
        result['test_results'] = [{
            'id': 1, 'name': 'Document is valid HTML', 'input': '', 'expected': '0 errors',
            'actual': f'{len(errors)} error(s), {len(diagnostics) - len(errors)} warning(s)',
            'passed': not errors, 'exit_code': 0, 'timed_out': False, 'time_ms': 0,
        }]
    result['passed_count'] = sum(1 for t in result['test_results'] if t['passed'])
    all_passed = result['passed_count'] == len(result['test_results'])
    result['status'] = 'COMPILE_ERROR' if errors else ('SUCCESS' if all_passed else 'WRONG_ANSWER')
    return result


def run_code(language, code, test_cases=None, mode='run'):
    language = (language or 'c').lower()
    if language not in ('c', 'cpp', 'python', 'html'):
        return {'status': 'UNSUPPORTED', 'message': f'Language {language} is not compiled server-side.'}
    if not (code or '').strip():
        return {'status': 'COMPILE_ERROR', 'compiler': None, 'diagnostics': [
            {'line': 1, 'column': 1, 'severity': 'error', 'message': 'The program is empty.'}], 'compile_output': '', 'test_results': []}
    if language == 'html':
        # Parsed in-process by html5lib; no subprocess, so no sandbox needed.
        return _run_html(code, test_cases, mode)

    try:
        sandbox.ensure_allowed()
    except sandbox.SandboxUnavailable as exc:
        return {
            'status': 'SANDBOX_UNAVAILABLE',
            'compiler': None,
            'diagnostics': [{'line': 1, 'column': 1, 'severity': 'error', 'message': str(exc)}],
            'compile_output': str(exc),
            'test_results': [],
            'sandbox': sandbox.status()['tier'],
        }

    workdir = Path(tempfile.mkdtemp(prefix='trace_run_'))
    try:
        build = _check_python(code, workdir) if language == 'python' else _compile_c_family(language, code, workdir)
        result = {
            'compiler': build['compiler'],
            'diagnostics': build['diagnostics'],
            'compile_output': build['output'],
            'test_results': [],
            'sandbox': sandbox.status()['tier'],
        }
        if not build['ok']:
            result['status'] = 'COMPILE_ERROR'
            return result
        if mode == 'check':
            result['status'] = 'OK'
            return result

        exe_name = build.get('exe_name') or Path(build['exe']).name
        if language == 'python':
            run_argv = [sys.executable, str(build['exe'])]
            container_argv = ['python3', exe_name]
        else:
            run_argv = [str(build['exe'])]
            container_argv = [f'./{exe_name}']
        cases = test_cases or [{'input': '', 'output': ''}]
        all_passed, any_runtime_error = True, False
        for idx, tc in enumerate(cases):
            stdin_text = (tc.get('input') or '')
            if stdin_text and not stdin_text.endswith('\n'):
                stdin_text += '\n'
            run = _run_process(run_argv, stdin_text, workdir, container_argv=container_argv)
            passed = (run['exit_code'] == 0) and judge_output(tc.get('output', ''), run['stdout'])
            if run['exit_code'] != 0:
                any_runtime_error = True
            all_passed = all_passed and passed
            result['test_results'].append({
                'id': idx + 1,
                'input': tc.get('input', ''),
                'expected': tc.get('output', ''),
                'actual': run['stdout'].strip(),
                'stderr': run['stderr'].strip(),
                'exit_code': run['exit_code'],
                'timed_out': run['timed_out'],
                'time_ms': run['time_ms'],
                'passed': passed,
            })
        result['status'] = 'RUNTIME_ERROR' if any_runtime_error else ('SUCCESS' if all_passed else 'WRONG_ANSWER')
        result['passed_count'] = sum(1 for t in result['test_results'] if t['passed'])
        return result
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
