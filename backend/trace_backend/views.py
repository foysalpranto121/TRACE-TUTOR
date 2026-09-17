"""Views that belong to the site rather than to an app: the health probe, the built
React app, and uploaded media. Each is a way a deployment could look healthy while quietly
broken, so all three are covered in trace_backend/tests.py."""
import logging

from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_safe
from django.views.static import serve

logger = logging.getLogger(__name__)


@require_safe
def health(request):
    """Unauthenticated liveness probe for a supervisor or uptime monitor.

    200 while the database answers, 503 otherwise, and nothing else is revealed. Exempt
    from the https redirect (SECURE_REDIRECT_EXEMPT) so a probe on the box itself can use
    plain http."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        database = 'ok'
    except Exception:
        logger.exception('health probe: database unreachable')
        database = 'unreachable'
    ok = database == 'ok'
    response = JsonResponse(
        {'status': 'ok' if ok else 'degraded', 'database': database},
        status=200 if ok else 503,
    )
    response['Cache-Control'] = 'no-store'
    return response


@csrf_exempt  # nothing to protect: require_safe rejects every write with 405 before CSRF's 403
@require_safe
def spa_index(request):
    """The React app's shell, for every client-side route.

    The bundles it references live under /assets/ and are served by whitenoise with
    immutable caching. The shell itself is revalidated on every load (no-cache) so a new
    build is picked up the moment it is deployed."""
    dist = settings.FRONTEND_DIST
    if not (dist / 'index.html').is_file():
        return HttpResponse(
            'The frontend has not been built. Run `npm run build` in frontend/ and restart '
            'the server, or use the Vite dev server (`npm run dev`, http://localhost:3000) '
            'during development.\n',
            status=503,
            content_type='text/plain; charset=utf-8',
        )
    response = serve(request, 'index.html', document_root=str(dist))
    response['Cache-Control'] = 'no-cache'
    return response


@require_safe
def media_file(request, path):
    """Uploaded files (profile avatars).

    Django serves them only while SERVE_MEDIA is on: fine for a single-site lab server,
    while anything internet-facing should put a file server in front. Unlike Django's
    django.conf.urls.static.static() helper, this does not silently switch itself off when
    DEBUG is off, which is exactly when a deployment needs it."""
    if not settings.SERVE_MEDIA:
        raise Http404
    return serve(request, path, document_root=str(settings.MEDIA_ROOT))
