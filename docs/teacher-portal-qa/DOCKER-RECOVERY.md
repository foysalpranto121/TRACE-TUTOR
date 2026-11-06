# TRACE Tutor: Docker recovery and release verification

Date: 2026-10-09. This report supersedes the earlier sandbox-blocked test totals in [REPORT.md](REPORT.md).

**Outcome:** the local Docker blocker is resolved. All five previously failing tests pass with real execution. The final backend suite has **497 tests: 493 passed, zero failed, four platform skips**. Frontend verification has **108 passed**. Real browser-to-Django-to-PostgreSQL-to-Docker integration passes. Local verification is complete; production readiness still requires target-platform and intended-cohort checks described below. Nothing was deployed.

## Docker connectivity and architecture

The requested docker version, docker info, docker ps -a and docker image ls commands all communicate with Docker Desktop. The CLI is Windows/amd64, context desktop-linux; the daemon is Linux/amd64, Docker Engine 29.6.2 on Docker Desktop 4.84.0. The runner image was already installed, so no rebuild, pull, or configuration change was necessary.

Runner image: trace-tutor-runner:1, ID sha256:62c70a33a66a75b7836f9ec812d2ea1855fc071cc8183cc1e89eeb74f39b787d. Its history agrees with backend/tutor/sandbox.Dockerfile: Debian bookworm-slim, gcc/g++/libc development files/python3-minimal, non-root user 65532:65532, workdir /work. [docker-connectivity.log](docker-connectivity.log) records engine/image inventory; its container snapshot was taken during the smoke timeout test, so its temporary trace-run container is expected. The final cleanup check confirms it was removed.

TRACE Tutor **does not require a persistent execution container**. tutor/runner.py compiles and runs through tutor/sandbox.py. Requests create private temporary workdirs; each compile/run command uses a disposable container, named trace-run-<unique ID>, with --rm. Compilation writes its binary in the private mounted workdir. Execution mounts that workdir read-only and has a read-only root plus a 16 MB /tmp tmpfs. Timeouts kill the named container before stopping the Docker client. Runner finally blocks remove the temporary workdir.

The actual sandbox read/write mount probe returns tier=docker, isolated=True, enforced=True, required_tier=docker, allowed=True, detail=None. The previous failure was an unavailable local daemon/image at that time, not a requirement to start one of the unrelated stopped containers. None of those containers was modified.

Security remains unchanged: no network, all capabilities dropped, no-new-privileges, explicit non-root identity, memory and swap caps, process cap, CPU quota and CPU/file-size ulimits. Configured run caps are 256 MB memory/swap, 64 processes, 1 CPU, and 4 MB file size; compile caps are 1,024 MB, 128 processes, 1 CPU and 64 MB file size. Memory/PID policy flags and containment behavior are covered by the unchanged existing tests. Resource-exhaustion cases ran only inside Docker. The memory test permits a bounded timeout as well as allocation failure; it is not a claim that every case produced an OOM kill.

The runner's base run timeout is 3 seconds and compile timeout 60 seconds. Existing CODE_SANDBOX_STARTUP_GRACE=15 gives Docker wall-clock limits of **18 seconds per test case** and 75 seconds per compile. CPU backstops are above those wall-clock deadlines (48 and 105 CPU seconds with the default backstop), while the ordinary timeout path kills the container. The live UI correctly showed Time limit exceeded (18s); these limits were not shortened, removed, or relaxed during this task.

Relevant settings: CODE_SANDBOX, CODE_SANDBOX_REQUIRED, CODE_SANDBOX_MIN_TIER, CODE_SANDBOX_IMAGE, CODE_SANDBOX_WORKDIR_ROOT, CODE_SANDBOX_HOST_WORKDIR_ROOT, CODE_SANDBOX_MOUNT_STYLE, CODE_SANDBOX_CPUS, CODE_SANDBOX_STARTUP_GRACE, CODE_SANDBOX_REPROBE_SECONDS, and the CODE_RUN_*/CODE_COMPILE_* caps. Host-path mapping is needed for a containerized backend; this backend runs directly on Windows and its real mount probe succeeds without mapping changes. Existing fail-closed/reprobe tests pass.

## Previously failing five tests

All previously returned SANDBOX_UNAVAILABLE. No tests or assertions were skipped, deleted, weakened, or changed into mocked successes.

