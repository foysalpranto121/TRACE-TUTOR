# Restricted wrapper compatibility

The supplied server wrapper allows `--volume` and a non-root `--user`, but rejects
`--mount`. The root-owned wrapper has not been changed. The default mount style
remains `bind` (`--mount`). A deployment can explicitly select `volume` only with
an existing workspace under a configured root at the same absolute backend/host
path. Read-only execution mounts and the random-token read/write probe remain.

The runner also reads the new workspace/mount environment values when an older
Django settings module lacks their attributes. Therefore this server can update
only `sandbox.py` and the previously changed `runner.py`.

From the Windows backend folder:

```powershell
scp -i "$env:USERPROFILE/.ssh/trace_tutor" .\tutor\sandbox.py .\tutor\runner.py shihab@89.167.59.65:/srv/trace-tutor/backend/tutor/
ssh -i "$env:USERPROFILE/.ssh/trace_tutor" shihab@89.167.59.65
```

On the server:

```bash
mkdir -p /srv/trace-tutor/sandbox-work
chmod 700 /srv/trace-tutor/sandbox-work
cd /srv/trace-tutor/backend
nano .env
```

Add or update these keys, keeping one entry for each key:

```dotenv
CODE_SANDBOX=docker
CODE_SANDBOX_REQUIRED=1
CODE_SANDBOX_MIN_TIER=docker
CODE_SANDBOX_MOUNT_STYLE=volume
CODE_SANDBOX_WORKDIR_ROOT=/srv/trace-tutor/sandbox-work
CODE_SANDBOX_HOST_WORKDIR_ROOT=/srv/trace-tutor/sandbox-work
```

Then:

```bash
../venv/bin/python manage.py shell -c "from tutor import sandbox; print(sandbox.status())"
pm2 restart trace-tutor --update-env
```

Status must report `tier: docker`, `allowed: True`, and `detail: None`.
No sandbox image rebuild is required for these Python changes.

Local verification command:

```powershell
E:/projects/anaconda/envs/trace_tutor/python.exe docs/sandbox-verification/verify_volume_compat.py
```

The harness uses an existing private workspace and real Docker; it does not bypass
containment. Results are saved in `volume-compat-results.txt`. New regression
tests cover read-only/writable volumes, missing sources, missing configured roots,
and refusing different host/backend paths.

Results: the complete compatibility suite ran 54 tests in 66.680 seconds: 50 passed
and 4 POSIX-only tests skipped on Windows. A further 25 targeted tests all passed
with the workspace attributes removed from Django settings to exercise the legacy
environment fallback. Both runs executed the requested C program with input `5`,
output `15`, exit code `0`, and enforced Docker containment. Logs are
`volume-compat-results.txt` and `volume-compat-final-results.txt`. The initial
Windows reprobe timing failure was resolved by explicitly advancing the mocked
clock in that test; production reprobe behavior was unchanged.
