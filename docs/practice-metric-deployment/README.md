# Practice completion metric version 2 deployment

Published to https://trace.musfiqurtuhin.me on 23 November 2026. Both backend and frontend were published using the existing SSH / PM2 deployment. GitHub was not changed.

The 21 release files matched their original production baselines before publication. Only those reviewed sources and the generated frontend build were published. Previous hashed assets remain available. Environment files, production dependency manifests, database schema and existing study records were not changed. New practice runs now create version 2 server records. Historical successes retain their original meaning.

Rollback backup: `/srv/trace-tutor/deployment-backups/practice-metric-v2-20261123T164009Z`. This contains the original sources and frontend build; no database restore is needed for this source-only release. The publisher automatically restores sources and the old entry point and restarts PM2 if publication verification fails. Publication succeeded without rollback.

Staging used a separate candidate directory, the local tested frontend dependency lockfile, and a disposable PostgreSQL 16 cluster with a private Unix socket and no TCP listener. Production credentials and provider keys were not used by these tests. The test cluster was stopped afterward. Staging-only test dependencies were not installed in the live app.

Validation: 5 Node tests and 76 Vitest tests passed; frontend lint and production build passed. Backend staging ran 166 tests: 165 passed and one existing Windows MinGW path diagnostic test failed on Linux. Repeating that single test with the original production runner reproduced the identical failure; the relevant function was unchanged by this release. New practice metric tests passed. Earlier local Windows validation also passed, as reported in the implementation conversation.

Live verification passed: Django checks, database health, login/dashboard/workspace routes, byte hashes of all newly emitted public assets, version 2 authenticated dashboard fields, rejection of client-created CODE_RESULT events, and real C/HTML server checks. Production verification used an existing token internally without exposing it. The compiler checks called the runner directly and did not create practice records or student accounts.

Refresh existing browser tabs with Ctrl+Shift+R to load the updated client. The dashboard reports test-passed tasks, not independent authorship. Existing historical counts can appear separately and do not become version 2 completions automatically.

See `PUBLISHED.json` for the deployment receipt and `STAGING_VERIFIED` for the recorded staging limitation. Deployment helper scripts are retained here for review. The source release payload contains code only.
