"""Generated learner fixtures with real grading and explicit internal provenance.

Inject FIXTURES (the previously validated 32 correct reference programs). Sources
come from the verified removal backup. Dates are simulated, not observed history.
"""
import copy
from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import random
import re
import secrets
from uuid import uuid4
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from accounts.models import ParticipantProfile
from assessment import scoring, timing
from assessment.models import AssessmentTimeline, ExamSubmission, PaperSitting
from assessment.views import get_student_submissions
from logging_app.models import InteractionLog
from rest_framework.test import APIRequestFactory, force_authenticate

BACKUP = Path('/srv/trace-tutor/deployment-backups/remove-sim001-060-20261025-5f66d46b23ee')
ORIGINAL_HASH = 'd3969ddcea5fbe7a0ed6a5bd974f7c6caaa7ae377b418e1a028246c6f1d61e80'
WINDOW_START = datetime(2026, 7, 1, tzinfo=ZoneInfo('Asia/Dhaka'))
WINDOW_END = datetime(2026, 10, 20, 23, 59, 59, tzinfo=ZoneInfo('Asia/Dhaka'))
IMPORT_VERSION = 'varied-learner-fixtures-20261025-v1'
SEED = secrets.randbits(128)


def c(body):
    return '#include <stdio.h>\nint main(void) {\n' + body + '\nreturn 0;\n}\n'


def html(body):
    return '<!DOCTYPE html>\n<html><head><title>ICT</title></head><body>\n' + body + '\n</body></html>'


BUGS = {
    'pre_c_code_01': c(r'int n,sum=0; scanf("%d",&n); for(int i=1;i<n;i++) sum+=i; printf("Sum = %d\n",sum);'),
    'pre_c_code_02': c(r'int n; scanf("%d",&n); if(n>0) puts("Even"); else puts("Odd");'),
    'pre_c_code_03': c(r'int n,fact=0; scanf("%d",&n); for(int i=1;i<=n;i++) fact*=i; printf("Factorial = %d\n",fact);'),
    'pre_c_code_04': c(r'int a,b,c,m; scanf("%d %d %d",&a,&b,&c); m=a; if(b>m)m=b; printf("Max = %d\n",m);'),
    'pre_c_code_05': c(r'int n; scanf("%d",&n); if(n%2) printf("%d is Prime\n",n); else printf("%d is Not Prime\n",n);'),
    'pre_html_code_01': html('<table><tr><td>Roll</td><td>Marks</td></tr><tr><td>11</td><td>50</td></tr></table>'),
    'pre_html_code_02': html('<a href="https://nctb.gov.bd">College</a><img src="college.jpg" alt="College">'),
    'pre_html_code_03': html('<ol><li>Bangla</li><li>English</li><li>ICT</li></ol>'),
    'post_c_code_01': c(r'int n,p=0; scanf("%d",&n); for(int i=1;i<=n;i++)p*=i; printf("Product = %d\n",p);'),
    'post_c_code_02': c(r'int n; scanf("%d",&n); if(n>1) puts("Positive"); else puts("Negative");'),
    'post_c_code_03': c(r'int n,a=0,b=1; scanf("%d",&n); for(int i=0;i<=n;i++){int t=a+b;a=b;b=t;} printf("Fibonacci = %d\n",a);'),
    'post_c_code_04': c(r'int a,b,c,m; scanf("%d %d %d",&a,&b,&c);m=a;if(b<m)m=b;printf("Minimum = %d\n",m);'),
    'post_c_code_05': c(r'int n,count=0;scanf("%d",&n);for(int i=1;i<n;i++){if(n%i==0)count++;}printf("Divisors = %d\n",count);'),
    'post_html_code_01': html('<table><tr><th>Department</th><td>Rahim</td></tr><tr><td>Karim</td></tr></table>'),
    'post_html_code_02': html('<a href="#contact">Contact</a><section id="contacts"><h2>Contact</h2></section>'),
    'post_html_code_03': html('<ul><li>HTML</li><li>CSS</li><li>JavaScript</li></ul>'),
    'trans_c_code_01': c(r'int n,sum=0;scanf("%d",&n);for(int i=1;i<=n;i++)sum+=i;printf("Sum = %d\n",sum);'),
    'trans_c_code_02': c(r'int year;scanf("%d",&year);if(year%4==0)puts("Leap Year");else puts("Common Year");'),
    'trans_c_code_03': c(r'int n,rev=0;scanf("%d",&n);while(n>0){rev=n%10;n/=10;}printf("Reverse = %d\n",rev);'),
    'trans_c_code_04': c(r'float a,b,c;scanf("%f %f %f",&a,&b,&c);printf("Average = %.2f\n",a+b+c/3);'),
    'trans_c_code_05': c(r'int n,t,sum=0;scanf("%d",&n);t=n;while(t>0){int d=t%10;sum+=d*d;t/=10;}if(sum==n)puts("Armstrong Number");else puts("Ordinary Number");'),
    'trans_html_code_01': html('<form><label>Name</label><input type="text"><button type="submit">Register</button></form>'),
    'trans_html_code_02': html('<video width="640" height="360"><source src="lesson.mp4" type="video/mp4"></video>'),
    'trans_html_code_03': html('<ul><li>Computer</li><li>Hardware</li><li>Software</li><li>Internet</li></ul>'),
    'with_c_code_01': c(r'int n,sum=0;scanf("%d",&n);for(int i=1;i<=n;i++)sum+=i;printf("Sum = %d\n",sum);'),
    'with_c_code_02': c(r'int marks;scanf("%d",&marks);if(marks>80)puts("Grade = A+");else if(marks>70)puts("Grade = A");else puts("Grade = F");'),
    'with_c_code_03': c(r'int b,e,r=1;scanf("%d %d",&b,&e);for(int i=1;i<e;i++)r*=b;printf("Result = %d\n",r);'),
    'with_c_code_04': c(r'int a,b;scanf("%d %d",&a,&b);a=b;b=a;printf("After swap: %d %d\n",a,b);'),
    'with_c_code_05': c(r'int n,old,rev=0;scanf("%d",&n);old=n;while(n>0){rev=n%10;n/=10;}if(rev==old)puts("Palindrome = YES");else puts("Palindrome = NO");'),
    'with_html_code_01': html('<table><tr><th>Class Routine</th></tr><tr><td>Bangla</td><td>ICT</td></tr></table>'),
    'with_html_code_02': html('<img src="book1.jpg" alt="Book Cover"><img src="book2.jpg">'),
    'with_html_code_03': html('<nav><ul><li><a href="home.html">Home</a></li><li>Courses</li><li><a href="contact.html">Contact</a></li></ul></nav>'),
}


