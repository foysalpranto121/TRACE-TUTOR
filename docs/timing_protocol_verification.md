# Assessment timing and 60 learner scenarios

Completed and verified on 2026-10-25 (Asia/Dhaka).

## Live application behavior

- Pre-test submission unlocks Post immediately.
- Transfer requires a Post submission and seven days since Post first opened.
- Withdrawal requires a Transfer submission and fourteen days since Transfer first opened.
- Late submissions are accepted. Retakes do not reset first-opening wait anchors.
- Students see availability dates in Dhaka time; periodic refresh preserves unsaved answers.
- Teachers see opening/submission timestamps, elapsed calendar time per paper, total completion time, and participation window.
- The new read-only Assessment Timeline section is available in Django admin. Timeline data is included in personal exports and erased when a participant leaves the study.

## Recreated scenarios

60 generated learner records and 237 submissions are present. Original supplied profile fields, summary data and exam scores were retained. All 237 submission timestamps are unique and fall within 1 July–20 October 2026. All phase-opening dates satisfy the submission prerequisites and seven/fourteen-day waits.

Dates and learner answers are generated test fixtures, not recovered participant work or observed historical activity. This provenance and the random seed are recorded internally. Supplied activity-minute summaries remain source metadata; displayed elapsed calendar durations include waiting and idle time.

`SIM-007`, `SIM-027` and `SIM-053` retain their missing withdrawal submissions. Their overall completion time is unavailable, rather than zero.

## Actual code-grading distribution

| Checks passed | Code-item results |
| --- | ---: |
| 0/4 | 203 |
| 0/5 | 9 |
| 1/4 | 178 |
| 2/4 | 156 |
| 3/4 | 242 |
| 4/4 | 940 |
| 4/5 | 65 |
| 5/5 | 103 |

641 code answers pass some checks but not all. Every final exam percentage was reproduced by the real server grader. Code logic, selected answers, omitted answers, variable names and formatting vary. Forms whose supplied score is 100% necessarily have all items correct.

## Verification

- 83 backend regression tests passed in an isolated PostgreSQL schema, including exact wait boundaries, direct API bypass attempts, late submissions, retakes, teacher reporting and study withdrawal.
- Frontend regression suite passed (104 existing tests, plus the new teacher timing test); six Node tests passed. The focused teacher suite passed all 28 tests.
- Frontend production builds and changed-file lint checks passed. The server frontend was rebuilt from its existing source plus the reviewed timing changes.
- Authenticated live HTTP verified the new schedule endpoint and all 237 teacher-visible submissions with dates, source scores and pending-review status.
- Unrelated user/profile/submission/log fingerprints were unchanged; 18 other user accounts remain.
- Browser screenshot verification was unavailable; UI date rendering was checked with React tests and the published entry was checked over HTTP.

## Recovery artifacts

Application backup: `/srv/trace-tutor/deployment-backups/protocol-20261025-5357f6cdd3a7`.

Graded scenario plan: `/srv/trace-tutor/deployment-backups/learner-fixture-plan-20261025-29360f03598a/plan.json`.

Plan SHA-256: `49b9af87fd12f3fe6466034f32bf5567a6dec5bf5dd47766f60ec57df75ebabe`.

Old imported rows were removed earlier at the user's request. These are new generated submissions, not restoration of the old teacher grades.

## Per-participant dates

Dates below use Dhaka time. Scores are Pre / Post / Transfer / Withdrawal.

