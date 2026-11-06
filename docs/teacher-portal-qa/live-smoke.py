"""Real browser -> Django -> disposable PostgreSQL -> Docker smoke test. No API mocks."""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ['DJANGO_SETTINGS_MODULE'] = 'trace_backend.qa_settings'
import django
django.setup()
from django.conf import settings
from django.contrib.auth.models import User
from django.test import LiveServerTestCase, override_settings
from django.urls import re_path
from django.views.static import serve
from django.db import connections
from trace_backend.urls import urlpatterns as app_urls
from trace_backend.qa_runner import TeacherQARunner
from accounts.models import ParticipantProfile
from assessment.models import ExamSubmission, ExpertGrade, ExpertRating
from assessment import scoring
from tutor import sandbox

# Serve the actual built frontend, preserving all actual backend API routes.
urlpatterns = [re_path(r'^(?P<path>.*\.[A-Za-z0-9]+)$', serve,
                       {'document_root': str(ROOT / 'frontend' / 'dist')})] + app_urls

@override_settings(ROOT_URLCONF=__name__, ALLOWED_HOSTS=['127.0.0.1', 'localhost', 'testserver'],
                   SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
                   CODE_SANDBOX='docker', CODE_SANDBOX_REQUIRED=True)
class LiveSmoke(LiveServerTestCase):
    host = '127.0.0.1'

    def test_browser_real_requests(self):
        self.assertTrue(connections['default'].settings_dict['NAME'].startswith('test_trace_teacher_qa_'))
        self.assertEqual(sandbox.status()['tier'], 'docker')
        password = 'Disposable-Smoke-Only!2345'
        def account(name, role):
            user = User.objects.create_user(username=name, password=password)
            ParticipantProfile.objects.create(user=user, role=role, full_name='Disposable Smoke Account',
                                               school_name='Disposable QA School', preferred_language='en',
                                               assigned_arm='REASONING_VISIBLE', consent_given=True)
            return user
        teacher = account('qa-live-teacher', 'EXPERT_TEACHER')
        student = account('qa-live-student', 'STUDENT')
        untouched = account('qa-live-other-reviewer', 'EXPERT_TEACHER')
        zero = ExamSubmission.objects.create(student=student, exam_type='post', score_pct=0)
        missing = ExamSubmission.objects.create(student=student, exam_type='pre', score_pct=None)
        preserved_grade = ExpertGrade.objects.create(submission=zero, expert_user=untouched, assigned_marks=31,
                                                      feedback_comments='Preserved fixture grade')
        preserved_rating = ExpertRating.objects.create(expert_user=untouched, item_key=scoring.all_items()[0][1]['id'],
                                                        feedback='Preserved fixture research rating')
        expected_grade = (preserved_grade.assigned_marks, preserved_grade.feedback_comments)
        expected_rating = (preserved_rating.alignment_score, preserved_rating.feedback)
        env = dict(os.environ, TRACE_QA_ORIGIN=self.live_server_url, TRACE_QA_PASSWORD=password)
        completed = subprocess.run(['node', str(ROOT / 'docs/teacher-portal-qa/live-browser.mjs')],
                                   cwd=ROOT, env=env, timeout=360, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace')
        print(completed.stdout)
        print(completed.stderr)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        preserved_grade.refresh_from_db()
        preserved_rating.refresh_from_db()
        self.assertEqual((preserved_grade.assigned_marks, preserved_grade.feedback_comments), expected_grade)
        self.assertEqual((preserved_rating.alignment_score, preserved_rating.feedback), expected_rating)
        missing.refresh_from_db()
        zero.refresh_from_db()
        self.assertIsNone(missing.score_pct)
        self.assertEqual(zero.score_pct, 0)
        self.assertEqual(ExpertRating.objects.filter(expert_user=teacher).count(), 1)
        self.assertEqual(ExpertGrade.objects.get(expert_user=teacher, submission=missing).assigned_marks, 88)
        self.assertFalse(subprocess.check_output(['docker', 'ps', '-aq', '--filter', 'name=trace-run-']).strip())

runner = TeacherQARunner(verbosity=2, interactive=False)
runner.setup_test_environment()
old_config = None
try:
    old_config = runner.setup_databases()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LiveSmoke)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
finally:
    if old_config is not None:
        connections.close_all()
        runner.teardown_databases(old_config)
    runner.teardown_test_environment()
sys.exit(0 if result.wasSuccessful() else 1)