def style(source, rng, is_html=False):
    if is_html:
        if rng.random() < .5:
            source = source.replace('"', "'")
        if rng.random() < .6:
            source = source.replace('><', '>\n<')
        indent = rng.choice(['', ' ', '  ', '    ', '\t'])
        return '\n'.join((indent if index and line.startswith('<') else '') + line for index, line in enumerate(source.splitlines()))
    names = {'n': ['num', 'number', 'n1', 'n'], 'sum': ['total', 's', 'sum'],
             'i': ['j', 'counter', 'i'], 'factorial': ['fact', 'f', 'factorial'],
             'product': ['mul', 'p', 'product'], 'reverse': ['rev', 'reversed', 'reverse'],
             'minimum': ['small', 'minValue', 'minimum'], 'maximum': ['large', 'maxValue', 'maximum']}
    mapping = {key: rng.choice(values) for key, values in names.items()}
    token = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|\b[A-Za-z_]\w*\b')
    source = token.sub(lambda match: mapping.get(match.group(), match.group()), source)
    if rng.random() < .55:
        source = source.replace('int main(void)', 'int main()')
    if rng.random() < .4:
        source = source.replace(') {', ')\n{')
    indent = rng.choice(['', ' ', '  ', '   ', '    ', '\t'])
    lines = []
    for line in source.splitlines():
        leading = len(line) - len(line.lstrip())
        line = indent * (leading // 4) + line.lstrip() if leading else line
        if not line.strip() and rng.random() < .6:
            continue
        lines.append(line.rstrip())
    return '\n'.join(lines) + '\n'


def daytime(value, rng):
    if value.hour < 7:
        value = value.replace(hour=rng.randint(7, 10))
    return value


def schedule(rng, missing):
    for _ in range(100):
        first = WINDOW_START + timedelta(days=rng.randint(0, 80), hours=rng.randint(7, 22), minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))
        stamps = {}
        opened = first
        for exam in timing.ORDER:
            if exam == 'withdrawal' and missing:
                break
            if exam == 'pre':
                duration = timedelta(minutes=rng.randint(15, 90), seconds=rng.randint(1, 59)) + timedelta(hours=rng.choice([0, 0, 0, 1, 4, 14, 30]))
            elif exam == 'post':
                duration = timedelta(seconds=rng.randint(1800, 9 * 86400))
            elif exam == 'transfer':
                duration = timedelta(seconds=rng.randint(3600, 17 * 86400))
            else:
                duration = timedelta(seconds=rng.randint(900, 3 * 86400))
            submitted = daytime(opened + duration, rng)
            stamps[exam] = (opened, submitted)
            wait = timedelta(days=timing.WAIT_DAYS.get(exam, 0))
            opened = daytime(max(opened + wait, submitted) + timedelta(seconds=rng.randint(600, 4 * 86400)), rng)
        if max(finish for _, finish in stamps.values()) <= WINDOW_END:
            return stamps
    raise AssertionError('Unable to fit schedule inside the requested historical window')


