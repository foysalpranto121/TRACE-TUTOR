"""Serialize the authorized read-only snapshot to the requested plain CSV formats."""
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
snapshot = json.loads((ROOT / 'source_snapshot.json').read_text(encoding='utf-8'))
TZ = timezone(timedelta(hours=6))
EXAMS = ('pre', 'post', 'transfer', 'withdrawal')
SOURCE_COLUMNS = ('participant_id student_name college_name division gmail enrolled_arm completion_status '
                  'grade age_years gender prior_experience device_type weekly_study_hours learning_minutes '
                  'code_runs learning_help_requests post_help_requests copy_events tasks_solved '
                  'pre_score_pct post_score_pct transfer_score_pct withdrawal_score_pct post_minus_pre_pp '
                  'normalized_gain withdrawal_minus_post_pp total_minutes normalized_gain_sq withdrawal_drop_sq').split()
teachers = {row['id']: row for row in snapshot['teachers']}
teacher_order = {email: index for index, email in enumerate(snapshot['teacher_email_order'])}
students = {row['user_id']: row for row in snapshot['students']}
timelines = {row['student_id']: row for row in snapshot['timelines']}
submissions = {row['id']: row for row in snapshot['submissions']}
items = {row['id']: row for row in snapshot['items']}
cohort_ids = set(snapshot['cohort_submission_ids'])
grades = {(row['expert_user_id'], row['submission_id']): row for row in snapshot['grades']}
ratings = {(row['expert_user_id'], row['item_key']): row for row in snapshot['ratings']}
sub_owners = {row['submission_id']: row for row in snapshot['submission_assignments']}
item_owners = {row['item_key']: row for row in snapshot['item_assignments']}
events = defaultdict(Counter)
for row in snapshot['telemetry_counts']:
    events[row['user_id']][row['event_type']] = row['count']
by_student = defaultdict(lambda: defaultdict(list))
for row in snapshot['submissions']:
    if row['id'] in cohort_ids:
        by_student[row['student_id']][row['exam_type']].append(row)


def date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def local(value):
    return date(value).astimezone(TZ).isoformat(timespec='seconds') if value else None


def difference(start, end, divisor):
    return round((date(end) - date(start)).total_seconds() / divisor, 6) if start and end else None


def teacher_fields(teacher_id):
    row = teachers[teacher_id]
    return {'teacher_username': row['username'], 'teacher_name': row['profile__full_name'] or row['username'],
            'teacher_email': row['email'], 'teacher_institution': row['profile__school_name'],
            'teacher_division': row['profile__division'], 'teacher_district': row['profile__district']}


def origin(submission):
    metadata = (submission.get('answers') or {}).get('import_metadata') or {}
    simulated = metadata.get('kind') == 'generated_evaluation_fixture'
    return {'student_data_origin': 'generated_test_scenario' if simulated else 'database_record',
            'synthetic_student_data': simulated, 'submission_timestamp_source': metadata.get('timestamps_source') or 'recorded'}


def code_counts(submission):
    answers = submission.get('answers') or {}
    results = [r for r in answers.get('results', []) if r.get('type') in ('c_programming', 'html_coding')]
    return {'code_item_count': len(results),
            'fully_passed_code_items': sum(r.get('status') == 'SUCCESS' for r in results),
            'partial_pass_code_items': sum(0 < (r.get('passed_count') or 0) < (r.get('total_tests') or 0) for r in results),
            'zero_pass_code_items': sum((r.get('passed_count') or 0) == 0 for r in results),
            'unanswered_code_items': sum(not (answers.get('code_answers', {}).get(r.get('item_id')) or '').strip() for r in results)}


reviews = []
grade_pairs = set(grades) | {(row['expert_user_id'], row['submission_id']) for row in snapshot['submission_assignments']}
for teacher_id, submission_id in sorted(grade_pairs):
    submission = submissions.get(submission_id)
    if not submission:
        continue
    grade = grades.get((teacher_id, submission_id))
    assignment = sub_owners.get(submission_id)
    primary = bool(assignment and assignment['expert_user_id'] == teacher_id)
    row = {**teacher_fields(teacher_id), 'review_type': 'SUBMISSION_GRADE',
           'review_scope': 'PRIMARY_ASSIGNMENT' if primary else 'ADDITIONAL_OR_EARLIER_REVIEW',
           'review_status': 'GRADED' if grade and grade['is_graded'] else 'PENDING',
           'assigned_at_dhaka': local(assignment['assigned_at']) if primary else None,
           'participant_id': submission['student__profile__participant_code'],
           'student_name': submission['student__profile__full_name'], 'exam_type': submission['exam_type'],
           'submission_id': submission_id, 'cohort_member': submission_id in cohort_ids,
           'auto_score_pct': submission['score_pct'], 'auto_grading_status': submission['grading_status'],
           'teacher_marks': grade['assigned_marks'] if grade else None,
           'max_marks': grade['max_marks'] if grade else None,
           'qualitative_feedback': grade['feedback_comments'] if grade else None,
           'reviewed_at_dhaka': local(grade['graded_at']) if grade else None,
           'submission_at_dhaka': local(submission['submitted_at']), **origin(submission), **code_counts(submission),
           'grade_level': 'whole_submission',
           'submission_item_ids': ';'.join(r.get('item_id', '') for r in (submission['answers'] or {}).get('results', []))}
    reviews.append(row)

