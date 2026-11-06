# Teacher review queues — deployed 6 November 2026

The ten authorized teachers each have six primary item assignments. The 237 currently
submitted papers from SIM-001 through SIM-060 have one primary marker each. Seven
teachers have 24 submissions and three have 23. SIM-007, SIM-027 and SIM-053 have no
Withdrawal submission, so no submission or grade was manufactured for them.

| Teacher | Items assigned / completed / remaining | Submissions assigned / completed / remaining |
|---|---|---|
| Aiyesha Anwar | 6 / 1 / 5 | 24 / 1 / 23 |
| Md. Asique Iqbal | 6 / 0 / 6 | 24 / 0 / 24 |
| Abu Motaleb | 6 / 0 / 6 | 24 / 0 / 24 |
| Mohammed Alamgir Hossain | 6 / 0 / 6 | 24 / 0 / 24 |
| Md. Abu Raihan | 6 / 0 / 6 | 24 / 0 / 24 |
| Md. Rokibul Islam | 6 / 0 / 6 | 24 / 0 / 24 |
| Md. Abullah Al Mamun | 6 / 0 / 6 | 24 / 0 / 24 |
| M. K. Alam Shamim Akanda | 6 / 6 / 0 | 23 / 18 / 5 |
| Md. Anisur Rahman | 6 / 0 / 6 | 23 / 5 / 18 |
| Md. Abdul Kadir | 6 / 0 / 6 | 23 / 0 / 23 |

Counts reflect the deployment snapshot. Assigned is the default scope. Earlier work
shows all previously completed work by the signed-in teacher, including work outside
their primary quota. More exposes the complete item bank or submission list and permits
additional independent ratings/grades. Drafts survive scope changes and refreshes.

All 24 existing completed cohort grades retain their original teacher as primary owner.
Abu Raihan's 11 legacy grades outside this cohort remain available in Earlier work.
Item ownership preserves earlier ratings where the six-item quota permits. Overlapping
ratings and Shamim Akanda's eight historical item reviews remain intact in Earlier work.
The allocation never edits or duplicates grade/rating rows. A colleague's grade no longer
prefills another teacher's marks/feedback or counts as that teacher's completed review.
Conditional updates protect each expert's own revision; More does not change primary ownership.

Assignments are persisted in three new assessment tables (migration 0010) and visible
read-only in Django admin. `allocate_teacher_reviews` previews allocation by default;
`--apply` saves it atomically. A repeat preserves existing ownership. Newly submitted
papers after this snapshot are not automatically added by this initial allocation.

Validation: 56 backend tests; 119 frontend tests plus six Node utility tests; frontend
lint; isolated Linux production build. Authenticated live HTTPS requests checked each
teacher's six item assignments, 23/24 submission assignments, own grade isolation, and
all prior feedback. All 44 emitted JavaScript/CSS assets returned correct content types.
The served index references the new bundle. Fingerprints of existing cohort submissions,
the ten teachers' grades and their ratings were unchanged. Temporary verification tokens
were removed. Browser discovery returned no available browser, so no visual browser
inspection is claimed.

Staging: `/tmp/trace-assignments-20261106-6353185188ac`.
Private source/data backup, allocation preview and published verification report:
`/srv/trace-tutor/deployment-backups/review-assignments-20261106-bba15032ed47`.
