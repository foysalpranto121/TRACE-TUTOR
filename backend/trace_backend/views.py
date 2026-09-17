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


def _latest_backup():
    """The newest backup folder's manifest, or None. Cheap: one directory listing."""
    import json
    root = settings.BACKUP_DIR
    try:
        candidates = sorted((p for p in root.iterdir() if p.is_dir() and (p / 'manifest.json').exists()),
                            key=lambda p: p.name, reverse=True)
    except OSError:
        return None
    for folder in candidates[:1]:
        try:
            data = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
            data['folder'] = str(folder)
            return data
        except (OSError, ValueError):
            return {'folder': str(folder), 'error': 'manifest unreadable'}
    return None


def system_status(request):
    """Everything an operator needs to know a deployment is actually fit to serve a cohort.

    The public /api/health/ probe answers one question - is the process up and can it reach
    the database - and reveals nothing else. This is the staff-only view behind it: sandbox
    tier, corpus state, tutor model, grading queue, backups and disk. Wired up in urls.py
    with a DRF permission; it is a plain view so it can be imported without DRF's decorators.
    """
    import shutil
    from django.db.models import Count
    from django.utils import timezone
    from assessment.models import ExamSubmission
    from assessment.manifest import _git
    from curriculum.models import IngestRun, OcrPage
    from curriculum.ocr_ingest import DOCS, INGEST_STATE, RAG_DIR, corpus_version
    from curriculum.rag_engine import rag_engine_instance
    from tutor import runner, sandbox
    from trace_backend import gemini, llm

    def safe(fn, default=None):
        try:
            return fn()
        except Exception as e:  # a status page must never 500 because one component is down
            logger.warning('system status: %s failed: %s', getattr(fn, '__name__', 'component'), e)
            return default

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        database = 'ok'
    except Exception:
        database = 'unreachable'

    last_run = safe(lambda: IngestRun.objects.order_by('-pk').first())
    grading = safe(lambda: {row['grading_status']: row['n'] for row in
                            ExamSubmission.objects.values('grading_status').annotate(n=Count('id'))}, {})
    pages = safe(lambda: {
        'transcribed': OcrPage.objects.count(),
        'blank': OcrPage.objects.filter(thin=True).count(),
        'unindexed': OcrPage.objects.filter(thin=False, indexed_chunks=0).count(),
    }, {})
    disk = safe(lambda: shutil.disk_usage(settings.BASE_DIR))
    backup = safe(_latest_backup)
    problems = []
    box = safe(sandbox.status, {})
    if not box.get('allowed', True):
        problems.append('code execution is refused: sandbox below the required tier')
    if not safe(llm.configured, False):
        problems.append('tutor model is not configured')
    if safe(rag_engine_instance.vector_count, 0) == 0:
        problems.append('vector index is empty: the tutor is answering from seed passages')
    if grading.get('failed'):
        problems.append(f"{grading['failed']} submission(s) failed grading")
    if backup is None:
        problems.append('no backup has ever been taken (run: python manage.py backup_study)')
    elif backup.get('taken_at'):
        try:
            age_h = (timezone.now() - timezone.datetime.fromisoformat(backup['taken_at'])).total_seconds() / 3600
            if age_h > 26:
                problems.append(f'last backup is {age_h / 24:.1f} days old')
        except (TypeError, ValueError):
            pass
    if disk and disk.free < 2 * 1024 ** 3:
        problems.append(f'less than 2 GB free on the application disk ({disk.free / 1024 ** 3:.1f} GB)')
    if settings.DEBUG:
        problems.append('DEBUG is on')

    data = {
        'status': 'ok' if database == 'ok' and not problems else ('degraded' if database == 'ok' else 'down'),
        'problems': problems,
        'checked_at': timezone.now().isoformat(),
        'database': database,
        'debug': settings.DEBUG,
        'code_commit': safe(lambda: _git('rev-parse', '--short', 'HEAD')),
        'sandbox': box,
        'compiler': safe(runner.compiler_status, {}),
        'tutor': {
            'provider': safe(llm.provider), 'model': safe(llm.model_name), 'chain': safe(llm.model_chain, []),
            'configured': safe(llm.configured, False), 'temperature': safe(llm.generation_temperature),
            'parameters_rejected_by_model': safe(llm.rejected_parameters, []),
            'embedding_model': safe(gemini.embed_model_name), 'gemini_configured': safe(gemini.api_key) is not None,
        },
        'corpus': {
            'version': safe(corpus_version, 0),
            'vector_count': safe(rag_engine_instance.vector_count, 0),
            'pages': pages,
            'documents': [{'name': n, 'present': (RAG_DIR / n).exists(),
                           'pages_recorded': safe(lambda n=n: OcrPage.objects.filter(document=n).count(), 0)}
                          for n in DOCS],
            'ingest_running': bool(INGEST_STATE.get('running')),
            'last_run': {
                'id': last_run.pk, 'status': last_run.status, 'started_at': last_run.started_at.isoformat(),
                'finished_at': last_run.finished_at.isoformat() if last_run.finished_at else None,
                'warnings': len(last_run.warnings or []), 'error': last_run.error,
            } if last_run else None,
        },
        'grading': {'mode': settings.GRADING_MODE, 'queue': grading},
        'logging': {'level': settings.LOG_LEVEL, 'file': settings.LOG_FILE or None},
        'backup': {'directory': str(settings.BACKUP_DIR), 'latest': backup},
        'disk': {'free_gb': round(disk.free / 1024 ** 3, 1), 'total_gb': round(disk.total / 1024 ** 3, 1)} if disk else None,
    }
    response = JsonResponse(data)
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
