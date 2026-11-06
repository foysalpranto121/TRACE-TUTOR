"""Two-stage, guarded SIM-008 evaluation fixture import via manage.py shell.

Set SIM008_IMPORT_STAGE to summary, answers, or verify. Unanswered items remain
absent from the answer dictionaries. Scores must be reproduced by the live grader.
"""
import copy
import hashlib
import json
import os

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import ExamSubmission
from logging_app.models import InteractionLog

SOURCE = {
    'participant_id': 'SIM-008', 'student_name': 'Omar Faruk Fariyan',
    'college_name': 'rajuk uttara model college', 'division': 'Dhaka',
    'gmail': 'omarfarukffariyan58@gmail.com', 'enrolled_arm': 'ANSWER_ONLY',
    'completion_status': 'COMPLETE', 'grade': 12, 'age_years': 18,
    'gender': 'Male', 'prior_experience': 'Basic', 'device_type': 'Laptop',
    'weekly_study_hours': 6, 'learning_minutes': 32, 'code_runs': 18,
    'learning_help_requests': 7, 'post_help_requests': 2, 'copy_events': 3,
    'tasks_solved': 8, 'pre_score_pct': 47, 'post_score_pct': 80,
    'transfer_score_pct': 67, 'withdrawal_score_pct': 80,
    'post_minus_pre_pp': 33, 'normalized_gain': 0.623,
    'withdrawal_minus_post_pp': 0.000, 'total_minutes': 99,
    'normalized_gain_sq': 0.388, 'withdrawal_drop_sq': 0.000,
}
TARGETS = {'pre': (47, 7), 'post': (80, 12), 'transfer': (67, 10), 'withdrawal': (80, 12)}
CODE_COUNTS = {'pre': 3, 'post': 7, 'transfer': 4, 'withdrawal': 5}
IMPORT_KEY = 'user-supplied-participant-summary:SIM-008:v1'
ATTACH_KEY = 'SIM-008:generated-correct-only-evaluation:v1'
BANK_HASH = 'cb2ce8f4634078b0a6de87bd776f7eb4a105cb5d2ee410d1f2f6a54b0c5ebdba'
ARM = SOURCE['enrolled_arm']


def c(body):
    return '#include <stdio.h>\n\nint main(void) {\n' + body.strip() + '\n    return 0;\n}\n'


def html(body):
    return '<!DOCTYPE html>\n<html lang="en">\n<head><title>ICT Assignment</title></head>\n<body>\n' + body + '\n</body>\n</html>\n'


CODE = {
    'pre_c_code_01': c(r'''    int n, sum = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) sum += i;
    printf("Sum = %d\n", sum);'''),
    'pre_c_code_02': c(r'''    int n;
    scanf("%d", &n);
    if (n % 2 == 0) printf("Even\n");
    else printf("Odd\n");'''),
    'pre_html_code_01': html('<table>\n<tr><th>Roll</th><th>Marks</th></tr>\n<tr><td>11</td><td>47</td></tr>\n</table>'),
    'post_c_code_01': c(r'''    int n;
    long long product = 1;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) product *= i;
    printf("Product = %lld\n", product);'''),
    'post_c_code_02': c(r'''    int n;
    scanf("%d", &n);
    if (n > 0) printf("Positive\n");
    else printf("Negative\n");'''),
    'post_c_code_03': c(r'''    int n, a = 0, b = 1;
    scanf("%d", &n);
    for (int i = 0; i < n; i++) {
        int next = a + b;
        a = b;
        b = next;
    }
    printf("Fibonacci = %d\n", a);'''),
    'post_c_code_04': c(r'''    int a, b, c, minimum;
    scanf("%d %d %d", &a, &b, &c);
    minimum = a;
    if (b < minimum) minimum = b;
    if (c < minimum) minimum = c;
    printf("Minimum = %d\n", minimum);'''),
    'post_html_code_01': html('<table>\n<tr><th rowspan="2">Department</th><td>Rahim</td></tr>\n<tr><td>Karim</td></tr>\n</table>'),
    'post_html_code_02': html('<a href="#contact">Contact</a>\n<section id="contact"><h2>Contact</h2><p>College office</p></section>'),
    'post_html_code_03': html('<ul type="disc">\n<li>HTML</li>\n<li>CSS</li>\n<li>JavaScript</li>\n</ul>'),
    'trans_c_code_01': c(r'''    int n, sum = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) sum += i * i;
    printf("Sum = %d\n", sum);'''),
    'trans_c_code_03': c(r'''    int n, reverse = 0;
    scanf("%d", &n);
    while (n > 0) {
        reverse = reverse * 10 + n % 10;
        n /= 10;
    }
    printf("Reverse = %d\n", reverse);'''),
    'trans_html_code_01': html('<form>\n<label for="name">Student name</label>\n<input id="name" name="name" type="text">\n<button type="submit">Register</button>\n</form>'),
    'trans_html_code_02': html('<video controls width="640" height="360">\n<source src="lesson.mp4" type="video/mp4">\nYour browser does not support video.\n</video>'),
    'with_c_code_01': c(r'''    int n, sum = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i += 2) sum += i;
    printf("Sum = %d\n", sum);'''),
    'with_c_code_02': c(r'''    int marks;
    scanf("%d", &marks);
    if (marks >= 80) printf("Grade = A+\n");
    else if (marks >= 70) printf("Grade = A\n");
    else printf("Grade = F\n");'''),
    'with_c_code_04': c(r'''    int a, b, temp;
    scanf("%d %d", &a, &b);
    temp = a;
    a = b;
    b = temp;
    printf("After swap: %d %d\n", a, b);'''),
    'with_html_code_01': html('<table>\n<tr><th colspan="2">Class Routine</th></tr>\n<tr><td>Bangla</td><td>ICT</td></tr>\n</table>'),
    'with_html_code_03': html('<nav>\n<ul>\n<li><a href="index.html">Home</a></li>\n<li><a href="courses.html">Courses</a></li>\n<li><a href="contact.html">Contact</a></li>\n</ul>\n</nav>'),
}