| Exact test | Previous expected result | Current result |
|---|---|---|
| tutor.tests.CompilerIntegrationTests.test_a_compile_error_is_reported_with_diagnostics | COMPILE_ERROR with diagnostics | Passed |
| tutor.tests.CompilerIntegrationTests.test_a_correct_program_passes_its_test_case | SUCCESS | Passed |
| tutor.tests.CompilerIntegrationTests.test_a_wrong_answer_is_not_a_pass | WRONG_ANSWER | Passed |
| tutor.tests.PythonCheckingTests.test_a_syntax_error_is_reported_with_a_line_number | COMPILE_ERROR with line number | Passed |
| tutor.tests.PythonCheckingTests.test_valid_python_passes_the_syntax_check | OK | Passed |

The focused rerun ran 5 tests in 2.774 seconds, exit 0: [docker-five-tests.log](docker-five-tests.log). They also pass in the final full suite. Python syntax checking intentionally uses AST parsing; the C compilation/run tests perform actual gcc execution inside Docker.

## Confirmed defects discovered during verification

1. **Malformed code API requests could produce server exceptions.** Numeric source reached .strip(), null test cases reached .get(), and an invalid falsey language could silently become C. POST /api/code/run/ now validates the request object, string fields, run/check mode, test-case array/object shape, and input/output/selector text before invoking the runner. Invalid structures return structured HTTP 400 errors. Valid existing requests and unsupported-language result behavior remain intact. The obsolete API docstring claiming execution was unsandboxed was corrected. Six new real API tests cover stdin/stdout, compiler diagnostics, nonzero exit, actual timeout, malformed inputs and anonymous denial.
2. **A graded row with score_pct=NULL crashed the student Dashboard.** The real smoke log exposed max(integer, None). Aggregation now retains a null best score when all scores are missing, excludes null from numeric comparison, and keeps a real prior best score. Attempt counts and records remain intact. Dashboard rendering now reuses formatScore for latest/best values, preserving genuine 0% and avoiding null% or a fabricated zero. Three backend and two frontend regressions cover these cases. No scoring algorithm or stored grade was changed.

The first smoke harness could exit successfully while the student Dashboard had HTTP 500. Its server log was inspected, the defect was fixed, and the harness now asserts real student Dashboard success and rejects unexpected teacher API HTTP failures. Initial evidence is retained in docker-live-smoke-initial.log. Later harness failures were a focus check racing the intentional refresh loading state and a selector choosing the mobile-hidden desktop model span. Both were corrected by waiting for enabled refresh and checking the visible provenance control. Assertions about actual focus, changed records, and model provenance remain in place. The initial new frontend score tests also needed scoping to assessment cards because unrelated mastery percentages legitimately display 0%; their initial failure log is retained.

## Exact final checks

| Check | Final result and evidence |
|---|---|
| Backend full suite | **497 run: 493 passed, 0 failures/errors, 4 skipped**, 210.254 seconds, exit 0. Includes TRACE_LOAD_TEST=3. [docker-backend-final.log](docker-backend-final.log) |
| First Docker full rerun | 488 run, 483 passed, 0 failed, 5 skipped, 186.027 seconds. Before the nine new backend regressions. [docker-backend-full.log](docker-backend-full.log) |
| New real code API regressions | 6 passed, 22.156 seconds, exit 0. Also included in full-suite totals. [docker-code-api-tests.log](docker-code-api-tests.log) |
| Frontend tests | **108 passed, 0 failed**: 4 Node plus 104 Vitest tests across 6 files. Two new Dashboard regressions. [docker-frontend-tests.log](docker-frontend-tests.log) |
| Lint | Passed, no errors/warnings, exit 0. [docker-frontend-lint.log](docker-frontend-lint.log) |
| Local production build | Passed, 2,249 modules, 4.60 seconds, exit 0. [docker-frontend-build.log](docker-frontend-build.log) |
| Type checking | Not configured for this JavaScript project; not claimed. |
| Django system checks | Passed, no issues. [docker-final-checks.log](docker-final-checks.log) |
| Real local integration | 1 live-server smoke test passed in 51.974 seconds, with desktop teacher, mobile teacher and mobile student browser contexts. No API mock responses. [docker-live-smoke.log](docker-live-smoke.log), [live-browser-results.json](live-browser-results.json) |
| Accessibility | Four real-page axe scans: CVI and marking at 1440×1000 and 390×844, zero violations. Refresh name, focus and keyboard activation also checked. Not an all-app manual screen-reader certification. |
| Patch hygiene/cleanup | git diff --check passed. No disposable DB or trace-run container remains; original three stopped containers unchanged. [docker-final-checks.log](docker-final-checks.log) |

## Real local integration coverage

The harness serves the actual frontend/dist through a real Django LiveServerTestCase on 127.0.0.1. Every local API request goes to Django without interception or substituted responses. External writes are blocked; only the editor's existing Monaco CDN GET assets are allowed. A fresh PostgreSQL test database supplies disposable teacher/student/reviewer accounts and missing/zero-score submissions. Real authentication creates real test tokens. QA settings clear provider keys, isolate media/caches/RAG/backup files, reject remote database hosts, and never point at the configured application database.

