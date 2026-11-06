> Follow-up: Docker recovery and real integration results in [DOCKER-RECOVERY.md](DOCKER-RECOVERY.md) supersede the historical test totals and sandbox blocker below.

# TRACE Tutor teacher portal: engineering and QA report

Date: 2026-10-09. Scope: local investigation, repairs, and isolated verification only.

The five requested issues have passing local regression coverage. The whole application is **not completely release-verified**: the final full Django run has five real code-runner integration failures because this Windows environment has no available Docker sandbox. Actual provider-backed AI generation was deliberately not called. No remote environment was contacted for deployment or research-data operations.

## Architecture and investigation

The application uses React 18, React Router, Vite 6, Tailwind, and component/context state on the frontend; Django 5.2 and Django REST Framework with PostgreSQL on the backend. Existing verification includes Node tests, Vitest/Testing Library, Django API/transaction tests, and sandbox integration tests. RAG uses Chroma and OCR/PDF artifacts. The compiler service requires an isolated execution tier.

Relevant paths and flows:

- AppShell supplies the shared HeaderSearch. Its existing local learningSearch index derives topics and practice tasks from NCTB_PROBLEMS and navigates to /workspace?problem=… . It does not query exam banks, submissions, research records, or staff OCR endpoints.
- ExpertPortal obtains /api/expert/reviews/ and /api/expert/submissions/ through apiService. Explicit POSTs to /api/expert/rating/ and /api/expert/grade/ store ExpertRating and ExpertGrade rows. Server exam scores remain separate from expert marks.
- IsStaffRole authorizes the expert APIs from the authenticated user's stored profile, accepting expert teachers/researchers and rejecting students, anonymous callers, and missing profiles. Researcher-only APIs have a separate IsResearcher gate. Expert identity comes from the authenticated user, never a client-supplied reviewer ID.
- Dashboard and Workspace receive backend tutor configuration metadata. Completed tutor responses supply provider/model/ai_status/cached metadata. AnswerOnlyPanel and ReasoningTracePanel display this provenance; Workspace calls /api/tutor/query/ and the compiler API. Provider configuration and routing were not changed.
- Profile changes go through AuthContext and /api/accounts/profile/; refreshed /api/accounts/me/ reconstructs the authenticated profile. Server study-arm rules remain authoritative.
- Existing fetchApi/ApiError conventions carry structured validation and failure responses. The review changes retain this architecture and add optional revision tokens and explicit 409 handling.

The workspace already contained substantial uncommitted work. [baseline-status.txt](baseline-status.txt) records the initial state. In particular, HeaderSearch/learningSearch integration, neutral/configured model helpers, and earlier Dashboard changes existed before this task. They were preserved and tested; this report does not attribute those earlier changes to this task. No commits, remote pushes, deployment scripts, or live migrations were executed.

## A. Fix summary

| Issue | Established root cause | Files touched by this task | Resulting behavior | Supporting verification |
|---|---|---|---|---|
| T1 — CVI draft loss | One ratings/comment state was reinitialized from the selected item's submitted record on navigation. There was no independent draft map. | ExpertPortal.jsx; expert-portal.test.jsx | Drafts are keyed by stable item ID inside an account/role-keyed workbench. Draft values take precedence over submitted values. Next/Previous preserves each item; only explicit successful Submit clears that item's draft. All five integer scores remain required. | Passing component regressions and desktop/mobile browser flows verify independent ratings/comments, edits, no automatic writes, submitted-state restoration, failures, and refresh behavior. |
| T2 — null% | Both list and detail interpolated a nullable score with a percent suffix without validating its type/status. | score.js; ExpertPortal.jsx; expert-portal.test.jsx | One formatter handles both views. Genuine numeric 0–100 values render percentages, including 0%. Missing pending scores render Not graded; missing grading scores render Grading…; other missing/invalid values render Score unavailable. Numeric strings, booleans, NaN, infinity, and out-of-range values are rejected as scores. Missing detail text wraps within the mobile card. | Table-driven unit/component tests, PostgreSQL API null/zero/pending tests, browser list/detail checks for null, 0 and 85, and visual screenshots pass. |
| T3 — refresh name | The icon-only submissions button had no accessible name or explicit busy state. | ExpertPortal.jsx; expert-portal.test.jsx | Accessible name is Refresh submissions; icon is decorative; loading disables the control and exposes busy feedback. Existing focus styling remains visible. | Accessible-role tests; keyboard Enter and Space retrieve changed mock records; browser focus outline is solid 2px. Four axe scans report zero violations. |
| S1 — header search | The committed version had an inert input. At task start, uncommitted HeaderSearch/learningSearch implementation already addressed it. | No additional search production changes; browser-checks.mjs verifies existing implementation. | Existing permitted topics/tasks, explicit empty results, Enter/navigation, loading/error/retry, status announcements, and mobile behavior were retained. Data scope is public practice content only. | Existing header-search regressions pass, including loading/error/empty/keyboard/role cases. Desktop teacher, mobile teacher, and mobile student browser flows verify actual destination URL, no-results and empty submission. |
| S2 — model labels | Original panels defaulted to Gemini without metadata. Earlier working-tree changes removed that fallback; a remaining loading path could still attach the previous completed/cached response's metadata until preflight finished. | tutorModel.js; AnswerOnlyPanel.jsx; ReasoningTracePanel.jsx; Workspace.jsx; tutor-model-labels.test.jsx | Loading is set and old response cleared before preflight. Pending labels use backend configuration plus pending, or neutral AI Tutor when metadata is unavailable. Completed live/fallback/cache labels use response provenance. Old cached labels are suppressed while loading. | Model regressions cover neutral, configuration, provider fallback, stale responses, pending, completed cache, and tabs. All three browser contexts verify Dashboard/Workspace consistency and pending/cache/tab behavior. No real model-selection claim is made from mocked responses. |