def profile_and_rows():
    profile = ParticipantProfile.objects.get(participant_code='SIM-008')
    assert profile.user.email == SOURCE['gmail'] and profile.enrolled_arm == ARM
    expected_profile = {
        'full_name': SOURCE['student_name'], 'school_name': SOURCE['college_name'],
        'division': SOURCE['division'], 'assigned_arm': ARM, 'role': 'STUDENT',
        'grade': str(SOURCE['grade']), 'age': SOURCE['age_years'],
        'gender': SOURCE['gender'], 'prior_experience': SOURCE['prior_experience'],
        'device_type': SOURCE['device_type'], 'weekly_study_hours': SOURCE['weekly_study_hours'],
    }
    assert all(getattr(profile, key) == value for key, value in expected_profile.items()), 'Profile/source mismatch'
    receipt = InteractionLog.objects.get(user=profile.user, event_type='SUMMARY_IMPORT', payload__import_key=IMPORT_KEY)
    assert receipt.payload['source'] == SOURCE
    assert len(SOURCE) == 29
    pre, post = SOURCE['pre_score_pct'], SOURCE['post_score_pct']
    drop = SOURCE['withdrawal_score_pct'] - post
    gain = (post - pre) / (100 - pre)
    assert SOURCE['post_minus_pre_pp'] == post - pre
    assert SOURCE['withdrawal_minus_post_pp'] == drop
    assert SOURCE['normalized_gain'] == round(gain, 3)
    assert SOURCE['normalized_gain_sq'] == round(gain * gain, 3)
    assert SOURCE['withdrawal_drop_sq'] == drop * drop
    rows = list(ExamSubmission.objects.filter(student=profile.user).order_by('pk'))
    assert len(rows) == 4 and {r.exam_type: r.score_pct for r in rows} == {k: v[0] for k, v in TARGETS.items()}
    return profile, rows


def summary():
    with transaction.atomic():
        if ParticipantProfile.objects.filter(participant_code='SIM-008').exists():
            _, rows = profile_and_rows()
            print('ALREADY_IMPORTED', [r.pk for r in rows], flush=True)
            return
        assert not User.objects.filter(email__iexact=SOURCE['gmail']).exists(), 'Email conflict'
        assert not User.objects.filter(username='SIM-008').exists(), 'Username conflict'
        user = User(username='SIM-008', email=SOURCE['gmail'], first_name='Omar', last_name='Faruk Fariyan')
        user.set_unusable_password()
        user.save()
        ParticipantProfile.objects.create(
            user=user, participant_code='SIM-008', role='STUDENT',
            full_name=SOURCE['student_name'], school_name=SOURCE['college_name'], division=SOURCE['division'],
            assigned_arm=ARM, enrolled_arm=ARM, grade='12', age=18, gender='Male',
            prior_experience='Basic', device_type='Laptop', weekly_study_hours=6,
        )
        for exam, (score, _) in TARGETS.items():
            ExamSubmission.objects.create(
                student=user, exam_type=exam, arm=ARM, score_pct=score,
                grading_status=ExamSubmission.GRADED,
                answers={'answers': {}, 'code_answers': {}, 'results': [],
                         'import_metadata': {'import_key': IMPORT_KEY, 'kind': 'summary_only',
                                             'score_source': 'user_supplied', 'answers_available': False,
                                             'original_submission_time_available': False}},
            )
        InteractionLog.objects.create(
            user=user, event_type='SUMMARY_IMPORT', arm=ARM,
            payload={'import_key': IMPORT_KEY, 'source': SOURCE,
                     'note': 'Aggregate import receipt, not observed learning events. Creation times are import times.'},
        )
    _, rows = profile_and_rows()
    print('SUMMARY_IMPORTED', json.dumps([{'id':r.pk,'exam':r.exam_type,'score':r.score_pct} for r in rows]), flush=True)


