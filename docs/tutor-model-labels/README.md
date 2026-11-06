# AI tutor model labels: implementation and release

Status: DEPLOYED successfully on 9 October 2026 (Asia/Dhaka) to https://trace.musfiqurtuhin.me, using shihab@89.167.59.65 and /srv/trace-tutor. The earlier staging blocker is resolved without changing any production database permissions. Only the 11 verified source/helper/test files in release.json and generated frontend assets were published. All 62 backend tests and 38 frontend tests, lint, build, Django checks and guarded public/runtime verification passed. No rollback was needed and no paid AI generation request was made.

Verified rollback backup: /srv/trace-tutor/deployment-backups/tutor-model-labels-20261008T201126Z (directory timestamp is UTC; local deployment date is 9 October). It includes original changed sources, frontend dist, protected environment copies, the PostgreSQL dump, OCR cache, vector store and uploaded media. The database dump restored successfully into a disposable private cluster and all eight recorded table counts matched. backup-checksums.json verifies backed-up files. Original production environment files and PM2 environment fingerprints remain unchanged.

Public Dashboard, Workspace, Assessment and health routes returned 200 and their frontend assets matched the new build. Credential-free backend dashboard verification returned provider=openai, primary_model=gpt-5-mini, fallback_models=[], configured=true. The deployed shared formatter produced OpenAI · gpt-5-mini for both Dashboard and Workspace. No browser connection was available for a fresh visual production check. No student had an active restricted paper at verification time; active pre-test blocking, submission unlocking and draft preservation passed the isolated regressions. No live paid-generation request was attempted, as instructed.

## Verified configuration and root cause

The inspected deployment selects OpenAI with primary alias gpt-5-mini and no configured fallback generation models. The most recent recorded HELP_REQUEST marked live and computed records gpt-5-mini at 2026-10-08 15:47:07 UTC (21:47:07 Asia/Dhaka). No new paid model request was made for this investigation. The code records the selected request model alias, not a provider-resolved revision; a precise underlying model revision cannot be verified from this record.

Dashboard previously read llm_model from curriculum status, which dynamically uses trace_backend.llm. Workspace panels defaulted to the literal Gemini before a response. Dashboard status describes the same generation configuration used by Workspace and Assessment, not a second generation model. Gemini separately handles OCR/embeddings; the inspected embedding model is gemini-embedding-001.

LLM_PROVIDER chooses openai, gemini, or auto (OpenAI when its key is present; otherwise Gemini). OPENAI_MODEL/GEMINI_MODEL set primary names. OPENAI_FALLBACK_MODELS/GEMINI_FALLBACK_MODELS configure same-provider model chains. This fix does not change routing, aliases, temperatures, caching policy, or generation instructions.

## Implementation

llm.public_metadata returns only provider, primary_model, fallback_models and configured. The authenticated dashboard adds this metadata outside its progress cache; existing no-store responses prevent HTTP caching. Workspace obtains it through its existing dashboard/progress request, adding no API call and leaving the availability store/hook untouched.

The shared frontend formatter displays configured primary provider/model before a response. Successful response metadata can display a different selected model, a configured fallback, or a cached answer, while retaining the configured primary in the badge tooltip. Provider metadata is captured with newly generated results and preserved through caching and both arms. Legacy cached answers have unknown provider, which is not inferred from current configuration. Missing/unconfigured metadata uses AI Tutor. Failed generation displays Textbook fallback without claiming a model generated the textbook answer. Assessment reuses the same formatter to remove its remaining hardcoded default.

## Changed/added files in this task

- backend/trace_backend/llm.py
- backend/logging_app/views.py
- backend/tutor/views.py
- backend/tutor/test_model_metadata.py
- frontend/src/services/tutorModel.js
- frontend/src/pages/Dashboard.jsx
- frontend/src/pages/Workspace.jsx
- frontend/src/pages/AssessmentPage.jsx
- frontend/src/components/TutorPanel/AnswerOnlyPanel.jsx
- frontend/src/components/TutorPanel/ReasoningTracePanel.jsx
- frontend/tests/tutor-model-labels.test.jsx
- docs/tutor-model-labels/README.md
- docs/tutor-model-labels/inspect-runtime.py
- docs/tutor-model-labels/release.json
- docs/tutor-model-labels/deploy.py
- docs/tutor-model-labels/verify.py

Deployment-only safeguards: preflight.py, test-release.py, backup-release.py, check-unchanged.py and final-audit.py. The application release.json contents remain exactly the 11 localhost-verified source/helper/test files; these safeguards are uploaded to /tmp only.

Other existing workspace edits are preserved and excluded from this release bundle.

## Validation

npm test: 38 passed (34 Vitest and 4 existing assessment tests).
npm run lint: passed without errors/warnings.
npm run build: passed.
Backend: 62 passed, including model metadata/security, cache provenance, provider routing, existing dashboard/availability/submission lifecycle and hint-policy tests. All model generation in the new backend tests is mocked. Django system checks passed.