| Participant | Scores | First opening | Completion | Calendar days |
| --- | --- | --- | --- | ---: |
| SIM-001 | 47 / 87 / 60 / 40 | 2026-08-05 17:34:10 | 2026-09-03 10:54:40 | 28.7226 |
| SIM-002 | 33 / 87 / 53 / 67 | 2026-07-15 13:10:25 | 2026-08-11 22:11:50 | 27.376 |
| SIM-003 | 47 / 60 / 40 / 27 | 2026-08-14 21:12:15 | 2026-09-09 10:09:10 | 25.5395 |
| SIM-004 | 80 / 100 / 100 / 73 | 2026-07-05 17:16:59 | 2026-08-08 09:52:08 | 33.6911 |
| SIM-005 | 60 / 80 / 40 / 27 | 2026-09-09 14:27:43 | 2026-10-12 09:08:00 | 32.778 |
| SIM-006 | 53 / 80 / 53 / 67 | 2026-09-08 07:11:21 | 2026-10-07 10:16:49 | 29.1288 |
| SIM-007 | 53 / 87 / 67 / Missing | 2026-09-15 17:25:03 | Incomplete | — |
| SIM-008 | 47 / 80 / 67 / 80 | 2026-07-30 07:29:14 | 2026-08-28 13:34:30 | 29.2537 |
| SIM-009 | 73 / 67 / 73 / 67 | 2026-09-03 18:55:49 | 2026-10-07 11:07:43 | 33.6749 |
| SIM-010 | 60 / 80 / 60 / 73 | 2026-09-18 10:44:33 | 2026-10-15 08:57:23 | 26.9256 |
| SIM-011 | 40 / 67 / 67 / 40 | 2026-07-01 10:29:47 | 2026-07-29 08:36:54 | 27.9216 |
| SIM-012 | 60 / 67 / 67 / 53 | 2026-07-16 13:56:10 | 2026-08-13 09:14:37 | 27.8045 |
| SIM-013 | 60 / 93 / 53 / 40 | 2026-07-14 10:01:36 | 2026-08-18 07:13:27 | 34.8832 |
| SIM-014 | 27 / 47 / 53 / 47 | 2026-07-27 22:01:32 | 2026-08-24 13:03:00 | 27.626 |
| SIM-015 | 33 / 27 / 27 / 40 | 2026-07-12 08:20:04 | 2026-08-11 14:55:14 | 30.2744 |
| SIM-016 | 53 / 60 / 60 / 33 | 2026-07-26 14:02:07 | 2026-08-22 16:57:52 | 27.122 |
| SIM-017 | 47 / 80 / 60 / 33 | 2026-07-05 07:38:11 | 2026-08-08 07:10:40 | 33.9809 |
| SIM-018 | 33 / 73 / 27 / 20 | 2026-09-14 21:12:32 | 2026-10-12 11:47:16 | 27.6075 |
| SIM-019 | 20 / 93 / 80 / 67 | 2026-08-01 22:52:33 | 2026-08-27 15:59:04 | 25.7129 |
| SIM-020 | 47 / 47 / 60 / 73 | 2026-07-18 19:52:07 | 2026-08-17 07:00:27 | 29.4641 |
| SIM-021 | 53 / 93 / 47 / 80 | 2026-07-24 13:17:13 | 2026-08-24 19:37:31 | 31.2641 |
| SIM-022 | 67 / 100 / 53 / 13 | 2026-09-04 13:07:36 | 2026-10-06 09:53:55 | 31.8655 |
| SIM-023 | 40 / 53 / 27 / 27 | 2026-08-15 22:41:08 | 2026-09-16 12:56:28 | 31.594 |
| SIM-024 | 7 / 33 / 13 / 7 | 2026-08-29 17:52:09 | 2026-09-27 07:54:08 | 28.5847 |
| SIM-025 | 20 / 67 / 60 / 33 | 2026-09-13 21:07:35 | 2026-10-10 21:47:57 | 27.028 |
| SIM-026 | 67 / 93 / 87 / 87 | 2026-08-18 15:50:26 | 2026-09-15 23:23:45 | 28.3148 |
| SIM-027 | 53 / 60 / 60 / Missing | 2026-07-02 18:27:16 | Incomplete | — |
| SIM-028 | 13 / 73 / 40 / 13 | 2026-08-25 07:41:18 | 2026-09-22 16:04:12 | 28.3492 |
| SIM-029 | 40 / 20 / 47 / 40 | 2026-07-29 08:10:50 | 2026-08-31 15:34:03 | 33.3078 |
| SIM-030 | 40 / 93 / 73 / 87 | 2026-09-08 14:40:04 | 2026-10-08 10:35:16 | 29.83 |
| SIM-031 | 73 / 67 / 73 / 87 | 2026-09-18 14:45:35 | 2026-10-19 14:44:37 | 30.9993 |
| SIM-032 | 53 / 93 / 80 / 67 | 2026-08-11 19:47:43 | 2026-09-07 08:27:05 | 26.5273 |
| SIM-033 | 47 / 47 / 47 / 53 | 2026-08-13 18:56:38 | 2026-09-11 11:37:56 | 28.6953 |
| SIM-034 | 47 / 100 / 87 / 40 | 2026-07-03 13:57:06 | 2026-08-02 11:30:13 | 29.898 |
| SIM-035 | 47 / 33 / 67 / 40 | 2026-07-22 11:28:29 | 2026-08-22 12:20:53 | 31.0364 |
| SIM-036 | 67 / 87 / 67 / 67 | 2026-07-20 12:03:07 | 2026-08-18 18:36:55 | 29.2735 |
| SIM-037 | 60 / 87 / 73 / 73 | 2026-09-07 13:57:18 | 2026-10-10 12:36:49 | 32.9441 |
| SIM-038 | 53 / 60 / 47 / 13 | 2026-08-01 07:12:45 | 2026-08-28 13:28:43 | 27.2611 |
| SIM-039 | 7 / 33 / 20 / 47 | 2026-08-02 08:54:14 | 2026-09-01 22:32:47 | 30.5684 |
| SIM-040 | 47 / 73 / 80 / 67 | 2026-07-02 21:13:05 | 2026-08-04 12:30:27 | 32.6371 |
| SIM-041 | 13 / 40 / 47 / 13 | 2026-07-23 08:15:00 | 2026-08-17 09:16:28 | 25.0427 |
| SIM-042 | 20 / 80 / 13 / 13 | 2026-07-19 15:17:53 | 2026-08-20 08:25:50 | 31.7139 |
| SIM-043 | 33 / 87 / 60 / 33 | 2026-08-28 09:50:49 | 2026-09-25 21:26:05 | 28.4828 |
| SIM-044 | 80 / 80 / 67 / 40 | 2026-08-01 18:36:29 | 2026-08-29 16:06:42 | 27.896 |
| SIM-045 | 53 / 73 / 67 / 67 | 2026-08-06 22:43:10 | 2026-09-10 15:29:22 | 34.6987 |
| SIM-046 | 53 / 40 / 67 / 80 | 2026-08-04 12:28:39 | 2026-09-04 14:16:18 | 31.0748 |
| SIM-047 | 20 / 53 / 40 / 27 | 2026-09-14 22:29:44 | 2026-10-15 16:58:38 | 30.7701 |
| SIM-048 | 60 / 100 / 93 / 87 | 2026-09-02 16:06:26 | 2026-10-01 18:15:52 | 29.0899 |
| SIM-049 | 73 / 93 / 80 / 93 | 2026-07-16 11:58:04 | 2026-08-15 08:00:36 | 29.8351 |
| SIM-050 | 27 / 87 / 67 / 87 | 2026-08-07 22:54:25 | 2026-09-06 17:46:43 | 29.7863 |
| SIM-051 | 20 / 73 / 60 / 47 | 2026-07-02 22:23:38 | 2026-08-04 10:12:27 | 32.4922 |
| SIM-052 | 47 / 73 / 40 / 20 | 2026-08-23 17:53:48 | 2026-09-24 08:07:48 | 31.5931 |
| SIM-053 | 33 / 47 / 40 / Missing | 2026-09-10 10:00:50 | Incomplete | — |
| SIM-054 | 33 / 47 / 40 / 33 | 2026-07-26 11:49:24 | 2026-08-23 20:44:34 | 28.3716 |
| SIM-055 | 20 / 47 / 47 / 27 | 2026-08-21 18:25:47 | 2026-09-17 10:40:04 | 26.6766 |
| SIM-056 | 47 / 87 / 80 / 80 | 2026-07-10 08:01:14 | 2026-08-05 22:44:13 | 26.6132 |
| SIM-057 | 47 / 80 / 53 / 80 | 2026-08-24 16:58:41 | 2026-09-24 22:00:38 | 31.2097 |
| SIM-058 | 7 / 20 / 27 / 20 | 2026-08-19 15:25:13 | 2026-09-19 07:18:47 | 30.6622 |
| SIM-059 | 73 / 93 / 73 / 47 | 2026-07-23 18:42:00 | 2026-08-21 10:34:02 | 28.6611 |
| SIM-060 | 33 / 87 / 53 / 33 | 2026-08-09 16:34:25 | 2026-09-09 10:07:13 | 30.7311 |