### Draft lifetime and research-data protection

Drafts persist during the mounted expert portal session, including item and portal-tab navigation. They are intentionally **not written to localStorage, sessionStorage, or the backend**. Leaving the portal, signing out/changing account, refreshing, or closing clears unsent drafts. A visible notice explains this lifetime and a beforeunload handler requests the browser's standard unsaved-change warning while any draft exists. Browser policy controls whether the warning is shown; it is not a durable save guarantee. SPA navigation has no blocking prompt, so the visible notice remains important. Submitted ratings restore from the backend after reopen. This choice avoids retaining sensitive teacher comments on a shared device or confusing them with final research ratings. The account/role key prevents draft reuse between identities.

## B. Seven previously untested workflows

| Workflow | Status | What was tested, what worked, and remaining limits |
|---|---|---|
| 1. Tutor modes/persistence | Passed for tested behavior | AI, Textbook and Dual change the visible answer/evidence content and retain response provenance. Inspection confirms these display tabs are component-local, defaulting to Dual on remount; they are not a persisted account preference. The separate Answer-Only/Reasoning-Visible study arm saves through the profile API and survives reload; enrolled_arm remains immutable. Browser profile switching/reload and real API persistence tests pass. Actual AI generation is unverified. |
| 2. Teacher code execution | Partially verified; real execution blocked | Authenticated teacher API dispatch preserves mocked success, compile error, and timeout results; anonymous calls are rejected. Browser Run Code displays returned test output on desktop/mobile. The real C/Python compiler suite fails closed with SANDBOX_UNAVAILABLE. The daemon pipe dockerDesktopLinuxEngine is absent and runner image trace-tutor-runner:1 is unavailable; Windows has no POSIX rlimit tier. A local image build attempt could not connect to Docker. No unsafe fallback was enabled. Real compiled output and timeout enforcement remain unverified here. |
| 3. Teacher profile editing | Passed for tested fields | Disposable full name/institution/language changes persist via PostgreSQL; empty full name is rejected without losing the saved value; role escalation is ignored. Browser save failure retains edits, retry succeeds, and reload retrieves saved values on desktop/mobile. Destructive account withdrawal, real avatar upload, and password changes were outside this repair's browser coverage. |
| 4. CVI submission/persistence | Fixed and verified | Submitted scores/comments/item/user identity restore correctly. Replacement changes only the acting expert's row. Independent experts keep independent rows. Complete valid rubrics are required; malformed/partial/out-of-range rubrics never create rows. Stale submissions return 409 and preserve the UI draft until explicit discard/reload. All writes used mocks or disposable PostgreSQL records. |
| 5. Grade saving/updating | Fixed and verified | Valid integer 0 and 100 save and update; empty, boolean, fractional, malformed and out-of-range inputs are rejected. Expert marks do not alter automated score_pct. Success/failure/conflict states preserve appropriate UI edits. Updating an older review now updates graded_at so the actual latest edit is displayed. |
| 6. Concurrent reviews | Fixed and verified for revision-aware clients | Previously there was no conditional stale-write check, and first creation had no existing row to lock. Transactions lock the expert identity for a rating or submission for a grade, compare revision tokens, and return 409 on stale edits. Real threaded PostgreSQL races confirm one winner/one conflict for two same-expert first ratings and competing grades, and two successes for different experts' ratings. Legacy clients omitting expected_revision remain supported and do not receive stale protection. |
| 7. Backend role isolation | Passed for targeted endpoints | Real authenticated student and anonymous API clients cannot read review queues/submissions/certification or submit ratings/grades; no rows are created. Teacher operations pass. Backend role/identity gates remain in force. A mobile student visiting /expert is redirected without an expert API fetch. Header search exposes no teacher-only records. |

