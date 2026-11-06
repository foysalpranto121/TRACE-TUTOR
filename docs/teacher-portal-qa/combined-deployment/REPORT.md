The single combined TRACE Tutor release was deployed successfully to https://trace.musfiqurtuhin.me at **00:07:43 on 10 October 2026, Asia/Dhaka** (18:07:43 UTC on 9 October). All Task 1 and Task 2 runtime repairs are included. Authenticated live browser checks, actual production Docker compilation, final health checks and database integrity checks passed. No rollback was required and no paid AI request was made.

The current working tree was audited against both complete QA reports before connecting to production. It contains uncommitted repairs on Git HEAD `864de361537f161e56bcabd203e86323a275314c`; deployment did not use HEAD alone. The exact frozen 167-file validation candidate is identified by SHA-256 `6544fb040d6ffbe7671605e4c0820f86bb4965193370012cdbb799bb2828d468`. The 13 published runtime files have manifest SHA-256 `e0ace6dc71856ba612022d381f09ca6d8ca1317c0d43e5c0d1e73831d32c6d05`; their individual deployed byte hashes are recorded in [deployed-manifest.json](deployed-manifest.json). Production verification confirmed every published source hash and every generated frontend asset.

| Included repair | Release evidence |
|---|---|
| T1: independent CVI ratings/comments, explicit submit, draft/conflict recovery | Current ExpertPortal implementation; real desktop/mobile Next/Previous, submit, reload and independent unsent draft checks passed. |
| T2: missing server scores versus genuine zero | Shared validated formatter in ExpertPortal and Dashboard; live missing and zero fixtures both passed. |
| T3: accessible busy refresh control | Accessible label, disabled pending state and keyboard focus/Enter refresh; real grade refreshed to 88/100 on desktop/mobile. |
| S1: header search | Existing deployed HeaderSearch/catalogue dependencies match the combined candidate; current release passed results, empty state and keyboard navigation in the live teacher UI and task selection in the student UI. Loading/error behavior passed regressions. |
| S2: truthful configured/pending/completed/cache/fallback labels | Current model helper and panels; pending state clears stale response, configured metadata matches OpenAI/gpt-5-mini. Completed/cache/fallback behavior passed regressions; no paid generation was issued live. |
| Review validation and concurrent overwrite protection | Strict integers, additive revision tokens, transaction locks, conflict preservation and deterministic latest-review ordering; real PostgreSQL race regressions passed in isolated Linux staging. |
| Updated grade timestamps and persistence | Current assessment backend; timestamp regressions and real disposable grade save/update/refresh passed. |
| Backup driver mismatch | Updated command uses the installed/pinned psycopg2 driver and closes verification connections; candidate regressions passed. Deployment backup was independently restore-verified using psycopg2 and a private cluster. |
| Task 2 malformed code API requests | Runtime structural validation deployed; invalid request matrix passed isolated Linux tests without 500 errors. |
| Task 2 student Dashboard missing/best scores | Nullable aggregation and shared formatter deployed; PostgreSQL regressions and actual student Dashboard missing/zero display passed. |
| Five former backend failures and real sandbox verification | Frozen full backend suite passed with Docker active; real production compiler/stdin/stdout and compilation errors passed safely. |

| Published source file | Purpose |
|---|---|
| backend/assessment/views.py | Review validation, revision conflicts, locking and grade timestamps. |
| backend/assessment/management/commands/backup_study.py | Verification driver and connection cleanup. |
| backend/logging_app/views.py | Null-safe assessment summaries. |
| backend/tutor/views.py | Malformed code-request validation; preserves existing model metadata and policy. |
| frontend/src/pages/ExpertPortal.jsx | Independent drafts, validation/conflicts, refresh accessibility and scores. |
| frontend/src/services/score.js | Missing/zero/invalid score formatter. |
| frontend/src/services/api.js | Optional review revision contract. |
| frontend/src/services/tutorModel.js | Truthful configured/pending/response labels. |
| frontend/src/components/TutorPanel/AnswerOnlyPanel.jsx | Loading-state model label and cache behavior. |
| frontend/src/components/TutorPanel/ReasoningTracePanel.jsx | Loading-state model label and cache behavior. |
| frontend/src/pages/Workspace.jsx | Clears prior answer when a new request starts. |
| frontend/src/components/ui/index.jsx | Review heading semantics. |
| frontend/src/pages/Dashboard.jsx | Correct latest/best/missing/zero score displays. |

Header search, provider metadata backend support, runner/sandbox compatibility, assessment bank, hint policy and other existing functionality were already present in production. Their source dependencies were checked against the candidate rather than replaced by an older checkout. There are **118 guarded unchanged runtime dependencies**. New/updated tests, local QA settings/runner, browser tooling, reports, screenshots, caches and secrets were excluded from published application files. The separate secret-free validation archive was uploaded only to private `/tmp` staging. Pre-existing local settings additions were omitted because production already supports its configured workspace and volume mapping through the verified runner's environment fallback; staging used the actual production settings module and passed. No unrelated working-tree feature, environment file, deployment service template or research bank revision was published.