def build_answers(source, rng):
    prepared = {}
    for exam in timing.ORDER:
        target = source[f'{exam}_score_pct']
        if target is None:
            continue
        correct_count = next(n for n in range(16) if round(n * 100 / 15) == target)
        items = scoring.items_for(exam)
        code_items = [i for i in items if i['type'] in scoring.CODE_TYPES]
        mcqs = [i for i in items if i['type'] not in scoring.CODE_TYPES]
        code_correct = max(0, correct_count - len(mcqs), min(len(code_items), correct_count,
                           round(correct_count * 8 / 15) + rng.choice([-1, 0, 0, 1])))
        selected = set(rng.sample([i['id'] for i in code_items], code_correct))
        selected.update(rng.sample([i['id'] for i in mcqs], correct_count - code_correct))
        answers, code = {}, {}
        for item in items:
            key = item['id']
            if item['type'] in scoring.CODE_TYPES:
                if key in selected:
                    value = FIXTURES['code'][key]
                elif rng.random() < .14:
                    continue
                else:
                    value = BUGS[key]
                code[key] = style(value, rng, item['type'] == 'html_coding')
            elif key in selected:
                answers[key] = str(item['keyed_answer'])
            elif rng.random() > .16:
                answers[key] = rng.choice([str(o['id']) for o in item['options'] if str(o['id']) != str(item['keyed_answer'])])
        score, count, total, results = scoring.grade_submission(exam, answers, code)
        assert (score, count, total) == (target, correct_count, 15), (source['participant_id'], exam, score, results)
        assert {r['item_id'] for r in results if r['correct']} == selected
        prepared[exam] = {'answers': answers, 'code_answers': code, 'results': results}
        print('VARIED_GRADED', source['participant_id'], exam, score, flush=True)
    return prepared


def sources():
    data = (BACKUP / 'affected-rows.json').read_bytes()
    assert hashlib.sha256(data).hexdigest() == ORIGINAL_HASH
    receipts = [row['fields']['payload']['source'] for row in json.loads(data)
                if row['model'] == 'logging_app.interactionlog' and row['fields']['event_type'] == 'SUMMARY_IMPORT']
    assert len(receipts) == 60 and {s['participant_id'] for s in receipts} == {f'SIM-{n:03}' for n in range(1, 61)}
    return sorted(receipts, key=lambda s: s['participant_id'])


def fingerprints():
    from django.core import serializers
    return {model._meta.label_lower: hashlib.sha256(serializers.serialize('json', model.objects.exclude(
        **({'username__in': [f'SIM-{n:03}' for n in range(1,61)]} if model is User else
           {'user__username__in': [f'SIM-{n:03}' for n in range(1,61)]} if model in (ParticipantProfile, InteractionLog) else
           {'student__username__in': [f'SIM-{n:03}' for n in range(1,61)]})).order_by('pk')).encode()).hexdigest()
        for model in (User, ParticipantProfile, InteractionLog, ExamSubmission)}