### Additional confirmed defects and repairs

1. Server review validation previously substituted/clamped defaults and could silently accept invalid ratings or marks. It now requires five integer rubric values 1–4 and integer marks 0–100. This is validation tightening, not a change to exam scoring.
2. Updating ExpertGrade did not advance its auto_now_add timestamp, so an edited older row could remain hidden behind another expert's newer row. Explicit update timestamps and deterministic timestamp/ID ordering fix this.
3. Backup verification imported psycopg (v3), while the repository pins psycopg2. The first full suite failed with ModuleNotFoundError. Verification now uses the declared driver and closes its scratch connection before dropping the database. The existing real disposable backup/restore/verify/prune test passes.
4. Axe detected heading-level jumps in portal cards/code-answer sections. Optional SectionCard headingAs and correct portal h2/h3 levels repair semantic hierarchy while preserving styling.
5. ResourceExhaustionTests could reach hostile allocation/fork tests when a compiler existed but no isolated runtime did. Their assertions are preserved and now require the actual Docker tier. Runtime sandbox requirements were not reduced. The five ordinary compiler failures remain visible rather than being skipped or suppressed.

## C. Exact final verification

| Check | Result | Evidence/qualification |
|---|---|---|
| Frontend npm test | **106 passed, 0 failed**: 4 Node tests plus 102 Vitest tests across 6 files | [frontend-tests.log](frontend-tests.log). Baseline was 73; this task adds 33 frontend regressions: 27 portal tests, 3 review API tests, 3 model tests. |
| Focused PostgreSQL backend tests | **19 passed, 0 failed**, 5.408 seconds | 18 new teacher portal tests plus existing backup verification test. [targeted-backend-tests.log](targeted-backend-tests.log). |
| Full PostgreSQL Django suite | **488 run: 469 passed, 5 failed, 14 skipped**, 102.978 seconds; exit 1 | [backend-tests-final.log](backend-tests-final.log). No final errors. The targeted tests above are included in this suite; do not add their totals again. |
| Django configuration check | Passed, 0 issues | [final-checks.log](final-checks.log), local-only QA settings. |
| Frontend lint | Passed; zero errors/warnings, exit 0 | [frontend-lint.log](frontend-lint.log). |
| Type checking | Not supported by this JS project's scripts/configuration | No typecheck was invented or claimed. Build/lint do not substitute for static type checking. |
| Local production build | Passed, exit 0; 2,249 modules, 5.25 seconds | [frontend-build.log](frontend-build.log). Generated frontend/dist locally only. |
| Accessibility | Four axe scans, **0 violations** | CVI and code-marking views at 1440×1000 and 390×844; accessible refresh, score labels/pressed states, actual keyboard focus/activation checked. This is sampled automated coverage, not an all-app screen-reader certification. |
| Browser flows | Three contexts passed | Headless installed Edge: desktop teacher, mobile teacher, mobile student. [browser-results.json](browser-results.json), [browser-tests.log](browser-tests.log), [screenshots](screenshots/). No uncaught page errors in sampled flows. |
| Integration | Real DRF/PostgreSQL API persistence, validation, role and threaded concurrency checks passed; built frontend with mocked API contracts passed | There was **no live frontend-to-Django-to-provider/compiler end-to-end run**. Both layers were tested separately under isolated data conditions. |
| Patch hygiene | git diff --check passed, exit 0 | Only Git LF/CRLF conversion warnings; no whitespace errors. |
| Test cleanup | Passed | Read-only local pg_database inspection after tests found no disposable databases. No privilege grants were made. |

### Five full-suite failures

All expected an actual sandbox-backed result but received SANDBOX_UNAVAILABLE:

