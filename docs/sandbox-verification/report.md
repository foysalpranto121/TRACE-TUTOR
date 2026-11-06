# Sandbox repair — 2026-10-07

## Root cause and evidence

Python `mkdtemp()` creates a private `0700` directory owned by the backend. The
runner image uses `USER 65532:65532`. With a different backend UID, the runner
cannot traverse that bind mount. A restrictive umask also makes backend-written
source/probe files unreadable to a different UID. The same mismatch prevents GCC
from creating its executable in the writable compile mount.

This was reproduced on Linux with the built production runner image:

```text
Original root-owned 0700 workdir: 1 cat: probe.txt: Permission denied
Fixed shared workdir probe: (True, None)
```

The `rlimit` error is a consequence: Docker fails its probe, automatic detection
finds only rlimit, and the required Docker policy refuses execution correctly.
Neither the required policy nor the minimum tier was lowered.

There is a second concrete deployment defect: `deploy/linux/trace-tutor.service`
uses `PrivateTmp=true`. Its `/tmp` differs from the host daemon's `/tmp`. The
old `--volume` syntax could silently create an empty host directory instead of
mounting the backend's workspace. Containerized backends have the same path issue
unless their workspace is shared with the host daemon.

## Exact changes

The complete task-specific diff is in [exact-changes.patch](exact-changes.patch).
Existing unrelated changes in settings and the environment example were excluded.

| File | Change |
| --- | --- |
| `backend/tutor/sandbox.py` | Explicit Docker UID/GID; match non-root POSIX backend, or use `65532:65532` for root/Windows backend. Root backends chown private directories and files to the runner. Source/probe files use `0600`; directories remain `0700`. Shared workspace roots translate backend paths to daemon host paths. `--mount type=bind` rejects missing host sources. Random-token read and write probes verify both permissions and shared-directory identity. Failure messages point to Docker configuration rather than suggesting a policy downgrade. |
| `backend/tutor/runner.py` | All execution directories and C/C++/Python source files use the shared workspace helpers. Compiler status includes Docker failure details. |
| `backend/trace_backend/settings.py` | Read `CODE_SANDBOX_WORKDIR_ROOT` and `CODE_SANDBOX_HOST_WORKDIR_ROOT` from the environment. |
| `backend/.env.example` | Document a host/backend shared bind mount, the two root paths, and UID/GID behavior. |
| `deploy/linux/trace-tutor.service` | Add `RuntimeDirectory=trace-tutor-work`, mode `0700`, and both workspace roots at `/run/trace-tutor-work`; retain `PrivateTmp=true`. systemd owns the runtime directory as the configured service user. |
| `backend/tutor/test_sandbox.py` | Assert bind-mount and non-root flags; test UID/GID selection, workspace modes/ownership/cleanup, path mapping, read/write probes, and the requested sum program under Docker. |

The production `sandbox.Dockerfile` already supplies the correct toolchain and a
non-root default user, so it did not need a source change. Its image was built.
Network isolation, capability dropping, no-new-privileges, memory/process/CPU caps,
read-only execution root and read-only execution workspace remain enforced.

## Project inventory

Execution and configuration: `backend/tutor/sandbox.py`, `runner.py`,
`sandbox.Dockerfile`, `views.py`; `backend/trace_backend/settings.py`, `urls.py`;
`backend/.env.example`; `deploy/linux/trace-tutor.service`; `README.md`.

Callers: `backend/assessment/scoring.py`, `frontend/src/services/api.js`.

Related tests: `backend/tutor/test_sandbox.py`, `backend/tutor/tests.py`,
`backend/tests/test_journey.py`, and assessment tests `test_access.py`,
`test_load.py`, `test_scoring.py`, `test_sittings.py`.

Other temporary directories, unrelated to code execution, occur in
`backend/curriculum/tests.py`, `backend/trace_backend/tests.py`, and
`backend/assessment/tests/test_sittings.py`. They were left unchanged.
No backend Dockerfile or Compose deployment is checked into this project.

## Commands executed

Read-only inspection used `rg --files`, `rg -n`, `rg -l`, `Get-Content`,
`Get-Command`, `Get-ChildItem`, `git status --short`, and targeted `git diff`.
The initial host Python had no Django installed. Docker CLI was present, but
Docker Desktop/WSL were stopped. Commands below ran from the repository root in
PowerShell; Docker access required execution outside the filesystem sandbox.