rating_pairs = set(ratings) | {(row['expert_user_id'], row['item_key']) for row in snapshot['item_assignments']}
for teacher_id, item_key in sorted(rating_pairs):
    rating = ratings.get((teacher_id, item_key))
    assignment = item_owners.get(item_key)
    primary = bool(assignment and assignment['expert_user_id'] == teacher_id)
    item = items.get(item_key, {})
    reviews.append({**teacher_fields(teacher_id), 'review_type': 'ITEM_REVIEW',
                    'review_scope': 'PRIMARY_ASSIGNMENT' if primary else 'ADDITIONAL_OR_EARLIER_REVIEW',
                    'review_status': 'RATED' if rating else 'PENDING',
                    'assigned_at_dhaka': local(assignment['assigned_at']) if primary else None,
                    'exam_type': item.get('exam_type'), 'item_id': item_key, 'item_title': item.get('title'),
                    'item_type': item.get('type'), 'item_question': item.get('question'),
                    'alignment_score': rating['alignment_score'] if rating else None,
                    'accuracy_score': rating['accuracy_score'] if rating else None,
                    'clarity_score': rating['clarity_score'] if rating else None,
                    'difficulty_score': rating['difficulty_score'] if rating else None,
                    'answerability_score': rating['answerability_score'] if rating else None,
                    'teacher_comment': rating['feedback'] if rating else None,
                    'rating_created_at_dhaka': local(rating['created_at']) if rating else None})
reviews.sort(key=lambda r: (teacher_order[r['teacher_email']], r['review_type'], r.get('participant_id') or '',
                            r.get('exam_type') or '', r.get('submission_id') or 0, r.get('item_id') or ''))