Passed checks include:

- Teacher login; two independent CVI drafts across Next/Previous; explicit submission and backend retrieval; submitted values restored after reload; unsent values remain memory-only.
- Missing score versus genuine zero in list/detail; grade save and update; another real HTTP session changes marks to 88; keyboard refresh retrieves that changed server value and renders 88 / 100.
- Public practice search matching loop, destination navigation, and explicit nonexistent-query feedback.
- Actual Run Code on desktop/mobile: inputs 5 and 10 produce Sum = 15 and Sum = 55 with exit 0 and passing sample tests. Desktop additionally verifies gcc diagnostics, a real exit-7 runtime error, and real infinite-loop timeout with visible TIMEOUT output.
- Genuine no-credit tutor fallback through /api/tutor/query/: initial metadata remains neutral, response ai_status=fallback, and labels describe Textbook fallback. Existing passing automated regressions cover configured/provider/loading/completed/cached labels and AI/Textbook/Dual tabs. Paid provider-backed generation remains intentionally untested.
- Student login, successful null-score Dashboard, frontend /expert redirection, and real backend 403 denial for all five teacher read/write checks.
- Checked fixture marks/feedback and rating values belonging to another reviewer remain unchanged; automated null/zero scores stay unchanged. Actual application/research databases were neither used for tests nor written.

The in-app browser still had no available browser, so the existing standalone headless Edge QA tooling was used. Sampled teacher flows have no uncaught page errors or unexpected HTTP errors. Expected role-denial responses and provider-not-configured warnings are intentional. Django broken-pipe messages occurred during cancelled navigation requests; they are not compiler/grade failures. Native PowerShell may label unittest stderr as NativeCommandError in Tee logs even on success; unittest totals and process exit codes above determine results.

## All 14 previously skipped tests

Names below in the sandbox rows have prefix tutor.test_sandbox.; the cohort row has prefix assessment.tests.test_load.

| Previously skipped test | Now | Deployment relevance |
|---|---|---|
| ContainerIsolationTests.test_the_program_cannot_overwrite_its_own_source_tree | Passed | Required containment evidence |
| ContainerIsolationTests.test_the_program_cannot_reach_the_network | Passed | Required containment evidence |
| ContainerIsolationTests.test_the_program_cannot_write_outside_its_workdir | Passed | Required containment evidence |
| ContainerIsolationTests.test_the_program_does_not_run_as_root | Passed | Required containment evidence |
| DockerSumTests.test_sum_of_first_five_natural_numbers | Passed | Required real compiler/stdin/stdout evidence |
| ResourceExhaustionTests.test_an_infinite_loop_is_stopped_and_reported | Passed | Required timeout containment evidence |
| ResourceExhaustionTests.test_a_program_blocked_on_input_does_not_hang_the_request | Passed | Required bounded-request evidence |
| ResourceExhaustionTests.test_a_runaway_allocation_does_not_take_the_host_down | Passed | Required resource-containment evidence |
| ResourceExhaustionTests.test_a_fork_bomb_is_contained | Passed | Required process-containment evidence |
| KillTreeTests.test_it_kills_the_childs_own_group_when_that_is_not_ours | Windows skip | Must run for a Linux/POSIX backend before claiming that target path verified |
| KillTreeTests.test_it_never_signals_the_web_servers_own_process_group | Windows skip | Must run for a Linux/POSIX backend before claiming that target path verified |
| RlimitTests.test_a_limit_the_platform_rejects_does_not_break_the_run | Windows skip | Required if rlimit is supported/selected; not a substitute for required Docker containment |
| RlimitTests.test_the_limit_set_covers_memory_cpu_processes_and_file_size | Windows skip | Required if rlimit is supported/selected; not a substitute for required Docker containment |
| ConcurrentSubmissionTests.test_the_whole_cohort_submitting_at_once | Passed with 3 participants | Small real concurrency smoke passed; intended cohort capacity still needs its actual size |

Ten formerly skipped tests now execute. The four remaining skips are platform conditions, not suppressed failures. For a Linux release, rerun the suite there to cover process-group behavior and classify the optional rlimit tier on that target.

The load check used the existing unchanged 30-second budget: 3/3 saved and graded, zero failures, p95 request latency 2.10 seconds, maximum/time-to-marks 12.8 seconds. These results do not establish performance for a 60-student cohort or for production web-worker topology.

## Changed files in this recovery task

