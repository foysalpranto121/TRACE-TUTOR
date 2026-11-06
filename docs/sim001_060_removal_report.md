# SIM-001–SIM-060 removal

Completed on 2026-10-25 (Asia/Dhaka), at the user's explicit request to remove all 60 session-imported students.

Removed from the live database:

- 60 student accounts and 60 participant profiles.
- 237 exam submissions, including generated answers.
- 120 associated import/audit logs.
- 5 teacher grades linked to those submissions.

Total: 482 database rows. Before deletion, each account was verified against its original import receipt. The deletion ran in a transaction, and fingerprints confirmed that unrelated users, profiles, submissions, logs, and teacher grades were unchanged.

A private backup remains on the server at:

`/srv/trace-tutor/deployment-backups/remove-sim001-060-20261025-5f66d46b23ee`

The directory contains the affected-row fixture, SHA-256 manifest, and removal receipt. Fixture SHA-256: `d3969ddcea5fbe7a0ed6a5bd974f7c6caaa7ae377b418e1a028246c6f1d61e80`.

Earlier import reports document historical imports; they do not represent the current live database state.

Later on 2026-10-25, the user requested a new set of 60 learner scenarios with scheduled phases and varied code. New records were created from the archived source summaries; the old teacher grades were not restored. See `timing_protocol_verification.md` for the current state.
