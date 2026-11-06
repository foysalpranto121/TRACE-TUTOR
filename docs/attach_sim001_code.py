"""Attach generated evaluation fixtures to the four existing SIM-001 summaries.

Invoke with manage.py shell. Computes actual grader results before any writes,
requires exact original scores, and preserves the prior JSON in an audit receipt.
"""
import copy
import hashlib
import json

from django.db import transaction
from django.utils import timezone
from accounts.models import ParticipantProfile
from assessment import scoring
from assessment.models import ExamSubmission
from logging_app.models import InteractionLog

KEY = 'SIM-001:generated-evaluation-code:v1'
EXPECTED_BANK = 'cb2ce8f4634078b0a6de87bd776f7eb4a105cb5d2ee410d1f2f6a54b0c5ebdba'
TARGETS = {'pre': (47, 7), 'post': (87, 13), 'transfer': (60, 9), 'withdrawal': (40, 6)}


def c(body):
    return '#include <stdio.h>\n\nint main(void) {\n' + body.strip() + '\n    return 0;\n}\n'


def html(body):
    return '<!DOCTYPE html>\n<html lang="en">\n<head><title>ICT Assignment</title></head>\n<body>\n' + body + '\n</body>\n</html>\n'


# Deliberate beginner mistakes exercise both passing and failing teacher views.
CODE = {
    'pre': [
        c(r'''    int n, sum = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) sum += i;
    printf("Sum = %d\n", sum);'''),
        c(r'''    int n;
    scanf("%d", &n);
    if (n % 2 == 0) printf("Even\n");
    else printf("Odd\n");'''),
        c(r'''    int n, fact = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) fact *= i;
    printf("Factorial = %d\n", fact);'''),
        c(r'''    int a, b, c, largest;
    scanf("%d %d %d", &a, &b, &c);
    largest = a;
    if (b > largest) largest = b;
    printf("Max = %d\n", largest);'''),
        c(r'''    int n;
    scanf("%d", &n);
    if (n % 2 != 0) printf("%d is Prime\n", n);
    else printf("%d is Not Prime\n", n);'''),
        html('<table>\n<tr><th>Roll</th><th>Marks</th></tr>\n<tr><td>11</td><td>47</td></tr>\n</table>'),
        html('<a href="https://nctb.gov.bd">College</a>\n<img src="college.jpg" alt="College">'),
        html('<ol>\n<li>Bangla</li>\n<li>English</li>\n<li>ICT</li>\n</ol>'),
    ],
    'post': [
        c(r'''    int n;
    long long product = 1;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) product *= i;
    printf("Product = %lld\n", product);'''),
        c(r'''    int n;
    scanf("%d", &n);
    if (n > 0) printf("Positive\n");
    else printf("Negative\n");'''),
        c(r'''    int n, a = 0, b = 1;
    scanf("%d", &n);
    for (int i = 0; i < n; i++) {
        int next = a + b;
        a = b;
        b = next;
    }
    printf("Fibonacci = %d\n", a);'''),
        c(r'''    int a, b, c, minimum;
    scanf("%d %d %d", &a, &b, &c);
    minimum = a;
    if (b < minimum) minimum = b;
    if (c < minimum) minimum = c;
    printf("Minimum = %d\n", minimum);'''),
        c(r'''    int n, count = 0;
    scanf("%d", &n);
    for (int i = 1; i < n; i++) {
        if (n % i == 0) count++;
    }
    printf("Divisors = %d\n", count);'''),
        html('<table>\n<tr><th rowspan="2">Department</th><td>Rahim</td></tr>\n<tr><td>Karim</td></tr>\n</table>'),
        html('<a href="#contact">Contact</a>\n<section id="contact"><h2>Contact</h2><p>College office</p></section>'),
        html('<ul type="disc">\n<li>HTML</li>\n<li>CSS</li>\n<li>JavaScript</li>\n</ul>'),
    ],
    'transfer': [
        c(r'''    int n, sum = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) sum += i * i;
    printf("Sum = %d\n", sum);'''),
        c(r'''    int year;
    scanf("%d", &year);
    if (year % 4 == 0) printf("Leap Year\n");
    else printf("Common Year\n");'''),
        c(r'''    int n, reverse = 0;
    scanf("%d", &n);
    while (n > 0) {
        reverse = reverse * 10 + n % 10;
        n /= 10;
    }
    printf("Reverse = %d\n", reverse);'''),
        c(r'''    float a, b, c, average;
    scanf("%f %f %f", &a, &b, &c);
    average = a + b + c / 3;
    printf("Average = %.2f\n", average);'''),
        c(r'''    int n, temp, sum = 0;
    scanf("%d", &n);
    temp = n;
    while (temp > 0) {
        int digit = temp % 10;
        sum += digit * digit;
        temp /= 10;
    }
    if (sum == n) printf("Armstrong Number\n");
    else printf("Ordinary Number\n");'''),
        html('<form>\n<label for="name">Student name</label>\n<input id="name" name="name" type="text">\n<button type="submit">Register</button>\n</form>'),
        html('<video controls width="640" height="360">\n<source src="lesson.mp4" type="video/mp4">\nYour browser does not support video.\n</video>'),
        html('<ul>\n<li>Computer</li>\n<li>Hardware</li>\n<li>Software</li>\n<li>Internet</li>\n</ul>'),
    ],
    'withdrawal': [
        c(r'''    int n, sum = 0;
    scanf("%d", &n);
    for (int i = 1; i <= n; i++) sum += i;
    printf("Sum = %d\n", sum);'''),
        c(r'''    int marks;
    scanf("%d", &marks);
    if (marks > 80) printf("Grade = A+\n");
    else if (marks > 70) printf("Grade = A\n");
    else printf("Grade = F\n");'''),
        c(r'''    int base, exp, result = 1;
    scanf("%d %d", &base, &exp);
    for (int i = 1; i < exp; i++) result *= base;
    printf("Result = %d\n", result);'''),
        c(r'''    int a, b, temp;
    scanf("%d %d", &a, &b);
    temp = a;
    a = b;
    b = temp;
    printf("After swap: %d %d\n", a, b);'''),
        c(r'''    int n, original, reverse = 0;
    scanf("%d", &n);
    original = n;
    while (n > 0) {
        reverse = n % 10;
        n /= 10;
    }
    if (reverse == original) printf("Palindrome = YES\n");
    else printf("Palindrome = NO\n");'''),
        html('<table>\n<tr><th>Class Routine</th></tr>\n<tr><td>Bangla</td><td>ICT</td></tr>\n</table>'),
        html('<div>\n<img src="book1.jpg">\n<img src="book2.jpg">\n</div>'),
        html('<nav>\n<ul>\n<li><a href="index.html">Home</a></li>\n<li><a href="courses.html">Courses</a></li>\n<li><a href="contact.html">Contact</a></li>\n</ul>\n</nav>'),
    ],
}
MCQ_CORRECT = {'pre': 4, 'post': 6, 'transfer': 5, 'withdrawal': 4}