The verified target is **shihab@89.167.59.65**, application root **/srv/trace-tutor**. Existing PM2 process **trace-tutor** runs the venv's waitress-serve from `/srv/trace-tutor/backend`; nginx is the active HTTPS proxy. PostgreSQL is **trace_tutor_db**, accessed by its existing non-superuser role without CREATEDB. Private staging was `/tmp/trace-tutor-combined-20261009`. These values came from existing deployment records and were independently checked on the server.

The existing guarded workflow was retained: exact source/dependency checks, isolated staging, npm ci with the unchanged lockfile, tests/lint/build, application source publication, Django checks, PM2 restart, health check, hashed assets before atomic index.html replacement, another PM2 restart for static discovery, live verification and PM2 save. Older hashed assets remain available to open tabs. Only PM2 trace-tutor was restarted, twice as documented. nginx, PostgreSQL and Docker were not restarted. No application dependency versions, secrets, provider routing, PM2 environment or sandbox configuration changed. npm ci installed the existing dependencies only in staging. The migration check passed with **no pending migrations**; no migrations were applied, and all 38 migration records remained unchanged.

The mandatory backup completed and was verified **before any candidate application file was uploaded**. Backup and durable rollback artifacts are at:

`/srv/trace-tutor/deployment-backups/combined-teacher-docker-20261009T175621Z`

A PostgreSQL REPEATABLE READ read-only transaction exported one snapshot. Both pg_dump and all table counts used that same snapshot. The dump restored successfully into a disposable PostgreSQL 16 cluster with a private Unix socket, no TCP listener, temporary random credentials and a separate non-superuser restore role. **All 22 public tables and every recorded row count matched.** The private restore cluster and subsequent regression cluster were stopped and removed. No production role privilege was granted, no local test database replaced production, and no database snapshot was restored over live data.

The protected backup preserves prior backend/frontend sources, frontend dist, root/backend environment copies, the current PM2 definition, media, OCR cache, Chroma store, backend data and RAG files where present. Hash checks verified the preserved files before publication and again after all smoke tests. The directory is mode 0700, and protected environment/PM2 copies are mode 0600. Production had about 30.4 GB free and write permission before backup. There were no frontend environment files requiring an additional copy. Exact release manifests and a durable rollback tool are stored alongside the backup.

Application rollback is available through the preserved `rollback.py --rollback` using `/srv/trace-tutor/venv/bin/python`. It verifies source identities, restores the 13 affected prior sources and old frontend entry point/assets, restarts only trace-tutor and checks health. It does **not** restore the database. Use it only after reviewing the incident and any subsequent release; its source guards refuse unexpected later changes. Automatic application rollback surrounded publication and critical verification. It was not exercised against healthy production. This is a verified server-local rollback backup; an independently stored off-host disaster-recovery copy was not created by this task.

| Verification | Result | Actual evidence |
|---|---|---|
| Frozen local backend | PASS | 497 tests: 493 passed, zero failed, four Windows platform skips; 201.361 seconds. |
| Frozen local frontend | PASS | 108 tests, lint and production build; build 4.35 seconds. |
| Four POSIX-only checks | PASS | Original unchanged tests ran in an offline restricted Linux container, then again in production-shaped private Linux staging; zero skips/failures. |
| Linux/PostgreSQL staging | PASS | 113 selected safe backend tests, zero failures/skips; 49.742 seconds; socket-only private database, provider keys blank, external model HTTP blocked. |
| Server frontend staging | PASS | Same 108 tests, lint and build; build 5.49 seconds. |
| Frontend | PASS | Public routes and every generated JS/CSS asset matched the release; real desktop/mobile UI loaded. |
| Backend | PASS | Django checks, actual APIs and final health; no new critical Python/startup log errors. |
| PostgreSQL | PASS | Health connection, isolated restore and final row fingerprints/counts. |
| Docker execution | PASS | Production reports enforced, allowed, isolated Docker tier; real safe C stdout `15`, compile diagnostics, and browser stdin cases `Sum = 15`/`Sum = 55`. |
| Teacher portal | PASS | Actual login, CVI, grading and refresh on desktop and mobile. |
| Student portal | PASS | Actual login/Dashboard, existing own submissions, Workspace, task selection, safe compiler and Tutor interface. |
| Header search | PASS | Actual result/empty state, keyboard navigation and Workspace destination. |
| CVI drafts | PASS | Distinct unsent drafts survived navigation; submitted feedback persisted across actual reload. |
| Grading | PASS | Designated submission saved, updated in a second real API session, refreshed and persisted at 88/100. |
| Score formatting | PASS | Missing remains unavailable and actual zero remains 0% in teacher/student views. |
| AI model metadata | PASS | Production configured OpenAI / gpt-5-mini, no fallback models; Dashboard/Workspace metadata consistent. |
| Actual paid AI generation | UNVERIFIED | No provider-backed request or credit spending authorized/performed. |
| Authentication/permissions | PASS | Real disposable teacher/student login; student frontend redirected from /expert and five teacher-only API operations returned denial. |
| Mobile usability | PASS | 390×844 teacher/student browser flows and screenshots inspected; student Workspace fits the viewport. |
| Accessibility | PASS | Four live teacher CVI/marking axe scans, zero violations; keyboard refresh passed. |

