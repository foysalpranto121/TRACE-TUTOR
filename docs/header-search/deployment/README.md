# Header search deployment

Deployed successfully on 9 October 2026 (Asia/Dhaka) to https://trace.musfiqurtuhin.me, using shihab@89.167.59.65 and /srv/trace-tutor. PM2 process trace-tutor runs the existing venv/bin/waitress-serve from /srv/trace-tutor/backend. No new deployment architecture was introduced.

## Exact application release

- frontend/src/components/Layout/AppShell.jsx
- frontend/src/pages/Workspace.jsx
- frontend/src/components/Layout/HeaderSearch.jsx
- frontend/src/services/learningSearch.js
- frontend/tests/header-search.test.jsx
- Generated frontend/dist assets and index.html.

No backend code, migrations, dependency manifests, environments, keys or uploaded files were published. The five files exactly match the localhost-verified implementation. Source-baseline checks validated both existing targets before replacement, and 15 dependency fingerprints confirmed the required code/dependencies were already deployed. Both checkouts have unrelated uncommitted changes; no git reset, pull or broad checkout replacement was performed. The build used the existing production frontend plus these five release files, excluding unrelated local modifications. npm ci was run only in temporary build staging, without dependency upgrades or live package changes.

## Checks performed

- Local frontend: 73 passed (69 Vitest + 4 assessment Node tests), lint and production build passed.
- Staged production frontend: the same 73 tests, lint and production build passed, including all 35 header-search regressions.
- Staged production backend: 83 tests passed. Coverage includes model metadata/routing, hint policy, dashboard/availability, assessment lifecycle/progression/permissions and staff-only curriculum access.
- Django checks passed with zero issues before testing and before service restart.
- The private PostgreSQL 16 test cluster ran under shihab with separate random credentials, a non-superuser dedicated test role, a private Unix socket and no TCP listener. Resolved settings and actual connections were checked before testing. Production credentials were never used to create a test database. API keys were blank in test processes and external synchronous/asynchronous model HTTP transports were blocked. No model/embedding/generation request was issued by these deployment tests.

## Verified backup and publication

Backup: /srv/trace-tutor/deployment-backups/header-search-20261008T212814Z. The timestamp is UTC; the local date is 9 October.

Original changed sources and frontend dist were copied and byte/hash verified. The existing backup_study command with keep=0 backed up the production database, OCR cache, vector store and uploaded media without pruning older backups. Protected environment copies were saved. The database dump restored successfully into another disposable private cluster; all eight recorded table counts matched. backup-checksums.json records backup integrity.

The existing guarded workflow applied only the release files, ran Django checks, restarted PM2 without --update-env, published assets before index.html, retained prior hashed assets, restarted to refresh static-file discovery, and ran verification inside the automatic rollback guard. It then saved PM2. No rollback was required. Automatic rollback restores original sources and frontend assets/entry point and restarts/health-checks PM2; it does not restore the production database, because this release changes no production data/schema and such a restore could overwrite legitimate new activity.

## Live verification

- Homepage, Profile, Dashboard, Workspace, a Workspace task deep link, Assessment and /api/health/ returned 200.
- Public HTML and required JS/CSS assets exactly matched the published build, including Profile/Dashboard/Workspace/Assessment chunks.
- Running the deployed catalogue logic confirmed case/whitespace-normalized loop matches: Loops & Accumulation, Sum of First N Natural Numbers, and Factorial of a Number. Destinations use existing /workspace?problem=<id> routes. A nonexistent query returned no matches.
- Component integration tests on the staged production frontend verified typing, clicking, Enter, arrow keys, Escape, retry/error handling, all four routes, narrow-screen pointer selection, locked/unauthorized results, same-page draft/editor preservation and browser Back behavior.
- PM2 was online, environment fingerprints unchanged, and no new critical Python/startup log errors appeared after deployment.
- Safe credential-free backend dashboard verification confirmed OpenAI / gpt-5-mini metadata and unchanged authoritative tutor availability. No student tokens were read or created. Verification cache/telemetry changes were rolled back in their local verification transaction.
- No currently locked participant was present for a live rejection check. Active pre-test restrictions and failed-request draft retention passed isolated backend/frontend regression tests.

No browser connection was available, so fresh authenticated browser clicking, browser-console inspection, mobile pixel layout and interactive reload checks remain unperformed. Public deep-link/asset checks and automated component navigation tests passed. The user had already visually verified the dropdown on localhost. No paid AI generation smoke test was made, per the standing instruction.

A CLI backup/check process emitted the existing code-sandbox configuration warning also seen in prior releases. No sandbox/backend settings changed; this search release did not verify compiler execution separately.

## Final state and follow-up

Only the reviewed search feature is published. The production database role still lacks CREATEDB, disposable PostgreSQL directories were removed, backup checksums passed the final audit and PM2 configuration was saved. Hard-refresh a signed-in live browser to load the release; inspect the dropdown/mobile layout and browser console for the visual checks unavailable in this session.

The scripts here are the existing guarded model-label workflow adapted for this release. They were uploaded only to /tmp/trace-tutor-header-search-release. Do not rerun deploy.py now: its exact old-source guard will correctly reject applying this same release twice. No additional infrastructure or credentials are required for this deployed feature.
