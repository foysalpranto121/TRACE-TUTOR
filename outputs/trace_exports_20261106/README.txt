TRACE CSV export — 2026-11-06T15:03:07+06:00

Scope and format
----------------
Ten named teachers; SIM-001 through SIM-060; 60 item assignments; 237 submitted
cohort papers. Files are UTF-8 with BOM, comma-separated, quoted with CRLF rows.
Excel can open them directly; embedded commas/newlines in feedback are preserved.
Blank means missing or not applicable; zero is a recorded zero. TRUE/FALSE are flags.
All dates are ISO 8601 in Asia/Dhaka (UTC+06:00).

Files
-----
teacher_reviews.csv: one row per teacher/submission grade or teacher/item review,
including pending primary assignments if present. Filter review_type to separate
SUBMISSION_GRADE from ITEM_REVIEW. review_scope distinguishes primary work from
additional/earlier work. This includes the ten teachers' older saved grades outside
the SIM cohort; cohort_member distinguishes those submissions. Marks are for whole
submissions. The system stores no manually assigned per-question marks. Item-review
rubric scores are 1–4; item comments are distinct from qualitative submission feedback.

teacher_summary.csv: one row per teacher with primary assigned/completed/pending
counts and all saved review/feedback totals. No grade or comment is invented.

students_database.csv: one row per SIM student, relevant current database fields,
first chronological submission per test, assigned teacher's marks and feedback,
dates, attempts, source flags, reported aggregates and observed event counts.
When more than one teacher grades a paper, all reviews remain in teacher_reviews.csv;
the student summary uses the primary assigned teacher's grade only.
normalized_gain = (post - pre)/(100 - pre), using saved automatic scores, rounded
to six decimals; undefined denominators remain blank. Squared gain uses the unrounded
ratio before rounding. withdrawal_minus_post_pp = withdrawal - post; its square is
withdrawal_drop_sq. Calendar elapsed time includes waiting/idle time and is distinct
from user-reported study minutes.

students_sheet_format.csv: exactly the original 29 headers supplied in this chat,
in their original order. Values come from the preserved original_summary import
metadata, including original rounded ratios and original spellings. This is the
requested prior sheet layout; no separate uploaded XLS/XLSX was available.

student_submissions.csv: 237 existing cohort submissions in long format, one row per
student/test, with assigned teacher, marks, feedback and code-check counts.
Partial passes require 0 < passed_count < total_tests. Zero-pass and unanswered
counts overlap by design. Each code question counts once, not once per compiler test.

data_dictionary.csv: column list and missing/source conventions for each CSV.

Provenance — essential for thesis use
-----------------------------------
All sixty SIM students have is_synthetic=TRUE in the database. Their per-item code
answers are generated learner examples and historical exam dates are simulated.
Their original aggregate scores/activity summaries were supplied by the user.
These are test/simulation records, not observed human-participant results. Preserve
that distinction in a thesis; do not describe these simulated records as observed
student behavior. Saved teacher feedback/rubric/grade records are exported as stored;
the export itself does not independently verify how those reviews were authored.

Reported code runs/help/copy counts are not substituted for observed InteractionLog
event counts. Missing Withdrawal for SIM-007, SIM-027 and SIM-053 remains blank.
The original 29-column sheet has no provenance column because its exact schema is
preserved; keep this README with that file. The database-format exports carry flags.

Reference document
------------------
221-35-848_book binding.docx is a thesis sample titled Gestational Diabetes Risk
Prediction Using Machine Learning, not a TRACE student-sheet schema. It contains
no embedded Excel file. It was read as reference and was not edited. No medical
variables were added to TRACE exports. No website or database records were changed.

Verification
------------
Read-only repeatable-read database transaction. Counts, assigned quotas, original
29-column values, missing Withdrawal, all saved grades/ratings and CSV round trips
were checked. Cells escaped to prevent formula execution in Excel: 0.
The source snapshot was captured at 2026-11-06T09:03:07.757Z.