| File | Change |
|---|---|
| backend/tutor/views.py | Code API request validation and corrected sandbox documentation. |
| backend/tutor/test_code_api.py (new) | Six real Docker API regressions; no mocked execution. |
| backend/logging_app/views.py | Null-safe latest/best assessment-score aggregation. |
| backend/logging_app/test_dashboard_scores.py (new) | Three real PostgreSQL null/zero/prior-best regressions. |
| frontend/src/pages/Dashboard.jsx | Shared validated formatter for latest/best score displays; unavailable scores do not become zero. |
| frontend/tests/tutor-model-labels.test.jsx | Two scoped Dashboard missing/zero display regressions; earlier model tests preserved. |
| docs/teacher-portal-qa/live-smoke.py (new) | Local Django live server, disposable accounts/records, real browser subprocess, preservation/cleanup assertions. |
| docs/teacher-portal-qa/live-browser.mjs (new) | Real desktop/mobile API/UI/compiler/fallback/permission/accessibility smoke checks. |
| docs/teacher-portal-qa/live-browser-results.json (new) | Final structured live results and actual API statuses/compiler output. |
| docs/teacher-portal-qa/DOCKER-RECOVERY.md (new) | This report. |
| docs/teacher-portal-qa/REPORT.md | Historical report gains a link to these superseding results. |

New logs in docs/teacher-portal-qa: docker-connectivity.log, docker-five-tests.log, docker-backend-full.log, docker-backend-final.log, docker-code-api-tests.log, docker-frontend-tests.log, docker-frontend-lint.log, docker-frontend-build.log, docker-dashboard-tests-initial.log, docker-live-smoke-initial.log, docker-live-smoke-focus-race.log, docker-live-smoke-mobile-selector.log, docker-live-smoke.log, docker-final-checks.log.

New screenshots: screenshots/live-desktop-marking.png, screenshots/live-mobile-marking.png, screenshots/live-desktop-workspace.png, screenshots/live-mobile-workspace.png, screenshots/live-mobile-student-dashboard.png. Ignored baseline/ contains local pre-edit reference copies; frontend/dist is generated local build output.

No application dependencies, schema changes, migrations, production configuration changes, Docker daemon changes, or sandbox image changes were introduced. Existing QA-only Playwright/axe tooling was reused. Existing work was preserved. Validation now returns 400 for malformed code requests instead of accepting invalid structures or throwing 500; unavailable Dashboard best_score may now be null, which the updated frontend handles explicitly.

## Reproduce and release assessment

Use the installed Django interpreter E:/projects/anaconda/envs/trace_tutor/python.exe. From backend:

- manage.py test tutor.tests.CompilerIntegrationTests tutor.tests.PythonCheckingTests --settings=trace_backend.qa_settings --noinput --verbosity=2
- manage.py test tutor.test_code_api --settings=trace_backend.qa_settings --noinput --verbosity=2
- Set TRACE_LOAD_TEST=3 only in the child test process, then manage.py test --settings=trace_backend.qa_settings --noinput --verbosity=2
- manage.py check --settings=trace_backend.qa_settings

From frontend: npm test; npm run lint; npm run build. From the repository root: run docs/teacher-portal-qa/live-smoke.py using that Python interpreter. Do not run concurrent invocations that share the named disposable test database. The harness starts/stops its own localhost server and tears down its database; no deployment command is involved.

**Local sandbox, targeted regressions, and real integration are verified. The changes are ready for release review, with target-environment verification still required.** The former Docker blocker is no longer a reason to hold local testing. Before a future separately authorized production deployment:

1. Run the suite on the actual backend operating-system/runtime shape. On Linux/POSIX, the process-group checks must execute rather than skip. Run the rlimit checks if that tier is supported, while retaining Docker as the required tier for untrusted code.
2. Run the unchanged cohort-load test at the intended cohort size and actual web/worker topology before claiming production capacity. Three participants on Docker Desktop is a bounded smoke test.
3. Verify runner image, host-path mapping, non-root mount permissions, strict sandbox policy, and backup/restore capability in the target environment under its own authorized test procedure. No production environment was inspected or modified in this task.
4. Actual paid provider-backed generation/provenance remains unverified by explicit instruction; obtain separate permission and use authorized test credentials if that smoke check is required. Neutral/pending/completed/cache and actual offline fallback labels are covered without spending credits.
5. Review pre-existing working-tree changes as well as this recovery patch, and retain the earlier documented CVI draft lifetime and legacy-client revision limitations.
6. Obtain explicit deployment authorization. No build, successful test, or local release assessment authorizes deployment automatically.

**DEPLOYMENT STATUS: NOT DEPLOYED**

**PRODUCTION STATUS: UNCHANGED BY THIS TASK**

**AWAITING EXPLICIT USER AUTHORIZATION FOR DEPLOYMENT**