- tutor.tests.CompilerIntegrationTests.test_a_compile_error_is_reported_with_diagnostics
- tutor.tests.CompilerIntegrationTests.test_a_correct_program_passes_its_test_case
- tutor.tests.CompilerIntegrationTests.test_a_wrong_answer_is_not_a_pass
- tutor.tests.PythonCheckingTests.test_a_syntax_error_is_reported_with_a_line_number
- tutor.tests.PythonCheckingTests.test_valid_python_passes_the_syntax_check

The 14 skips comprise five Docker containment tests, four Docker resource-exhaustion tests, two POSIX process-group tests, two POSIX rlimit tests, and one opt-in cohort load test. They are not counted as passes. Actual Docker containment/timeouts and opt-in cohort stress remain uncovered in this environment.

Initial failures were investigated rather than concealed: the first broad run also had the backup-driver import error, now fixed. An early threaded test run passed its assertions but failed database cleanup because thread connections stayed open; tests now close every thread's connections and QA CONN_MAX_AGE is zero. Subsequent runs exit normally and remove the database. Browser harness corrections addressed a datalist's native combobox role and a mock missing passed_count; those were fixture/selector problems, not application bugs. [backend-tests.log](backend-tests.log) retains the initial full failure evidence.

### Isolation and reproducibility

The earlier CREATEDB obstacle did not reproduce: read-only system catalog inspection showed the configured **local** role already had CREATEDB and SUPERUSER. Neither privilege was granted or changed. Tests exclusively create/drop test_trace_teacher_qa_20261009; QA settings reject remote DB hosts and do not target the configured application database. Media, backups, Chroma/OCR/PDF test artifacts and caches are isolated, and provider keys are cleared only inside the QA process. Thread connections are closed before teardown. Test migrations applied only to the disposable database.

Commands from frontend: npm test; npm run lint; npm run build.

Commands from backend using the installed Django Python E:/projects/anaconda/envs/trace_tutor/python.exe:

- manage.py check --settings=trace_backend.qa_settings
- manage.py test assessment.tests.test_teacher_portal assessment.tests.test_sittings.BackupCommandTests --settings=trace_backend.qa_settings --noinput --verbosity=2
- manage.py test --settings=trace_backend.qa_settings --noinput --verbosity=2

Browser tooling: npm install --prefix docs/teacher-portal-qa/browser-runtime --no-save --package-lock=false playwright axe-core. Then start node docs/teacher-portal-qa/preview.mjs, run node docs/teacher-portal-qa/browser-checks.mjs, and stop that owned preview. The preview serves only the local build on 127.0.0.1:4174 and rejects every unmocked /api request with 501; it has no backend proxy. The harness uses fresh contexts, dummy tokens/users, intercepted APIs, and blocks external writes. Only the editor's existing Monaco CDN GET assets are allowed. No real research submission/grade/profile is touched. The in-app browser plugin had no available browser after documented troubleshooting, so local headless Edge was used instead. The owned preview was stopped after verification.

## D. Every task-authored source/test/configuration change

Paths below are relative to the repository. Existing changes in other files are recorded in baseline-status.txt and were not authored by this task.

| Path | Change |
|---|---|
| frontend/src/pages/ExpertPortal.jsx | Account-scoped per-item drafts, draft notice/unload warning, explicit submission handling, score formatting, accessible refresh, strict marks input, revision conflicts/recovery, preserved grade-edit baseline, semantic headings. |
| frontend/src/services/score.js (new) | Shared validated server-score formatter. |
| frontend/src/services/api.js | Optional expected_revision in review request bodies, including explicit null for first creation. |
| frontend/src/services/tutorModel.js | Pending provenance ignores old response metadata. Existing helper preserved. |
| frontend/src/components/TutorPanel/AnswerOnlyPanel.jsx | Loading-aware label/cache handling and accessible loading status. |
| frontend/src/components/TutorPanel/ReasoningTracePanel.jsx | Same provenance/status repair for the reasoning view. |
| frontend/src/pages/Workspace.jsx | Clear stale response and enter pending state before asynchronous preflight. |
| frontend/src/components/ui/index.jsx | Optional SectionCard headingAs; existing default and visual classes retained. |
| backend/assessment/views.py | Strict integer validation, revision metadata/checks, transaction locks, explicit updated grade timestamps and deterministic latest-review ordering. |
| backend/assessment/management/commands/backup_study.py | Use pinned psycopg2 and close scratch verification connection. |
| backend/tutor/test_sandbox.py | Require actual Docker isolation before resource-exhaustion tests; existing assertions retained. |
| backend/trace_backend/qa_settings.py (new) | Local disposable database, process-local provider/log suppression, isolated caches/media/backups, zero persistent DB connections. Not production settings. |
| backend/trace_backend/qa_runner.py (new) | Route Chroma/OCR/PDF test artifacts to ignored QA directories. |
| backend/assessment/tests/test_teacher_portal.py (new) | 18 real isolated API/validation/persistence/role/concurrency regressions. |
| frontend/tests/expert-portal.test.jsx (new) | 27 state, validation, failure, formatting, accessibility, draft and conflict regressions. |
| frontend/tests/review-api.test.js (new) | 3 request-contract/revision/error regressions. |
| frontend/tests/tutor-model-labels.test.jsx | 3 new pending/cache/teacher-mode regressions; existing tests retained. |

