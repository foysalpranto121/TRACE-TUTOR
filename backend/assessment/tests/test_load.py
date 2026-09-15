"""Concurrent-submission load test.

A lab session ends with the whole cohort pressing Submit inside the same minute. Each
submission grades 5 C programs by compiling and running them, so this is the one
moment the platform is CPU-bound with everyone waiting on it.

Opt in with TRACE_LOAD_TEST=<cohort size>; it takes real minutes. Reports latency
percentiles and fails if any submission errors or the slowest exceeds the budget.
"""
import os
import statistics
import threading
import time
import unittest

import json
import logging
import subprocess
import sys
import urllib.error
import urllib.request
from django.contrib.auth.models import User
from django.db import connections
from django.test import LiveServerTestCase, override_settings
from rest_framework.authtoken.models import Token

from accounts.models import ParticipantProfile
from assessment import grading, scoring
from assessment.models import ExamSubmission

COHORT = int(os.environ.get('TRACE_LOAD_TEST', '0') or 0)
LATENCY_BUDGET_SEC = float(os.environ.get('TRACE_LOAD_BUDGET', '30'))
# TRACE_LOAD_WORKER=1 measures the deployment shape where a separate
# `manage.py grade_submissions` process does the compiling and the web process only
# queues. The worker is started as a real subprocess pointed at the test database.
USE_WORKER = os.environ.get('TRACE_LOAD_WORKER', '0') == '1'

# LiveServerTestCase forces DEBUG off, which routes 500 tracebacks to the (unconfigured)
# mail_admins handler and nowhere else. A load test that hides why requests failed is
# not much use, so send them to stderr here.
_request_log = logging.getLogger('django.request')
_request_log.setLevel(logging.ERROR)
_request_log.addHandler(logging.StreamHandler(sys.stderr))

# The test live server is Django's development server, whose TCP listen backlog is
# socketserver's default of 5. Sixty browsers connecting in the same instant overflow
# that and get their connection reset before the request is even read - which says
# nothing about the application. A real deployment (gunicorn behind nginx) has a
# backlog in the hundreds, so give the harness the same.
from django.core.servers import basehttp  # noqa: E402
basehttp.ThreadedWSGIServer.request_queue_size = 256

# Poll at the cadence the real client uses (AssessmentPage GRADING_POLL_MS).
POLL_SEC = 1.5

C_SRC = '#include <stdio.h>\nint main(){ printf("hello\\n"); return 0; }\n'
HTML_SRC = ('<!DOCTYPE html><html><head><title>t</title></head>'
            '<body><table><tr><td>1</td></tr></table></body></html>')