sheet_rows, database_rows, long_rows = [], [], []
for profile in snapshot['students']:
    uid = profile['user_id']
    timeline = timelines.get(uid, {})
    source = (timeline.get('provenance') or {}).get('original_summary')
    assert source and source['participant_id'] == profile['participant_code']
    assert set(SOURCE_COLUMNS) <= set(source), f'Missing original columns for {profile["participant_code"]}'
    sheet_rows.append({field: source.get(field) for field in SOURCE_COLUMNS})
    first = {exam: sorted(by_student[uid][exam], key=lambda r: (r['submitted_at'], r['id']))[0]
             for exam in EXAMS if by_student[uid][exam]}
    completed = all(exam in first for exam in EXAMS)
    status = 'COMPLETE' if completed else ('WITHDRAWAL_MISSING' if all(exam in first for exam in EXAMS[:3]) else 'IN_PROGRESS')
    row = {'participant_id': profile['participant_code'], 'student_name': profile['full_name'],
           'college_name': profile['school_name'], 'division': profile['division'], 'district': profile['district'],
           'gmail': profile['user__email'], 'enrolled_arm': profile['enrolled_arm'], 'current_arm': profile['assigned_arm'],
           'completion_status': status, 'grade': profile['grade'], 'age_years': profile['age'],
           'gender': profile['gender'], 'prior_experience': profile['prior_experience'],
           'device_type': profile['device_type'], 'weekly_study_hours': profile['weekly_study_hours'],
           'consent_given': profile['consent_given'], 'medium': profile['medium'], 'area_type': profile['area_type'],
           'ai_tool_familiarity': profile['ai_tool_familiarity'], 'is_synthetic': timeline.get('is_synthetic'),
           'data_origin': (timeline.get('provenance') or {}).get('source'),
           'summary_source': 'user_supplied_aggregate', 'historical_phase_timestamps_source': 'simulated' if timeline.get('is_synthetic') else 'recorded',
           'reported_learning_minutes': source['learning_minutes'], 'reported_code_runs': source['code_runs'],
           'reported_learning_help_requests': source['learning_help_requests'],
           'reported_post_help_requests': source['post_help_requests'], 'reported_copy_events': source['copy_events'],
           'reported_tasks_solved': source['tasks_solved'], 'reported_total_minutes': source['total_minutes'],
           'observed_code_result_events': events[uid]['CODE_RESULT'],
           'observed_help_request_events': events[uid]['HELP_REQUEST'], 'observed_copy_paste_events': events[uid]['COPY_PASTE'],
           'study_window_start_dhaka': local(timeline.get('window_start')),
           'study_window_end_dhaka': local(timeline.get('window_end'))}
    for exam in EXAMS:
        submission = first.get(exam)
        opened = timeline.get(exam + '_started_at')
        assignment = sub_owners.get(submission['id']) if submission else None
        teacher = teachers.get(assignment['expert_user_id']) if assignment else None
        grade = grades.get((teacher['id'], submission['id'])) if teacher and submission else None
        data = {'submission_id': submission['id'] if submission else None,
                'attempts': len(by_student[uid][exam]),
                'auto_score_pct': submission['score_pct'] if submission else None,
                'opened_at_dhaka': local(opened), 'submitted_at_dhaka': local(submission['submitted_at']) if submission else None,
                'elapsed_minutes': difference(opened, submission['submitted_at'], 60) if submission else None,
                'assigned_teacher': teacher['profile__full_name'] if teacher else None,
                'assigned_teacher_username': teacher['username'] if teacher else None,
                'teacher_marks': grade['assigned_marks'] if grade else None,
                'teacher_max_marks': grade['max_marks'] if grade else None,
                'teacher_graded': bool(grade and grade['is_graded']),
                'qualitative_feedback': grade['feedback_comments'] if grade else None,
                'teacher_graded_at_dhaka': local(grade['graded_at']) if grade else None}
        row.update({exam + '_' + key: value for key, value in data.items()})
        if submission:
            long_rows.append({'participant_id': profile['participant_code'], 'student_name': profile['full_name'],
                              'exam_type': exam, 'enrolled_arm': profile['enrolled_arm'], **data,
                              'auto_grading_status': submission['grading_status'], **origin(submission), **code_counts(submission)})
    pre = first.get('pre', {}).get('score_pct')
    post = first.get('post', {}).get('score_pct')
    withdrawal = first.get('withdrawal', {}).get('score_pct')
    gain = (post - pre) / (100 - pre) if pre is not None and post is not None and pre < 100 else None
    drop = withdrawal - post if withdrawal is not None and post is not None else None
    row.update({'post_minus_pre_pp': post - pre if post is not None and pre is not None else None,
                'normalized_gain': round(gain, 6) if gain is not None else None,
                'normalized_gain_sq': round(gain ** 2, 6) if gain is not None else None,
                'withdrawal_minus_post_pp': drop, 'withdrawal_drop_sq': drop ** 2 if drop is not None else None,
                'study_elapsed_days': difference(timeline.get('pre_started_at'), first['withdrawal']['submitted_at'], 86400) if completed else None,
                'days_to_latest_submission': difference(timeline.get('pre_started_at'), max(s['submitted_at'] for s in first.values()), 86400)})
    database_rows.append(row)

summary_rows = []
for teacher in sorted(teachers.values(), key=lambda t: teacher_order[t['email']]):
    own = [r for r in reviews if r['teacher_username'] == teacher['username']]
    assigned_items = [r for r in own if r['review_type'] == 'ITEM_REVIEW' and r['review_scope'] == 'PRIMARY_ASSIGNMENT']
    assigned_subs = [r for r in own if r['review_type'] == 'SUBMISSION_GRADE' and r['review_scope'] == 'PRIMARY_ASSIGNMENT']
    summary_rows.append({**teacher_fields(teacher['id']),
                         'items_assigned': len(assigned_items), 'items_completed': sum(r['review_status'] == 'RATED' for r in assigned_items),
                         'items_pending': sum(r['review_status'] == 'PENDING' for r in assigned_items),
                         'submissions_assigned': len(assigned_subs), 'submissions_completed': sum(r['review_status'] == 'GRADED' for r in assigned_subs),
                         'submissions_pending': sum(r['review_status'] == 'PENDING' for r in assigned_subs),
                         'all_saved_grades': sum(r['review_type'] == 'SUBMISSION_GRADE' and r['review_status'] == 'GRADED' for r in own),
                         'all_saved_item_reviews': sum(r['review_type'] == 'ITEM_REVIEW' and r['review_status'] == 'RATED' for r in own),
                         'qualitative_feedback_count': sum(bool((r.get('qualitative_feedback') or '').strip()) for r in own),
                         'item_comment_count': sum(bool((r.get('teacher_comment') or '').strip()) for r in own),
                         'snapshot_at_dhaka': local(snapshot['extracted_at_utc'])})

formula_escapes = 0


def safe(value):
    global formula_escapes
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '@', '\t', '\r')):
        formula_escapes += 1
        return "'" + value
    if isinstance(value, str) and value.lstrip().startswith('-'):
        try:
            float(value)
        except ValueError:
            formula_escapes += 1
            return "'" + value
    return value


files = {}