The four POSIX checks were `KillTreeTests.test_it_kills_the_childs_own_group_when_that_is_not_ours`, `KillTreeTests.test_it_never_signals_the_web_servers_own_process_group`, `RlimitTests.test_a_limit_the_platform_rejects_does_not_break_the_run` and `RlimitTests.test_the_limit_set_covers_memory_cpu_processes_and_file_size`. These mock-based process-group/resource-limit checks did not weaken required Docker enforcement or run hostile programs on production. Full local sandbox stress tests were retained in the 497-test candidate run. Production tests used safe finite C programs, compilation errors and a harmless nonzero exit; no fork bomb, memory exhaustion, infinite-loop attack or large production load test was performed.

The existing Docker runner uses `trace-tutor-runner:1`, a non-root identity, no network, dropped capabilities, no-new-privileges, a read-only execution root/workspace, and the existing configured `volume` mapping under `/srv/trace-tutor/sandbox-work`. Run configuration remains 256 MB, 64 processes and 4 MB file size; compile remains 1024 MB, 128 processes and 64 MB. No image or wrapper changes were made. The unchanged wall-time/startup grace and Docker CPU backstop behavior remains documented in the preceding recovery report; the configured CPU-seconds fields are not a claim of a newly imposed five-second Docker wall timeout. Safe production case execution measured approximately 350–396 ms per case, including Docker startup. These samples do not establish cohort throughput.

Disposable testing created exactly three clearly marked QA accounts, two submissions and associated QA ratings/grades/tokens/events. Browser grading requests were explicitly constrained to those submission IDs; paid tutor queries and assessment submissions were blocked in the harness. The separate reviewer's QA grade and rating remained intact during verification. Afterwards the three accounts and only their dependent QA records were removed: 3 profiles, 2 submissions, 2 grades, 2 ratings, 2 tokens and 17 telemetry events. Their credentials were removed remotely and locally, and all browser contexts closed.

Final row fingerprints confirmed **every pre-existing record was unchanged**, and all original table counts matched after cleanup: 11 accounts/profiles, 11 submissions, 14 paper sittings, 232 interactions, four existing authentication tokens and 43 trace-cache rows. The original teacher grade/rating tables contained zero rows; their final counts remain zero, while preservation of independent existing reviewer records was exercised using the controlled QA fixtures. Existing participant data was neither reset nor reseeded. Temporary QA inserts advanced normal database sequences; sequences were intentionally not reset. Environment files, PM2 environment, database permissions and original backup hashes were unchanged, nginx/PM2 were healthy, and no new critical log errors were found.

Remaining limitations: actual provider-backed generation is unverified; intended full-cohort capacity is unverified. The unchanged three-person local concurrency test passed 3/3 saved/graded with p95 submission latency about 2.11 seconds and maximum time to marks 12.8 seconds, within its existing 30-second budget. No full-cohort capacity claim or production load test is made. CVI drafts remain memory-only with navigation/reload warnings. Legacy clients that omit revision tokens can still overwrite an edit; existing tabs should refresh to load the new client. A response model alias is not proof of a provider-resolved model revision. The backup is server-local, as noted above.

No unresolved critical release or sandbox defect was found. Two staging/publication harness assumptions were corrected before application replacement: PM2 must be resolved through the documented PATH, and fingerprinting must use each table's actual primary key rather than assuming an id column. The separate student harness was corrected for the initial Bangla login locale before login; its successful rerun completed the student Workspace checks. These were tooling corrections, with failed attempts stopped before their dependent application/test actions.

Evidence: [candidate identity](candidate-identity.json), [deployed source hashes](deployed-manifest.json), [production compiler/metadata verification](production-verification.json), [desktop/mobile browser results](production-browser-results.json), [student Workspace results](production-student-workspace-results.json), [final integrity audit](final-audit.json). Reproduction/rollback tools are preserved in this directory. Raw logs, source baselines, validation snapshots and screenshots remain QA artifacts excluded from the production app and Git.

**COMBINED RELEASE: ALL VERIFIED TASK 1 + TASK 2 FIXES INCLUDED**

**DEPLOYMENT: SUCCESS**

**PRODUCTION HEALTH: HEALTHY**

**DATABASE: PRESERVED**

**DOCKER SANDBOX: HEALTHY**

**ROLLBACK: AVAILABLE**

**REMAINING RISKS: Paid AI generation and full-cohort capacity unverified; memory-only drafts and legacy-client revision limits; server-local backup.**