@unittest.skipUnless(COHORT > 0, 'set TRACE_LOAD_TEST=<n> to run the load test')
@override_settings(GRADING_MODE='worker' if USE_WORKER else 'thread')
class ConcurrentSubmissionTests(LiveServerTestCase):
    """N participants submit the pre-test simultaneously through the real HTTP stack."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        items = scoring.items_for('pre')
        cls.payload = {
            'exam_type': 'pre',
            'answers': {i['id']: 'a' for i in items if i.get('type') == 'concept_mcq'},
            'code_answers': {i['id']: (C_SRC if i['type'] == 'c_programming' else HTML_SRC)
                             for i in items if i.get('type') in scoring.CODE_TYPES},
        }

    def setUp(self):
        super().setUp()
        self.tokens = []
        for n in range(COHORT):
            user = User.objects.create_user(username=f'load{n:03d}', password='Testpass!2345')
            ParticipantProfile.objects.create(user=user, role='STUDENT', consent_given=True)
            self.tokens.append(Token.objects.create(user=user).key)
        self.worker = None
        if USE_WORKER:
            # A genuine separate process, exactly as it would be deployed, aimed at the
            # test database the live server is using.
            env = dict(os.environ, DB_NAME=connections['default'].settings_dict['NAME'],
                       GRADING_MODE='worker')
            self.worker = subprocess.Popen(
                [sys.executable, 'manage.py', 'grade_submissions', '--interval', '0.5'],
                env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(self._stop_worker)

    def _stop_worker(self):
        if self.worker and self.worker.poll() is None:
            self.worker.terminate()
            try:
                self.worker.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.worker.kill()

    def _call(self, token, path, body=None):
        request = urllib.request.Request(
            f'{self.live_server_url}{path}',
            data=json.dumps(body).encode('utf-8') if body is not None else None,
            headers={'Authorization': f'Token {token}', 'Content-Type': 'application/json'},
            method='POST' if body is not None else 'GET',
        )
        with urllib.request.urlopen(request, timeout=LATENCY_BUDGET_SEC * 3) as response:
            return response.status, json.loads(response.read().decode('utf-8'))

    def submit(self, token, out, index):
        """Two numbers per participant: how long Submit took to come back (what they
        stare at), and how long until their marks were ready (what they wait for)."""
        started = time.perf_counter()
        try:
            status, body = self._call(token, '/api/assessment/submit/', self.payload)
            request_latency = time.perf_counter() - started
            deadline = started + LATENCY_BUDGET_SEC * 3
            while body.get('grading_status') in ('pending', 'grading'):
                if time.perf_counter() > deadline:
                    break
                time.sleep(POLL_SEC)
                status, body = self._call(token, f'/api/assessment/submissions/{body["submission_id"]}/')
            out[index] = {
                'request': request_latency,
                'graded': time.perf_counter() - started,
                'status': status,
                'grading_status': body.get('grading_status'),
                'error': body.get('error'),
            }
        except urllib.error.HTTPError as exc:
            out[index] = {'request': time.perf_counter() - started, 'graded': None,
                          'status': exc.code, 'grading_status': None, 'error': exc.read()[:200]}
        except Exception as exc:  # noqa: BLE001 - every failure mode must be reported
            out[index] = {'request': time.perf_counter() - started, 'graded': None,
                          'status': None, 'grading_status': None, 'error': repr(exc)}

    def probe_web_tier(self):
        """The same burst against an endpoint that does no grading at all.

        Separates two questions the headline numbers blur together: how much of the
        Submit latency is the web tier simply serving N simultaneous requests, and how
        much is the submission itself. If this is slow too, the fix is more web
        workers, not anything in assessment/.
        """
        timings = [None] * COHORT
        gate = threading.Barrier(COHORT)

        def hit(index):
            gate.wait()
            started = time.perf_counter()
            try:
                self._call(self.tokens[index], '/api/code/status/')
            except Exception:  # noqa: BLE001 - a probe failure is just a timing of None
                timings[index] = None
                return
            timings[index] = time.perf_counter() - started

        threads = [threading.Thread(target=hit, args=(i,)) for i in range(COHORT)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ok = sorted(t for t in timings if t is not None)
        return statistics.median(ok), ok[min(len(ok) - 1, int(len(ok) * 0.95))], COHORT - len(ok)

    def test_the_whole_cohort_submitting_at_once(self):
        probe_p50, probe_p95, probe_failures = self.probe_web_tier()

        results = [None] * COHORT
        gate = threading.Barrier(COHORT)

        def worker(index):
            gate.wait()  # everyone fires within the same instant
            self.submit(self.tokens[index], results, index)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(COHORT)]
        wall_start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.perf_counter() - wall_start

        def pct(values, q):
            values = sorted(values)
            return values[min(len(values) - 1, int(len(values) * q))]

        requests_ = [r['request'] for r in results]
        graded = [r['graded'] for r in results if r['graded'] is not None]
        failures = [r for r in results if r['status'] not in (200, 202) or r['grading_status'] != 'graded']

        print(f'\n--- {COHORT} concurrent submissions ---')
        print(f'grading mode            : {"separate worker process" if USE_WORKER else "threads in the web process"}')
        print(f'grading concurrency     : {grading._concurrency()} submissions '
              f'x {scoring.GRADE_WORKERS} compile workers ({os.cpu_count()} CPUs)')
        print(f'wall clock (all graded) : {wall:.1f}s')
        print(f'web-tier probe  p50/p95 : {probe_p50:.2f}s / {probe_p95:.2f}s  '
              f'(GET /api/code/status/, no grading; {probe_failures} failed)')
        print(f'submit request  p50/p95 : {statistics.median(requests_):.2f}s / {pct(requests_, 0.95):.2f}s')
        print(f'time to marks   p50/p95 : {statistics.median(graded):.1f}s / {pct(graded, 0.95):.1f}s')
        print(f'time to marks   max     : {max(graded):.1f}s')
        print(f'failures                : {len(failures)}')
        for failure in failures[:5]:
            print('   ', failure)
        print(f'rows saved              : {ExamSubmission.objects.count()} / {COHORT}')
        print(f'rows graded             : {ExamSubmission.objects.filter(grading_status="graded").count()} / {COHORT}')

        self.assertEqual(failures, [], 'every submission must be saved and graded')
        self.assertEqual(ExamSubmission.objects.count(), COHORT)
        # The submission must add no more than a little over what the web tier already
        # costs for a burst of this size: the answers are safe the moment it returns.
        # What the web tier itself costs under a burst is a deployment question (number
        # of gunicorn workers), reported by the probe rather than judged here.
        self.assertLessEqual(pct(requests_, 0.95), max(3.0, probe_p95 * 2 + 1.0),
                             f'submit p95 was {pct(requests_, 0.95):.2f}s against a web-tier '
                             f'probe p95 of {probe_p95:.2f}s: the submission itself is slow')
        self.assertLessEqual(max(graded), LATENCY_BUDGET_SEC,
                             f'slowest participant waited {max(graded):.1f}s for marks; '
                             f'budget is {LATENCY_BUDGET_SEC}s')