Backend command, run from backend:
E:/projects/anaconda/envs/trace_tutor/python.exe manage.py test tutor.test_model_metadata tutor.tests.LlmProviderTests tutor.tests.ModelConfigTests logging_app.test_tutor_availability logging_app.tests assessment.tests.test_sittings.SittingLifecycleTests tutor.test_hint_policy --noinput

No TypeScript/type-check script exists. Visual desktop/mobile browser verification was unavailable in this session; existing responsive layout is unchanged.

## Exact deployment steps (run only when deployment is authorized)

These are the commands used for this release, recorded for review. Do not rerun the deployment now: it has already succeeded, and the source-baseline guard will correctly refuse a second application of the same release. They use the existing server, SSH identity and PM2 process. Do not run git reset or overwrite the entire checkout: the server has other intentional changes.

The original runner reused production DB credentials and Django tried to create test_<database> on the production cluster. The new runner uses installed PostgreSQL 16 initdb/pg_ctl binaries as the unprivileged shihab user. Docker socket access and passwordless sudo were unavailable; no CI test environment was found. No privileged provisioning is needed. Each run gets a 0700 temporary directory, a distinct cluster/data directory, a private Unix socket, no TCP listener, SCRAM authentication, random temporary credentials and a dedicated non-superuser test role with database-creation permission ONLY in that disposable cluster. Before Django setup/tests, assertions check resolved database engine, socket, port, role and database names against the private configuration and reject production connection identities. The provisioning connection's data directory and Django's actual database/user/socket transport are checked too. Test API keys are blank; generation calls in these regressions are mocked. The test database and cluster are stopped and deleted afterward. Final audit confirmed the production role still has no CREATEDB.

~~~powershell
ssh -i "$env:USERPROFILE/.ssh/trace_tutor" -o BatchMode=yes shihab@89.167.59.65 "mkdir -p /tmp/trace-tutor-model-release"
if ($LASTEXITCODE -ne 0) { throw 'Release directory failed' }
scp -i "$env:USERPROFILE/.ssh/trace_tutor" docs/tutor-model-labels/release.json docs/tutor-model-labels/deploy.py docs/tutor-model-labels/verify.py docs/tutor-model-labels/preflight.py docs/tutor-model-labels/test-release.py docs/tutor-model-labels/backup-release.py shihab@89.167.59.65:/tmp/trace-tutor-model-release/
if ($LASTEXITCODE -ne 0) { throw 'Release upload failed' }
ssh -i "$env:USERPROFILE/.ssh/trace_tutor" -o BatchMode=yes shihab@89.167.59.65 "/srv/trace-tutor/venv/bin/python /tmp/trace-tutor-model-release/preflight.py"
if ($LASTEXITCODE -ne 0) { throw 'Production preflight failed' }
ssh -i "$env:USERPROFILE/.ssh/trace_tutor" -o BatchMode=yes shihab@89.167.59.65 "python3 /tmp/trace-tutor-model-release/deploy.py"
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed; inspect the reported error' }
ssh -i "$env:USERPROFILE/.ssh/trace_tutor" -o BatchMode=yes shihab@89.167.59.65 "/srv/trace-tutor/venv/bin/python /tmp/trace-tutor-model-release/verify.py"
if ($LASTEXITCODE -ne 0) { throw 'Public verification failed' }
~~~

The deploy script checks exact old source before any write, creates a timestamped staging/backup directory under /srv/trace-tutor/deployment-backups/tutor-model-labels-*, builds in isolation using the server's current frontend plus this bundle, runs npm ci, tests and lint, then builds production assets. It runs backend regressions using staged code and the private disposable PostgreSQL cluster. Only after these checks pass does it back up and byte/hash-verify production sources/dist, use the existing backup_study command with keep=0 to take a read-only database/file-store backup without pruning older backups, restore-verify the dump in another private cluster, save protected environment copies, and record backup checksums. Then it applies only the listed release files. It runs Django checks; restarts trace-tutor through PM2 without changing its environment; retains older hashed assets; replaces index.html last; restarts for static-file discovery; runs public/runtime verification inside the rollback guard; and saves PM2. Exceptions during publishing restore backed-up sources and original assets/entry point and restart and health-check the prior version. A mismatched old source aborts and must be reviewed rather than bypassed. No automatic database restore is performed: this release changes no production database schema or participant records, and restoring a database could overwrite legitimate new activity.

No production database migration, API key change, provider switch or generation-setting change is required. The verify script checks unchanged environment fingerprints, public pages and asset hashes, then checks safe dashboard metadata through the backend view using APIRequestFactory/force_authenticate without reading or creating student credentials. It evaluates the shared frontend formatter against that production metadata. Its verification transaction rolls back cache/telemetry writes. It checks an existing locked participant if one is currently present; model and embedding requests are explicitly blocked for that policy check. Isolated regressions cover the active pre-test scenario otherwise. No paid AI-generation request is performed. Fresh visual production verification and a paid generation smoke test remain unperformed; the user already verified the labels visually on localhost. Hard-refresh the live browser to see the release; a cached/secondary response may legitimately show its response model instead.
