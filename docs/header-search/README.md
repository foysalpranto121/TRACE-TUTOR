# Functional header search

Implemented and tested locally on 9 October 2026 (Asia/Dhaka), then deployed after explicit authorization to https://trace.musfiqurtuhin.me. See deployment/README.md for the exact release, verified backup, test results and live verification limits. No backend functionality or migration was added; production environments/data/permissions were preserved.

## Root cause

The shared AppShell header contained an uncontrolled input with a placeholder, but no query state, input/keyboard handlers, form submission or results UI. The field was unfinished. Separately, Workspace read its problem query parameter only when initializing state; changing a search destination while already on that page could change the URL without selecting the corresponding task.

The existing curriculum search API is a staff-only OCR inspection tool. Assessment item requests return protected paper content and open/refresh a paper sitting. Neither endpoint is appropriate for student suggestions, and their permissions and behavior remain unchanged.

## Behavior and data

HeaderSearch reuses NCTB_PROBLEMS, the public practice catalogue already used by Dashboard and Workspace. The search catalogue contains task/topic titles, chapter/category, task language/type, available status and public keywords. It does not include starter code, test cases, answers or assessment papers. Current public practice tasks are available to authenticated Workspace roles; there are no practice progression locks in the existing catalogue. Any supplied locked entry is displayed as locked and cannot navigate by mouse, touch or keyboard. Protected assessment tasks are excluded entirely.

Search matches task titles/IDs, topic names, chapters, language/type, existing public English/Bengali descriptions and difficulty keywords. It trims/collapses whitespace, ignores letter case and supports partial matches. Matching task titles take priority over broader keyword matches. Topics open the first available practice task for that topic at the existing /workspace?problem=<id> destination; no new topic page or duplicate backend search is introduced.

Typing shows an accessible combobox/listbox dropdown. Enter opens the highlighted result, or the first available match; during initial loading it shows the checking status. Arrow keys move the highlight and scroll it into view. Escape, outside pointer interaction and focus leaving the search close suggestions. Clearing resets them. No matches display exactly "No matching topics or tasks found." Catalogue construction is asynchronous/coalesced and failure has visible retry feedback. Search itself makes no API requests, so server-side debouncing and new API error handling are unnecessary. Results always derive from the latest query; asynchronous completion cannot reopen a dismissed dropdown or revive stale suggestions.

The search stays in the shared header on Profile, Dashboard, Workspace and Assessment. Workspace synchronizes task URL changes and browser Back using the existing state-reset convention. A different task resets code/compile output as its existing task selector does. Selecting the current task retains edited code. The mounted tutor input is preserved, and search does not change tutor availability/model metadata or send tutor requests.

Mobile search remains visible and flexible; the dropdown width is constrained to the field/viewport, text wraps and the results scroll within a bounded height. Touch selection and existing sidebar navigation are covered by tests.

## Complete modified/added files for this task

- frontend/src/components/Layout/AppShell.jsx — replaces the inert input with the shared search component.
- frontend/src/components/Layout/HeaderSearch.jsx — accessible interaction, statuses, selection and responsive results.
- frontend/src/services/learningSearch.js — shared public catalogue construction, normalized matching and ranking.
- frontend/src/pages/Workspace.jsx — synchronizes task query navigation without remounting the tutor.
- frontend/tests/header-search.test.jsx — 35 search/integration/security/mobile regressions.
- docs/header-search/README.md — this implementation/validation report.

All unrelated pre-existing workspace modifications were preserved. Generated frontend/dist is a local build artifact, not a production publication.

## Validation

- npm test: 73 passed (69 Vitest + 4 existing assessment tests), including all 35 new search tests and the existing model-label, tutor locking, draft preservation and quiet-refresh regressions.
- npm run lint: passed without warnings/errors.
- npm run build: passed.
- Backend: 35 passed in a disposable LOCAL PostgreSQL test database. Suites: curriculum.tests.CorpusAccessTests, assessment.tests.test_access.ExamPaperAccessTests, assessment.tests.test_access.EndpointPermissionTests, logging_app.test_tutor_availability, tutor.test_model_metadata.
- Django system checks: passed, zero issues.

The successful backend run used a fresh process with model API credentials blank and both synchronous/asynchronous httpx transports blocked; no environment files were edited. One existing staff corpus test made a single unintended Gemini embedding batch request during the initial run before it was stopped. No AI-generation request occurred. The complete successful rerun made no external model requests, and its local test database was destroyed afterward.

No browser was available for screenshots or actual desktop/mobile pixel inspection. Narrow-viewport tests verify visible controls, touch selection and navigation in jsdom; they do not prove pixel layout. API-error coverage exercises catalogue-loader rejection/retry because this search requires no backend API. Locked-row coverage uses a locked catalogue fixture; real protected paper access is covered by backend access tests, and assessment content is never downloaded by the search.

## Deployment readiness

The explicitly authorized production deployment is complete. Only the five source/helper/test changes listed above and their rebuilt frontend assets were published. Deployed backend/environment/security settings were retained; no database migration or new API was required. The final deployment report is in deployment/README.md. Local deployment-only tools/manifest files under docs/header-search/deployment were uploaded to /tmp, rather than applied to the production application.