def run():
    assert hashlib.sha256(scoring.ITEM_BANK_PATH.read_bytes()).hexdigest() == EXPECTED_BANK
    profile = ParticipantProfile.objects.get(participant_code='SIM-001')
    assert profile.user.email == 'arafathossen44@gmail.com'
    assert InteractionLog.objects.filter(user=profile.user, event_type='SUMMARY_IMPORT').exists()
    assert not InteractionLog.objects.filter(user=profile.user, payload__operation_key=KEY).exists(), 'Already applied'
    original = list(ExamSubmission.objects.filter(student=profile.user).order_by('pk'))
    assert len(original) == 4 and {s.exam_type: s.score_pct for s in original} == {k: v[0] for k, v in TARGETS.items()}
    assert all(not s.answers.get('code_answers') and not s.grades.exists() for s in original), 'Existing code or teacher grades: refusing overwrite'
    snapshots = {s.pk: copy.deepcopy(s.answers) for s in original}
    prepared = {}
    for exam, (target_score, target_correct) in TARGETS.items():
        items = scoring.items_for(exam)
        code_items = [i for i in items if i['type'] in scoring.CODE_TYPES]
        assert len(items) == 15 and len(code_items) == len(CODE[exam]) == 8
        code_answers = {i['id']: code for i, code in zip(code_items, CODE[exam])}
        answers = {}
        for idx, item in enumerate(i for i in items if i['type'] not in scoring.CODE_TYPES):
            correct = str(item['keyed_answer'])
            options = [str(o['id']) for o in item['options']]
            answers[item['id']] = correct if idx < MCQ_CORRECT[exam] else next(o for o in options if o != correct)
        score, correct, total, results = scoring.grade_submission(exam, answers, code_answers)
        print('GRADED', exam, score, correct, total, flush=True)
        assert (score, correct, total) == (target_score, target_correct, 15), (exam, results)
        prepared[exam] = {'answers': answers, 'code_answers': code_answers, 'results': results}

    with transaction.atomic():
        rows = list(ExamSubmission.objects.select_for_update().filter(student=profile.user).order_by('pk'))
        assert [s.pk for s in rows] == [s.pk for s in original]
        assert not InteractionLog.objects.filter(user=profile.user, payload__operation_key=KEY).exists()
        for row in rows:
            assert row.answers == snapshots[row.pk] and not row.grades.exists()
            assert row.score_pct == TARGETS[row.exam_type][0]
            stored = copy.deepcopy(row.answers)
            stored.update(prepared[row.exam_type])
            stored['import_metadata'].update({
                'kind': 'generated_evaluation_fixture', 'answers_available': True,
                'answers_source': 'AI_generated_for_user_authorized_teacher_flow_test',
                'operation_key': KEY, 'automatically_verified_score': row.score_pct,
                'note': 'Generated answers for evaluation workflow testing; not recovered participant work.',
            })
            row.answers = stored
            row.graded_at = timezone.now()
            row.save(update_fields=['answers', 'graded_at'])
        InteractionLog.objects.create(
            user=profile.user, event_type='EVALUATION_FIXTURE_ATTACH', arm='ANSWER_ONLY',
            payload={'operation_key': KEY, 'synthetic': True,
                     'purpose': 'User-authorized teacher evaluation workflow test',
                     'previous_answers': {str(k): v for k, v in snapshots.items()},
                     'submission_ids': [s.pk for s in rows]},
        )
    print('ATTACHED', json.dumps({'participant': 'SIM-001', 'submissions': [s.pk for s in rows], 'code_answers': 32}), flush=True)


run()
