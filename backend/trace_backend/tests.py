"""Site-level plumbing: the health probe, serving the built React app, uploaded media and
production logging.

None of this belongs to an app, and each item was a way for a deployment to look healthy
while quietly broken: avatars that 404 once DEBUG is off, a client-side route that 404s on
refresh, a 500 that leaves no trace in any log."""
import logging
import tempfile
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils.log import AdminEmailHandler, RequireDebugTrue


def body(response):
    """FileResponse streams; plain responses do not."""
    return b''.join(response.streaming_content) if response.streaming else response.content


class HealthProbeTests(TestCase):
    def test_answers_without_authentication(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'database': 'ok'})
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_only_safe_methods(self):
        self.assertEqual(self.client.post('/api/health/').status_code, 405)


class SpaShellTests(TestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dist = Path(tmp.name)
        (self.dist / 'index.html').write_text(
            '<!DOCTYPE html><html><body><div id="root"></div></body></html>', encoding='utf-8'
        )

    def test_every_client_route_gets_the_shell(self):
        with override_settings(FRONTEND_DIST=self.dist):
            # /admin and /admin/rag are the React researcher screens, which is why the
            # Django admin is mounted at /django-admin/ instead.
            for route in ('/', '/login', '/workspace', '/assessment', '/admin', '/admin/rag'):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200, route)
                self.assertIn(b'id="root"', body(response), route)
                # A new build must be picked up on the next load, never served from cache.
                self.assertEqual(response['Cache-Control'], 'no-cache', route)

    def test_api_admin_and_files_are_not_swallowed(self):
        with override_settings(FRONTEND_DIST=self.dist):
            # A wrong API path must stay a 404, not a 200 full of HTML the client cannot parse.
            self.assertEqual(self.client.get('/api/does-not-exist/').status_code, 404)
            # The Django admin answers with its own login redirect, not the app shell.
            response = self.client.get('/django-admin/')
            self.assertEqual(response.status_code, 302)
            self.assertIn('/django-admin/login/', response['Location'])
            # A stale bundle name, or any path with an extension, is a missing file.
            self.assertEqual(self.client.get('/assets/index-stale000.js').status_code, 404)
            self.assertEqual(self.client.get('/favicon.svg').status_code, 404)
            # ... and APPEND_SLASH must not turn it into a redirect to a served route.
            self.assertEqual(self.client.get('/favicon.svg/').status_code, 404)

    def test_writes_are_refused_with_405_not_a_csrf_403(self):
        # The default test client skips CSRF checks; a real browser or monitor would not.
        with override_settings(FRONTEND_DIST=self.dist):
            strict = Client(enforce_csrf_checks=True)
            self.assertEqual(strict.post('/workspace').status_code, 405)

    def test_unbuilt_frontend_says_so(self):
        with override_settings(FRONTEND_DIST=self.dist / 'not-built'):
            response = self.client.get('/workspace')
            self.assertEqual(response.status_code, 503)
            self.assertIn(b'npm run build', response.content)


class MediaServingTests(TestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.media = Path(tmp.name)
        (self.media / 'avatars').mkdir()
        (self.media / 'avatars' / 'a.webp').write_bytes(b'RIFF-not-really-webp')

    def test_served_with_debug_off_when_enabled(self):
        # The test runner forces DEBUG=False, which is precisely when Django's static()
        # helper used to go silent and every avatar 404ed on a deployed server.
        with override_settings(MEDIA_ROOT=self.media, SERVE_MEDIA=True, DEBUG=False):
            response = self.client.get('/media/avatars/a.webp')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(body(response), b'RIFF-not-really-webp')

    def test_refused_when_disabled(self):
        with override_settings(MEDIA_ROOT=self.media, SERVE_MEDIA=False):
            self.assertEqual(self.client.get('/media/avatars/a.webp').status_code, 404)

    def test_no_listing_and_no_traversal(self):
        with override_settings(MEDIA_ROOT=self.media, SERVE_MEDIA=True):
            self.assertEqual(self.client.get('/media/avatars/').status_code, 404)
            # safe_join refuses to leave MEDIA_ROOT; Django reports that as 400 or 404.
            self.assertIn(self.client.get('/media/../.env').status_code, (400, 404))


class ProductionLoggingTests(SimpleTestCase):
    def test_request_errors_reach_stderr_whatever_debug_is(self):
        """Django's default only prints while DEBUG is on and otherwise emails ADMINS, who
        are not configured, so a 500 during a live session left no trace. The 'django'
        logger must have a plain stream handler that is not gated on DEBUG."""
        handlers = logging.getLogger('django').handlers
        self.assertTrue(any(type(handler) is logging.StreamHandler for handler in handlers), handlers)
        for handler in handlers:
            self.assertNotIsInstance(handler, AdminEmailHandler)
            self.assertFalse(any(isinstance(f, RequireDebugTrue) for f in handler.filters), handler)

    def test_project_loggers_are_handled(self):
        # tutor.sandbox, assessment.grading and friends propagate to the root logger.
        self.assertTrue(logging.getLogger().handlers)


class SystemStatusTests(TestCase):
    """The staff status page must be locked down, must never 500 because one component is
    down, and must name the problems an operator has to fix before a cohort."""

    def _client(self, role):
        from django.contrib.auth.models import User
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient
        from accounts.models import ParticipantProfile
        user = User.objects.create_user(username=f'u_{role.lower()}', password='Testpass!2345')
        ParticipantProfile.objects.create(user=user, role=role, consent_given=True)
        return APIClient(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=user).key)

    def test_requires_a_staff_token(self):
        self.assertIn(Client().get('/api/admin/status/').status_code, (401, 403))
        self.assertEqual(self._client('STUDENT').get('/api/admin/status/').status_code, 403)

    def test_reports_every_component_and_the_problems(self):
        response = self._client('RESEARCHER_ADMIN').get('/api/admin/status/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        for key in ('status', 'problems', 'database', 'sandbox', 'compiler', 'tutor', 'corpus', 'grading', 'logging', 'backup', 'disk'):
            self.assertIn(key, data)
        self.assertEqual(data['database'], 'ok')
        self.assertIsInstance(data['problems'], list)
        self.assertIn(data['status'], ('ok', 'degraded', 'down'))
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_a_missing_backup_is_named_as_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BACKUP_DIR=Path(tmp) / 'none'):
            data = self._client('EXPERT_TEACHER').get('/api/admin/status/').json()
        self.assertTrue(any('backup' in p for p in data['problems']), data['problems'])
        self.assertIsNone(data['backup']['latest'])

    def test_a_broken_component_does_not_break_the_page(self):
        from unittest.mock import patch
        with patch('tutor.sandbox.status', side_effect=RuntimeError('docker exploded')):
            response = self._client('RESEARCHER_ADMIN').get('/api/admin/status/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sandbox'], {})