```powershell
docker info
docker context ls
wsl --list --verbose
docker desktop start
docker info --format '{{.ServerVersion}}'
docker image ls --format '{{.Repository}}:{{.Tag}}'
docker build -f backend/tutor/sandbox.Dockerfile -t trace-tutor-runner:1 backend/tutor

python -m venv .sandbox-venv
./.sandbox-venv/Scripts/python.exe -m pip install 'Django>=5.2,<5.3' html5lib beautifulsoup4
./.sandbox-venv/Scripts/python.exe -m pip install Django==5.2.17

New-Item -ItemType Directory -Path .sandbox-verification -Force | Out-Null
Copy-Item -LiteralPath backend/tutor -Destination .sandbox-verification/tutor -Recurse
Copy-Item -LiteralPath backend/tutor/test_sandbox.py -Destination .sandbox-verification/tutor/test_sandbox.py
docker build -t trace-sandbox-verification:local .sandbox-verification
./.sandbox-venv/Scripts/python.exe .sandbox-verification/verify.py *> .sandbox-verification/windows-results.txt

docker volume create trace-sandbox-verification-work
$sandboxHostRoot = docker volume inspect trace-sandbox-verification-work --format '{{.Mountpoint}}'
docker run --rm --mount type=volume,source=trace-sandbox-verification-work,target=/sandbox-work --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock -e CODE_SANDBOX_WORKDIR_ROOT=/sandbox-work -e "CODE_SANDBOX_HOST_WORKDIR_ROOT=$sandboxHostRoot" trace-sandbox-verification:local *> .sandbox-verification/linux-root-results.txt

docker run --rm --mount type=volume,source=trace-sandbox-verification-work,target=/sandbox-work trace-sandbox-verification:local chown 1001:1002 /sandbox-work
docker run --rm --user 1001:1002 --group-add 0 --mount type=volume,source=trace-sandbox-verification-work,target=/sandbox-work --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock -e CODE_SANDBOX_WORKDIR_ROOT=/sandbox-work -e "CODE_SANDBOX_HOST_WORKDIR_ROOT=$sandboxHostRoot" trace-sandbox-verification:local *> .sandbox-verification/linux-nonroot-results.txt

$sandboxReproFile = (Resolve-Path .sandbox-verification/reproduce.py).Path
docker run --rm --mount type=volume,source=trace-sandbox-verification-work,target=/sandbox-work --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock --mount "type=bind,source=$sandboxReproFile,target=/app/reproduce.py,readonly" -e CODE_SANDBOX_WORKDIR_ROOT=/sandbox-work -e "CODE_SANDBOX_HOST_WORKDIR_ROOT=$sandboxHostRoot" trace-sandbox-verification:local python3 /app/reproduce.py *> .sandbox-verification/reproduction-results.txt

docker run --rm --mount type=volume,source=trace-sandbox-verification-work,target=/sandbox-work trace-sandbox-verification:local ls -la /sandbox-work
git diff --check -- backend/tutor/sandbox.py backend/tutor/runner.py backend/tutor/test_sandbox.py backend/trace_backend/settings.py backend/.env.example deploy/linux/trace-tutor.service
```

The temporary harness scripts and Dockerfile above are saved alongside this
report. To reproduce, copy these three files into `.sandbox-verification` before
building. The verification image is test infrastructure, separate from the
production runner. Only this test backend has the daemon socket; student runner
containers never receive it. The test backend's supplementary GID 0 permits
daemon-socket access; the runner itself uses only `1001:1002` and dropped capabilities.

## Test results

| Environment | Sandbox suite | Requested C program |
| --- | --- | --- |
| Windows host backend → Docker Desktop Linux daemon | 50 tests, 42 passed, 8 skipped | Docker, `SUCCESS`, stdout `15`, exit 0 |
| Linux root backend container → host daemon; umask `077` | 50 tests, all passed, 64.851 s | Runner `65532:65532`, stdout `15`, exit 0 |
| Linux backend UID/GID `1001:1002` → host daemon; umask `077` | 50 tests, all passed, 65.139 s | Runner `1001:1002`, stdout `15`, exit 0 |

The Windows skips cover POSIX rlimits/process groups and unavailable host C
toolchain resource tests. Those tests all ran on Linux. Both Linux runs also
passed the network-denial, outside-root write denial, source write denial,
non-root UID, infinite-loop timeout, memory exhaustion and fork-bomb tests.
An incorrect host path was rejected with `bind source path does not exist`.
The shared test volume was empty after execution: cleanup succeeded.
The diff whitespace check passed.

Raw logs: [Windows](windows-results.txt), [Linux root](linux-root-results.txt),
[Linux non-root](linux-nonroot-results.txt), [reproduction](reproduction-results.txt).
The tests used isolated Django settings with the pinned Django `5.2.17`, enforced
Docker containment, and no application database or production credentials.
The full database-backed application suite was not run.

## Deployment

The code and runner image are fixed and verified locally. No remote deployment
was accessed or modified. Restart the deployed backend after updating its code.
For the supplied Linux service, install the updated unit, run
`sudo systemctl daemon-reload`, then `sudo systemctl restart trace-tutor`.
The live systemd unit could not be started here because the host is Windows.

For a backend container, mount an existing host directory into the backend and set
both roots, for example `/sandbox-work` locally and `/srv/trace-work` on the daemon
host. The backend user must own or have write/traverse permission on that shared
parent. The random-token probe then verifies actual read/write consistency.
Keep `CODE_SANDBOX_REQUIRED=1` and `CODE_SANDBOX_MIN_TIER=docker` in production.
