"""Compile and run student programs locally with real compiler diagnostics."""
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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
    c = _find_c_compiler()
    return {
        'c': c[0] if c else None,
        'cpp': c[0] if c else None,
        'python': f'python {sys.version.split()[0]}',
        'html': 'html5lib (HTML5 validator)',
        'ready': c is not None,
        'hint': None if c else 'No C compiler found. Install gcc/clang or run: pip install ziglang',
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
    e, a = _normalize(expected), _normalize(actual)
    if not e:
        return True
    return e == a or e in a


def _run_process(argv, stdin_text, cwd, timeout=RUN_TIMEOUT_SEC):
    start = time.time()
    try:
        proc = subprocess.run(
            argv, input=stdin_text or '', capture_output=True, text=True,
            cwd=cwd, timeout=timeout, encoding='utf-8', errors='replace',
        )
        return {
            'stdout': _clip(proc.stdout), 'stderr': _clip(proc.stderr),
            'exit_code': proc.returncode, 'timed_out': False,
            'time_ms': int((time.time() - start) * 1000),
        }
    except subprocess.TimeoutExpired as e:
        return {
            'stdout': _clip(e.stdout.decode('utf-8', 'replace') if isinstance(e.stdout, bytes) else (e.stdout or '')),
            'stderr': f'Time limit exceeded ({timeout}s). Check for an infinite loop or a scanf waiting for input.',
            'exit_code': -1, 'timed_out': True,
            'time_ms': int(timeout * 1000),
        }


def _compile_c_family(language, code, workdir):
    comp = _find_c_compiler()
    if not comp:
        return {'ok': False, 'compiler': None, 'output': compiler_status()['hint'], 'diagnostics': [], 'exe': None}
    label, prefix = comp
    src_name = 'main.c' if language == 'c' else 'main.cpp'
    argv = list(prefix) if language == 'c' else _cxx_argv(list(prefix))
    exe = workdir / ('main.exe' if os.name == 'nt' else 'main.out')
    (workdir / src_name).write_text(code, encoding='utf-8')
    flags = ['-fno-caret-diagnostics', '-fno-color-diagnostics', '-Wall', src_name, '-o', exe.name]
    try:
        proc = subprocess.run(argv + flags, capture_output=True, text=True, cwd=workdir,
                              timeout=COMPILE_TIMEOUT_SEC, encoding='utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return {'ok': False, 'compiler': label, 'output': 'Compiler timed out.', 'diagnostics': [], 'exe': None}
    diags = parse_diagnostics(proc.stderr)
    ok = proc.returncode == 0 and exe.exists()
    if not ok and not any(d['severity'] == 'error' for d in diags):
        diags.append({'line': 1, 'column': 1, 'severity': 'error', 'message': (proc.stderr or 'Compilation failed').strip().splitlines()[-1][:300]})
    return {'ok': ok, 'compiler': label, 'output': _clip(proc.stderr), 'diagnostics': diags, 'exe': exe if ok else None}


def _check_python(code, workdir):
    (workdir / 'main.py').write_text(code, encoding='utf-8')
    try:
        ast.parse(code, filename='main.py')
    except SyntaxError as e:
        return {'ok': False, 'compiler': 'python', 'output': f'main.py:{e.lineno}:{e.offset or 1}: error: {e.msg}',
                'diagnostics': [{'line': e.lineno or 1, 'column': e.offset or 1, 'severity': 'error', 'message': e.msg}], 'exe': None}
    return {'ok': True, 'compiler': 'python', 'output': '', 'diagnostics': [], 'exe': workdir / 'main.py'}


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
        return _run_html(code, test_cases, mode)

    workdir = Path(tempfile.mkdtemp(prefix='trace_run_'))
    try:
        build = _check_python(code, workdir) if language == 'python' else _compile_c_family(language, code, workdir)
        result = {
            'compiler': build['compiler'],
            'diagnostics': build['diagnostics'],
            'compile_output': build['output'],
            'test_results': [],
        }
        if not build['ok']:
            result['status'] = 'COMPILE_ERROR'
            return result
        if mode == 'check':
            result['status'] = 'OK'
            return result

        run_argv = [sys.executable, str(build['exe'])] if language == 'python' else [str(build['exe'])]
        cases = test_cases or [{'input': '', 'output': ''}]
        all_passed, any_runtime_error = True, False
        for idx, tc in enumerate(cases):
            stdin_text = (tc.get('input') or '')
            if stdin_text and not stdin_text.endswith('\n'):
                stdin_text += '\n'
            run = _run_process(run_argv, stdin_text, workdir)
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
