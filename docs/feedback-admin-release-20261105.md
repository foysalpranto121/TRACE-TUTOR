# Assessment feedback admin sections

Deployed on 5 November 2026, 23:22 Asia/Dhaka.

- Expert feedback: `/django-admin/assessment/expertfeedback/`. Shows student name/account,
  participant code, test, expert, complete qualitative feedback, marks and grading date.
  Details link to the original submission. Supports student/expert/text search and test/expert filters.
- Teacher comment: `/django-admin/assessment/teachercomment/`. Shows item key/title,
  test, teacher, complete item comment and date. Details also show the rubric scores.
  Supports item key/teacher/comment search and teacher filtering.
- Both sections appear under Assessment. They are read-only proxy views of the existing
  ExpertGrade and ExpertRating tables, with separate Django view permissions. Blank feedback
  rows are omitted. Existing and future portal updates appear directly without copying data.
- Teacher-authored content is HTML-escaped while preserving paragraphs and line breaks.

Validation: 26 tests passed in a disposable PostgreSQL schema, including existing teacher
portal regressions, historical feedback, search/filter, access control, blocked writes,
HTML escaping, nullable legacy relations and reflecting updates without duplicated records.
Migration consistency and Django system checks passed.

Live HTTPS verification visited both sections and every historical feedback/comment detail:
35 qualitative feedback entries and 11 item comments matched the saved database text.
Anonymous access redirects to admin login. Fingerprints of users, profiles, timelines,
submissions, sittings, grades and ratings were identical before and after deployment.
The temporary verification session was removed. No frontend bundle changes were required.

Staging: `/tmp/trace-feedback-20261105-164f7753b452`.
Private deployment backup and verification report:
`/srv/trace-tutor/deployment-backups/feedback-admin-20261105-9cd1e6ad47ad`.