def prepare(inputs):
    directory = BACKUP.parent / ('learner-fixture-plan-20261025-' + uuid4().hex[:12])
    directory.mkdir(mode=0o700)
    plan = {'version':IMPORT_VERSION, 'seed':str(SEED), 'bank_hash':FIXTURES['bank_hash'], 'participants':[]}
    seen = set()
    histogram = Counter()
    for source in inputs:
        identifier = source['participant_id']
        rng = random.Random(f'{SEED}:{identifier}')
        stamps = schedule(rng, source['withdrawal_score_pct'] is None)
        while any(value in seen for pair in stamps.values() for value in pair):
            stamps = schedule(rng, source['withdrawal_score_pct'] is None)
        seen.update(value for pair in stamps.values() for value in pair)
        answers = build_answers(source, rng)
        for paper in answers.values():
            for result in paper['results']:
                if result['type'] in scoring.CODE_TYPES:
                    histogram[f"{result.get('passed_count',0)}/{result.get('total_tests',0)}"] += 1
        plan['participants'].append({'source':source,'stamps':{e:[o.isoformat(),s.isoformat()] for e,(o,s) in stamps.items()},'prepared':answers})
        print('VARIED_PREPARED', identifier, len(answers), flush=True)
    plan['pass_counts'] = dict(histogram)
    plan['complete'] = True
    path = directory / 'plan.json'
    path.write_text(json.dumps(plan),encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / 'plan.sha256').write_text(digest)
    print('VARIED_PLAN_READY',json.dumps({'path':str(path),'sha256':digest,'participants':len(inputs),
        'submissions':sum(len(p['prepared']) for p in plan['participants']),'pass_counts':dict(histogram)}),flush=True)