def answers():
    assert hashlib.sha256(scoring.ITEM_BANK_PATH.read_bytes()).hexdigest() == BANK_HASH
    profile, original = profile_and_rows()
    if InteractionLog.objects.filter(user=profile.user, payload__operation_key=ATTACH_KEY).exists():
        verify()
        return
    assert all(not r.answers.get('answers') and not r.answers.get('code_answers') and not r.grades.exists() for r in original)
    snapshots = {r.pk: copy.deepcopy(r.answers) for r in original}
    prepared = {}
    for exam, (target_score, target_correct) in TARGETS.items():
        items = scoring.items_for(exam)
        code_items = [i for i in items if i['type'] in scoring.CODE_TYPES]
        code_answers = {i['id']:CODE[i['id']] for i in code_items if i['id'] in CODE}
        assert len(items) == 15 and len(code_items) == 8 and len(code_answers) == CODE_COUNTS[exam]
        mcqs = [i for i in items if i['type'] not in scoring.CODE_TYPES]
        chosen = {i['id']:str(i['keyed_answer']) for i in mcqs[:target_correct-len(code_answers)]}
        score, correct, total, results = scoring.grade_submission(exam, chosen, code_answers)
        assert (score,correct,total) == (target_score,target_correct,15), (exam,results)
        supplied = set(chosen) | set(code_answers)
        assert all(r['correct'] == (r['item_id'] in supplied) for r in results)
        assert all(r.get('status') == 'NO_ANSWER' for r in results if r['type'] in scoring.CODE_TYPES and r['item_id'] not in supplied)
        prepared[exam] = {'answers':chosen,'code_answers':code_answers,'results':results}
        print('GRADED',exam,score,correct,total,'nonblank_code',len(code_answers),flush=True)
    with transaction.atomic():
        rows = list(ExamSubmission.objects.select_for_update().filter(student=profile.user).order_by('pk'))
        assert [r.pk for r in rows] == [r.pk for r in original]
        assert not InteractionLog.objects.filter(user=profile.user,payload__operation_key=ATTACH_KEY).exists()
        for row in rows:
            assert row.answers == snapshots[row.pk] and row.score_pct == TARGETS[row.exam_type][0] and not row.grades.exists()
            stored = copy.deepcopy(row.answers)
            stored.update(prepared[row.exam_type])
            stored['import_metadata'].update({
                'kind':'generated_evaluation_fixture','answers_available':True,
                'answers_source':'AI_generated_for_user_authorized_teacher_flow_test',
                'operation_key':ATTACH_KEY,'unanswered_policy':'incorrect_items_left_blank',
                'automatically_verified_score':row.score_pct,
            })
            row.answers=stored
            row.graded_at=timezone.now()
            row.save(update_fields=['answers','graded_at'])
        InteractionLog.objects.create(
            user=profile.user,event_type='EVALUATION_FIXTURE_ATTACH',arm=ARM,
            payload={'operation_key':ATTACH_KEY,'synthetic':True,
                     'purpose':'User-authorized teacher evaluation workflow test; correct answers only',
                     'previous_answers':{str(k):v for k,v in snapshots.items()},
                     'submission_ids':[r.pk for r in rows]},
        )
    print('ANSWERS_ATTACHED',sum(len(p['code_answers']) for p in prepared.values()),flush=True)
    verify()


def verify():
    from assessment.views import get_student_submissions
    from rest_framework.test import APIRequestFactory, force_authenticate
    profile, saved = profile_and_rows()
    staff=ParticipantProfile.objects.filter(role__in=['EXPERT_TEACHER','RESEARCHER_ADMIN']).select_related('user').first()
    assert staff
    request=APIRequestFactory().get('/api/assessment/student-submissions/')
    force_authenticate(request,user=staff.user)
    response=get_student_submissions(request)
    assert response.status_code == 200
    rows=[r for r in response.data['submissions'] if r['participant_code']=='SIM-008']
    assert len(rows)==4
    for row in rows:
        assert (row['score_pct'],row['correct'],row['total']) == (*TARGETS[row['exam_type']],15)
        assert len(row['code_answers'])==8
        filled=[c for c in row['code_answers'] if c['code'].strip()]
        blank=[c for c in row['code_answers'] if not c['code'].strip()]
        assert len(filled)==CODE_COUNTS[row['exam_type']]
        assert all(c['auto']['status']=='SUCCESS' for c in filled)
        assert all(c['auto']['status']=='NO_ANSWER' for c in blank)
    for row in saved:
        supplied=set(row.answers['answers']) | set(row.answers['code_answers'])
        assert all(r['correct']==(r['item_id'] in supplied) for r in row.answers['results'])
    print('TEACHER_PORTAL_VERIFIED',json.dumps([{'id':r['id'],'exam':r['exam_type'],'score':r['score_pct'],
          'correct':r['correct'],'code_filled':sum(bool(c['code'].strip()) for c in r['code_answers']),
          'code_blank':sum(not c['code'].strip() for c in r['code_answers']),'status':r['status']} for r in rows]),flush=True)


{'summary':summary,'answers':answers,'verify':verify}[os.environ['SIM008_IMPORT_STAGE']]()


