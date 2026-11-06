# Tutor pre-test restriction UI fix

Workspace previously discovered the no-AI policy only when queryTutor failed. Both tutor panels cleared their drafts synchronously before awaiting the request. The restriction lived in the request error state, so remounting removed it.

The dashboard now includes live tutor_availability from the same sittings.blocking_paper function used by the tutor endpoint. This field is computed outside the cached progress summary and HTTP responses use Cache-Control: no-store. No assessment items are fetched just to discover eligibility, since fetching items opens a sitting.

Workspace has one availability store shared by both panels. Initial dashboard loading also supplies its progress snapshot. Concurrent checks are coalesced, old responses are ignored after assessment invalidation or a policy rejection, and submission checks eligibility again before setting the AI generating state. Status refreshes occur on assessment changes, tab focus/visibility, cross-tab storage events and a 30-second interval while visible. All unknown/error/checking states block submission and support retry.

The persistent notice uses the requested pre-test wording, with equivalent wording for withdrawal tasks. It remains visible during a locked status refresh. A shared controlled form keeps the question in Workspace state through status changes and tutor-mode switches. Failed requests never clear it; accepted requests clear only the submitted draft.

Changed or added files:
- backend/logging_app/views.py
- backend/logging_app/test_tutor_availability.py
- frontend/src/pages/Workspace.jsx
- frontend/src/components/TutorPanel/AnswerOnlyPanel.jsx
- frontend/src/components/TutorPanel/ReasoningTracePanel.jsx
- frontend/src/components/TutorPanel/TutorAvailabilityNotice.jsx
- frontend/src/components/TutorPanel/TutorQuestionForm.jsx
- frontend/src/hooks/useTutorAvailability.js
- frontend/src/services/api.js
- frontend/src/services/tutorAvailability.js
- frontend/src/services/assessmentEvents.js
- frontend/tests/workspace-tutor-availability.test.jsx
- frontend/tests/tutorAvailability.test.js
- frontend/tests/assessment-phase-refresh.test.mjs (existing lint issue only)
- frontend/vitest.config.js
- frontend/eslint.config.js
- frontend/package.json
- frontend/package-lock.json
- docs/tutor-pretest-ui-fix.md

Validation:
- npm test: 26 passed (22 component/store regressions and 4 existing assessment regressions).
- npm run lint: passed, no warnings.
- npm run build: passed.
- Focused backend run: 36 passed, including 6 new dashboard availability tests.
- Broader dashboard/sitting run: 52 of 53 passed. The unrelated backup verification test fails importing psycopg; the installed project driver is psycopg2.
- Django system checks: passed. The project has no TypeScript/type-check script.

Limitations:
- Mobile controls and responsive structure are covered by DOM tests. Visual browser verification was unavailable in this session.
- Other-device status changes can take up to 30 seconds to appear; every submission rechecks the server and the existing tutor endpoint remains authoritative.
- The draft is held in the current Workspace instance; drafts are not persisted across a full page reload.
- Deployed backend and frontend together on 2026-10-08 to https://trace.musfiqurtuhin.me. All 26 frontend tests, lint, production build and Django checks passed on the server. Public page/assets and read-only authenticated dashboard policy checks passed, including an active student lock. Rollback backup: /srv/trace-tutor/deployment-backups/tutor-availability-20261008T152026Z.

## Quiet refresh follow-up

On 2026-10-08, changed focus, visibility and periodic availability checks to refresh in the background without replacing a confirmed available/locked state with the checking notice. Unchanged responses do not republish state. Assessment invalidations, initial loading and explicit checks still block as appropriate; errors fail closed and requests await any queued fresh check. Changed only the availability store/hook and their regression tests. All 31 frontend tests, lint, build, server checks and public deployment verification passed. Deployed with rollback backup /srv/trace-tutor/deployment-backups/tutor-quiet-refresh-20261008T162412Z.