def run():
    assert hashlib.sha256(scoring.ITEM_BANK_PATH.read_bytes()).hexdigest() == FIXTURES['bank_hash']
    inputs = sources()
    if os.environ.get('VARIED_FIXTURE_MODE', 'prepare') == 'prepare':
        prepare(inputs)
        return
    assert os.environ['VARIED_FIXTURE_MODE'] == 'commit'
    path = Path(os.environ['VARIED_FIXTURE_PLAN']).resolve()
    assert path.parent.parent == BACKUP.parent and path.parent.name.startswith('learner-fixture-plan-20261025-')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (path.parent / 'plan.sha256').read_text().strip()
    plan = json.loads(path.read_text())
    assert plan['complete'] and plan['version'] == IMPORT_VERSION and plan['bank_hash'] == FIXTURES['bank_hash']
    plans = {p['source']['participant_id']:p for p in plan['participants']}
    assert set(plans) == {s['participant_id'] for s in inputs}
    assert all(plans[s['participant_id']]['source'] == s for s in inputs)
    baseline = fingerprints()
    reports = []
    seen_timestamps = set()
    for source in inputs:
        identifier = source['participant_id']
        previous = ParticipantProfile.objects.filter(participant_code=identifier).first()
        if previous:
            assert AssessmentTimeline.objects.filter(student=previous.user, is_synthetic=True,
                provenance__import_version=IMPORT_VERSION).exists(), 'Conflicting existing participant'
            reports.append({'participant':identifier, 'existing':True})
            continue
        stamps = {e:tuple(datetime.fromisoformat(v) for v in pair) for e,pair in plans[identifier]['stamps'].items()}
        assert not any(value in seen_timestamps for pair in stamps.values() for value in pair)
        seen_timestamps.update(value for pair in stamps.values() for value in pair)
        prepared = plans[identifier]['prepared']
        for exam, paper in prepared.items():
            assert len(paper['results']) == 15
            assert round(sum(r['correct'] for r in paper['results'])*100/15) == source[f'{exam}_score_pct']
        with transaction.atomic():
            assert not User.objects.filter(username=identifier).exists()
            assert not User.objects.filter(email__iexact=source['gmail']).exists()
            name = source['student_name'].split(' ', 1)
            user = User(username=identifier, email=source['gmail'], first_name=name[0], last_name=name[1] if len(name)>1 else '')
            user.set_unusable_password()
            user.save()
            profile = ParticipantProfile.objects.create(user=user, participant_code=identifier, role='STUDENT',
                full_name=source['student_name'], school_name=source['college_name'], division=source['division'],
                assigned_arm=source['enrolled_arm'], enrolled_arm=source['enrolled_arm'], grade=str(source['grade']),
                age=source['age_years'], gender=source['gender'], prior_experience=source['prior_experience'],
                device_type=source['device_type'], weekly_study_hours=source['weekly_study_hours'])
            timeline = AssessmentTimeline.objects.create(student=user, window_start=WINDOW_START, window_end=WINDOW_END,
                is_synthetic=True, provenance={'import_version':IMPORT_VERSION,'source':'generated_test_scenario',
                                             'random_seed':plan['seed'],'original_summary':source},
                **{f'{exam}_started_at': opened for exam,(opened,_) in stamps.items()})
            for exam, stored in prepared.items():
                opened, submitted = stamps[exam]
                stored['import_metadata'] = {'kind':'generated_evaluation_fixture','score_source':'actual_grader',
                    'answers_source':'generated_learner_examples','timestamps_source':'simulated',
                    'import_version':IMPORT_VERSION,'generated_at':timezone.now().isoformat()}
                sub = ExamSubmission.objects.create(student=user,exam_type=exam,arm=source['enrolled_arm'],
                    answers=stored,score_pct=source[f'{exam}_score_pct'],grading_status=ExamSubmission.GRADED,graded_at=timezone.now())
                ExamSubmission.objects.filter(pk=sub.pk).update(submitted_at=submitted)
                sitting = PaperSitting.objects.create(student=user,exam_type=exam,arm=source['enrolled_arm'],
                    submitted_at=submitted,submission=sub,last_opened_at=submitted)
                PaperSitting.objects.filter(pk=sitting.pk).update(first_opened_at=opened)
            InteractionLog.objects.create(user=user,event_type='SUMMARY_IMPORT',arm=source['enrolled_arm'],
                payload={'import_key':f'user-supplied-participant-summary:{identifier}:v1','source':source,
                         'synthetic':True,'import_version':IMPORT_VERSION})
            InteractionLog.objects.create(user=user,event_type='EVALUATION_FIXTURE_ATTACH',arm=source['enrolled_arm'],
                payload={'synthetic':True,'import_version':IMPORT_VERSION,'timing_source':'simulated'})
        results = [r for p in prepared.values() for r in p['results'] if r['type'] in scoring.CODE_TYPES]
        histogram = Counter(f"{r.get('passed_count',0)}/{r.get('total_tests',0)}" for r in results)
        report = {'participant':identifier,'exams':len(prepared),'pass_counts':dict(histogram),
                  'first_opened':stamps['pre'][0].isoformat(),'last_submitted':max(s for _,s in stamps.values()).isoformat()}
        reports.append(report)
        print('VARIED_IMPORTED',json.dumps(report),flush=True)
    assert fingerprints() == baseline, 'Unrelated records changed'
    staff = ParticipantProfile.objects.filter(role__in=['EXPERT_TEACHER','RESEARCHER_ADMIN']).select_related('user').first()
    request = APIRequestFactory().get('/api/expert/submissions/')
    force_authenticate(request,user=staff.user)
    response = get_student_submissions(request)
    assert response.status_code == 200
    rows = [r for r in response.data['submissions'] if r['participant_code'] in {s['participant_id'] for s in inputs}]
    assert len(rows) == 237
    by_code = {s['participant_id']:s for s in inputs}
    for row in rows:
        source = by_code[row['participant_code']]
        assert row['score_pct'] == source[f"{row['exam_type']}_score_pct"]
        assert row['timing']['opened_at'] and row['timing']['paper_elapsed_days'] is not None
        assert bool(row['timing']['study_completed_at']) == (source['withdrawal_score_pct'] is not None)
    submitted_dates = [row['submitted_at'] for row in rows]
    assert len(set(submitted_dates)) == len(submitted_dates), 'Duplicate simulated submission timestamps'
    for source in inputs:
        user = ParticipantProfile.objects.get(participant_code=source['participant_id']).user
        timeline = AssessmentTimeline.objects.get(student=user)
        actual = {s.exam_type:s for s in PaperSitting.objects.filter(student=user)}
        for exam, sitting in actual.items():
            assert WINDOW_START <= sitting.first_opened_at <= sitting.submitted_at <= WINDOW_END
        assert actual['post'].first_opened_at >= actual['pre'].submitted_at
        assert actual['transfer'].first_opened_at >= max(actual['post'].submitted_at,
            actual['post'].first_opened_at + timedelta(days=7))
        if 'withdrawal' in actual:
            assert actual['withdrawal'].first_opened_at >= max(actual['transfer'].submitted_at,
                actual['transfer'].first_opened_at + timedelta(days=14))
        else:
            assert source['withdrawal_score_pct'] is None
            assert timeline.withdrawal_started_at is None
    print('VARIED_FIXTURES_COMPLETE',json.dumps({'participants':len(inputs),'submissions':len(rows),
          'seed':plan['seed'],'reports':reports}),flush=True)


os.umask(0o077)
run()