def write_csv(filename, rows, fields=None):
    if fields is None:
        fields = list(dict.fromkeys(key for row in rows for key in row))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writeheader()
    writer.writerows({key: safe(row.get(key)) for key in fields} for row in rows)
    raw = stream.getvalue().encode('utf-8-sig')
    (ROOT / filename).write_bytes(raw)
    parsed = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
    assert len(parsed) == len(rows) and all(None not in row for row in parsed)
    files[filename] = {'rows': len(rows), 'columns': len(fields), 'sha256': hashlib.sha256(raw).hexdigest()}
    return fields, parsed


review_fields, parsed_reviews = write_csv('teacher_reviews.csv', reviews)
db_fields, parsed_database = write_csv('students_database.csv', database_rows)
sheet_fields, parsed_sheet = write_csv('students_sheet_format.csv', sheet_rows, SOURCE_COLUMNS)
summary_fields, parsed_summary = write_csv('teacher_summary.csv', summary_rows)
long_fields, parsed_long = write_csv('student_submissions.csv', long_rows)

assert len(sheet_rows) == len(database_rows) == 60 and len(summary_rows) == 10
assert len(long_rows) == len(cohort_ids) == 237
assert len({r['participant_id'] for r in parsed_sheet}) == 60
assert all(len(row) == 29 for row in parsed_sheet)
assert sum(int(row['items_assigned']) for row in parsed_summary) == 60
assert sum(int(row['submissions_assigned']) for row in parsed_summary) == 237
assert all(int(row['items_assigned']) == 6 for row in parsed_summary)
assert Counter(int(row['submissions_assigned']) for row in parsed_summary) == {24: 7, 23: 3}
assert sum(r['review_type'] == 'SUBMISSION_GRADE' and r['review_status'] == 'GRADED' for r in reviews) == sum(g['is_graded'] for g in snapshot['grades'])
assert sum(r['review_type'] == 'ITEM_REVIEW' and r['review_status'] == 'RATED' for r in reviews) == len(snapshot['ratings'])
for original, parsed in zip(sheet_rows, parsed_sheet):
    assert all(parsed[key] == ('' if original[key] is None else str(original[key])) for key in SOURCE_COLUMNS)
for parsed in parsed_database:
    assert parsed['is_synthetic'] == 'TRUE'
    if parsed['participant_id'] in ('SIM-007', 'SIM-027', 'SIM-053'):
        assert parsed['withdrawal_auto_score_pct'] == '' and parsed['withdrawal_teacher_marks'] == ''
        assert parsed['study_elapsed_days'] == ''

dictionary = []
for filename, fields in (('teacher_reviews.csv', review_fields), ('students_database.csv', db_fields),
                         ('students_sheet_format.csv', sheet_fields), ('teacher_summary.csv', summary_fields),
                         ('student_submissions.csv', long_fields)):
    for field in fields:
        meaning = field.replace('_', ' ')
        if field.endswith('_dhaka'):
            meaning += '; ISO 8601, UTC+06:00'
        if field.startswith('reported_') or filename == 'students_sheet_format.csv':
            meaning += '; preserved user-supplied aggregate, not an observed event measure'
        if field.startswith('observed_'):
            meaning += '; count of matching saved InteractionLog events'
        if field == 'qualitative_feedback' or field.endswith('_qualitative_feedback'):
            meaning += '; verbatim saved submission-level expert feedback'
        if field == 'teacher_comment':
            meaning += '; verbatim saved item-level expert comment'
        dictionary.append({'file': filename, 'column': field, 'description': meaning,
                           'missing_value': 'empty field; zero is retained as a numeric value'})
write_csv('data_dictionary.csv', dictionary)

readme = f'''TRACE CSV export — {local(snapshot['extracted_at_utc'])}

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
were checked. Cells escaped to prevent formula execution in Excel: {formula_escapes}.
The source snapshot was captured at {snapshot['extracted_at_utc']}.
'''
(ROOT / 'README.txt').write_text(readme, encoding='utf-8-sig')
manifest = {'snapshot_at_utc': snapshot['extracted_at_utc'], 'snapshot_at_dhaka': local(snapshot['extracted_at_utc']),
            'files': files, 'saved_grades': len(snapshot['grades']), 'saved_item_ratings': len(snapshot['ratings']),
            'formula_escaped_cells': formula_escapes, 'synthetic_student_count': sum(bool(t['is_synthetic']) for t in timelines.values()),
            'review_status_counts': dict(Counter((row['review_type'] + ':' + row['review_status']) for row in reviews))}
(ROOT / 'export_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
archive = ROOT / 'TRACE_teacher_student_CSVs.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
    for name in [*files, 'README.txt', 'export_manifest.json']:
        bundle.write(ROOT / name, arcname=name)
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
print(json.dumps(manifest, ensure_ascii=False, indent=2))
