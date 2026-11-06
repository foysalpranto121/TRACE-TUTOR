# Expert portal QA release — 26 October 2026

Published at **18:34 Asia/Dhaka** to https://trace.musfiqurtuhin.me/expert.

The existing production frontend was used as the build baseline. Only `src/pages/ExpertPortal.jsx`, `src/components/Layout/AppShell.jsx`, `src/services/assessmentTiming.js`, and the new `src/services/expertText.js` were published. Source hashes are recorded in `release.json` and `PUBLISHED.json`. Other local changes were excluded; package manifests, backend files, environment variables, and participant records were unchanged.

Isolated Linux staging passed 112 tests (6 Node + 106 Vitest), lint, and build. Publication verified a complete backup, checked production source hashes again, retained old assets, published the new assets before atomically replacing the index, and restarted only PM2 `trace-tutor` so WhiteNoise discovered the new files. All 44 JavaScript/CSS assets matched their staged bytes over HTTPS and had correct MIME types. Home/expert HTML matched the staged index and API database health remained OK. The publication script includes automatic rollback on verification failure; none was required.

Backup: `/srv/trace-tutor/deployment-backups/expert-qa-20261026-419fe54c6543`.

Staging: `/tmp/trace-expert-qa-20261026-a76f29`.

`verify-public.py` independently checks the public index, expert chunk containing the grade draft notice, and API health. This verification uses no authentication and makes no data writes. Browser automation was unavailable; no interactive live grading or keyboard behavior is claimed as tested.

Do not rerun `publish.py`: its original-source guards intentionally reject applying this release a second time.