New evidence and harness files in docs/teacher-portal-qa:

- REPORT.md (this report); .gitignore (ignore temporary tooling, test artifacts and baseline copies); baseline-status.txt (initial working tree).
- inspect_test_database.py (read-only local catalog discovery); preview.mjs (API-blocking localhost static server); browser-checks.mjs (Edge/axe isolated regression harness); browser-results.json (structured final results).
- frontend-tests.log; frontend-lint.log; frontend-build.log; targeted-backend-tests.log; backend-tests.log; backend-tests-final.log; browser-tests.log; final-checks.log.
- screenshots/desktop-teacher-cvi.png; screenshots/desktop-teacher-missing-score.png; screenshots/desktop-teacher-marking.png; screenshots/desktop-teacher-workspace.png.
- screenshots/mobile-teacher-cvi.png; screenshots/mobile-teacher-missing-score.png; screenshots/mobile-teacher-marking.png; screenshots/mobile-teacher-workspace.png; screenshots/mobile-student-workspace.png.

Ignored generated directories baseline/, browser-runtime/, and test-artifacts/ contain local reference copies, temporary QA dependencies, and disposable test output. Generated frontend/dist is build output, not a published site.

**Dependencies/migrations/configuration:** No application dependency, application package manifest/lockfile, database schema, migration, provider key, deployment configuration, or production environment change was introduced by this task. Temporary QA-only packages are Playwright 1.64.0 and axe-core 4.14.0. Optional expected_revision and returned revision tokens are additive API fields; invalid review inputs are now rejected instead of silently coerced. Existing legacy valid clients remain compatible.

**Remaining risks/limits:** Legacy clients/tabs that omit expected_revision can still overwrite another edit; future rollout should refresh clients, or separately coordinate mandatory revisions. CVI drafts are memory-only with the explicitly described leave/refresh behavior. Browser reload warnings depend on browser policy. Content-based rating revisions detect differing current content, not an audit history of identical edits. There is no new durable draft store or research audit schema. Real provider output, real contained compiler execution/timeouts, Linux-only sandbox checks and cohort load remain unverified. Existing pre-task changes must be reviewed separately before packaging a release.

## E. Deployment readiness

The requested repairs and targeted review/data-integrity checks are verified locally. **Complete deployment readiness is not established** while the five sandbox integration failures and containment coverage remain unresolved.

Before any separately authorized future deployment:

1. Make the intended isolated Docker daemon/image available in a local test environment and rerun the full suite. Require the five compiler tests to pass, and run the Docker containment/resource tests within their intended isolated tier. Do not lower SANDBOX_REQUIRED_TIER.
2. Run an isolated full browser→Django integration smoke test with disposable teachers/students; verify real sandbox success/error/timeout handling and, if credentials/test policy permit, actual model provenance. No production records should be used.
3. Review the full pre-existing working tree together with this task's patch; confirm integer grading policy, account-scoped draft lifetime, and a rollout plan for older clients without revision fields.
4. Confirm backups and restoration in the target operating environment, and run relevant Linux-only checks and opt-in cohort load safely before asserting those properties. This task's disposable backup verification already passed.
5. Obtain the user's separate explicit deployment instruction. A successful build or passing targeted tests is not deployment authorization.

## F. Final confirmation

**DEPLOYMENT STATUS: NOT DEPLOYED**

**PRODUCTION STATUS: UNCHANGED BY THIS TASK**

**AWAITING EXPLICIT USER AUTHORIZATION FOR DEPLOYMENT**
