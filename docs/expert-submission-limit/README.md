Deployed on 23 October 2026 (Asia/Dhaka) to https://trace.musfiqurtuhin.me.

The expert submission endpoint silently returned only its newest 100 rows. This
hid older participants, including SIM-001 through SIM-034. The endpoint now returns
all submissions in descending submission-time order, with descending primary key
as a stable tie breaker. The existing frontend already displays every returned row.

Only the focused query and its docstring in backend/assessment/views.py were
published. No frontend build or migration was required. Existing worktree changes
were preserved and were not included in this deployment.

All 19 teacher portal tests passed in a disposable, unprivileged PostgreSQL 16
cluster with no TCP listener. The new regression creates 105 submissions with tied
timestamps and verifies that the oldest participant and existing expert grade are
included in the expected order. The cluster and disposable test data were removed.

Authenticated HTTPS verification returned 248 submissions instead of 100,
covering 65 participants, including all 34 SIM codes below SIM-035. All returned
submission IDs and their order matched the database. Submission, grade and rating
row fingerprints were unchanged. Public health and database checks passed.

The previous application file and verification records are preserved at
/srv/trace-tutor/deployment-backups/expert-queue-20261022T183819Z.
The deployment script automatically restores that file if critical checks fail.
No database restore or reset was performed. Only PM2 process trace-tutor restarted.

See tested-manifest.json and deployed.json for source hashes and verification data.
