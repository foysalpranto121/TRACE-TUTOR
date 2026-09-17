import re

from django.conf import settings
from django.core.cache import caches
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsResearcher, IsStaffRole
from trace_backend.throttles import IngestThrottle

from django.db.models import Count, Q, Sum

from .rag_engine import rag_engine_instance
from .ocr_ingest import INGEST_STATE, start_background_ingest, DOCS, RAG_DIR, load_cache
from .models import CurriculumPassage, IngestRun, OcrPage

MAX_SEARCH_K = 50
MAX_PASSAGES = 500
PAGE_RANGE_RE = re.compile(r'^\s*(\d{1,5})\s*-\s*(\d{1,5})\s*$')


def _bounded_int(value, default, low, high):
    """Query parameters come from the wire: a non-numeric k used to 500 the endpoint."""
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


@api_view(['POST'])
@permission_classes([IsStaffRole])
def search_curriculum(request):
    """Retrieval over the OCR'd textbook corpus. Staff only: the passages are verbatim
    copyrighted NCTB text, and this is a research inspection tool, not a student feature."""
    query = request.data.get('query', '')
    language = request.data.get('language', None)
    k = _bounded_int(request.data.get('k'), 8, 1, MAX_SEARCH_K)

    results = rag_engine_instance.search_passages(query, language=language, k=k)
    return Response({
        'query': query,
        'results_count': len(results),
        'retrieval_backend': rag_engine_instance.last_backend,
        'passages': results,
    })


@api_view(['POST'])
@permission_classes([IsResearcher])
@throttle_classes([IngestThrottle])
def ingest_curriculum(request):
    """Starts a background OCR + indexing run. Researcher-only and rate limited: a full
    pass is hours of billed vision-model calls against the study's Gemini quota."""
    pdfs = request.data.get('pdfs') or None
    page_range = request.data.get('pages') or None
    if page_range:
        match = PAGE_RANGE_RE.match(str(page_range))
        if not match:
            return Response({'error': 'pages must look like "140-170".'}, status=400)
        lo, hi = int(match.group(1)), int(match.group(2))
        if lo > hi:
            return Response({'error': 'pages must start at or below the end page.'}, status=400)
        page_range = (lo, hi)
    started = start_background_ingest(
        pdf_names=pdfs, page_range=page_range,
        workers=_bounded_int(request.data.get('workers'), 3, 1, 8),
        ocr=not request.data.get('index_only', False),
        reindex=bool(request.data.get('reindex', False)),
        retry_empty=bool(request.data.get('retry_empty', False)),
        trigger='api', triggered_by_id=request.user.pk,
    )
    return Response({
        'status': 'started' if started else 'already_running',
        'rag_directory': str(RAG_DIR),
        'files_found': [n for n in DOCS if (RAG_DIR / n).exists()],
        'state': INGEST_STATE,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def rag_status(request):
    """Reads the OCR page caches on disk, so it is memoised in memory for a few seconds."""
    data = caches['default'].get('rag-status:v1')
    hit = data is not None
    if not hit:
        data = _build_rag_status()
        caches['default'].set('rag-status:v1', data, settings.RAG_STATUS_CACHE_SECONDS)
    response = Response(data)
    response['X-Trace-Cache'] = 'hit' if hit else 'miss'
    return response


def _serialize_run(run, with_log=False):
    data = {
        'id': run.pk,
        'status': run.status,
        'stage': run.stage,
        'trigger': run.trigger,
        'triggered_by': run.triggered_by.username if run.triggered_by_id else None,
        'started_at': run.started_at.isoformat(),
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'documents': run.documents,
        'page_range': run.page_range,
        'options': {'ocr': run.ocr, 'reindex': run.reindex, 'retry_empty': run.retry_empty, 'workers': run.workers},
        'done_pages': run.done_pages,
        'total_pages': run.total_pages,
        'indexed_chunks': run.indexed_chunks,
        'relabelled_chunks': run.relabelled_chunks,
        'vector_count_after': run.vector_count_after,
        'warnings': run.warnings,
        'error': run.error,
        'embedding_model': run.embedding_model,
        'ocr_model': run.ocr_model,
        'code_commit': run.code_commit,
    }
    if with_log:
        data['log'] = run.log
    return data


def _page_summary(name):
    """Per-document page status, straight from the OcrPage table."""
    rows = OcrPage.objects.filter(document=name)
    agg = rows.aggregate(
        pages=Count('id'),
        thin=Count('id', filter=Q(thin=True)),
        indexed=Count('id', filter=Q(indexed_chunks__gt=0)),
        chunks=Sum('indexed_chunks'),
    )
    chapters = list(rows.values('chapter').annotate(pages=Count('id'), chunks=Sum('indexed_chunks')).order_by('chapter'))
    return {
        'pages_recorded': agg['pages'] or 0,
        'pages_thin': agg['thin'] or 0,
        'pages_indexed': agg['indexed'] or 0,
        'chunks_in_index': agg['chunks'] or 0,
        'thin_pages': list(rows.filter(thin=True).values_list('page', flat=True)),
        'unindexed_pages': list(rows.filter(indexed_chunks=0, thin=False).values_list('page', flat=True)),
        'chapters': chapters,
    }


def _build_rag_status():
    docs = []
    for name, info in DOCS.items():
        path = RAG_DIR / name
        docs.append({
            'name': name,
            'exists': path.exists(),
            'size_mb': round(path.stat().st_size / 1e6, 1) if path.exists() else 0,
            'language': info['language'],
            'ocr_pages_cached': len(load_cache(name)),
            'db_chunks': CurriculumPassage.objects.filter(chroma_id__startswith=path.stem.replace(' ', '_') + '_p').count(),
            'pages': _page_summary(name),
        })
    last = IngestRun.objects.select_related('triggered_by').first()
    return {
        'engine': rag_engine_instance.status(),
        # 'ingest' is the live in-process view; 'last_run' is what PostgreSQL holds and survives a restart.
        'ingest': dict(INGEST_STATE),
        'last_run': _serialize_run(last) if last else None,
        'runs_recorded': IngestRun.objects.count(),
        'documents': docs,
    }


@api_view(['GET'])
@permission_classes([IsStaffRole])
def ingest_runs(request):
    """Every ingestion run ever recorded, newest first. ?id=<n> returns one run with its full log."""
    run_id = request.GET.get('id')
    if run_id:
        try:
            run = IngestRun.objects.select_related('triggered_by').get(pk=int(run_id))
        except (ValueError, IngestRun.DoesNotExist):
            return Response({'error': 'No such run.'}, status=404)
        return Response(_serialize_run(run, with_log=True))
    limit = _bounded_int(request.GET.get('limit'), 50, 1, 500)
    runs = IngestRun.objects.select_related('triggered_by')[:limit]
    return Response({'count': IngestRun.objects.count(), 'runs': [_serialize_run(r) for r in runs]})


@api_view(['GET'])
@permission_classes([IsStaffRole])
def ocr_pages(request):
    """Per-page transcription and indexing status for one document.
    ?document=<pdf name> (defaults to the Bangla textbook); ?thin=1 or ?unindexed=1 to filter."""
    document = request.GET.get('document') or next(iter(DOCS))
    rows = OcrPage.objects.filter(document=document)
    if request.GET.get('thin'):
        rows = rows.filter(thin=True)
    if request.GET.get('unindexed'):
        rows = rows.filter(indexed_chunks=0)
    return Response({
        'document': document,
        'summary': _page_summary(document),
        'pages': [
            {
                'page': r.page, 'chars': r.chars, 'thin': r.thin, 'attempts': r.attempts,
                'chapter': r.chapter, 'indexed_chunks': r.indexed_chunks,
                'transcribed_at': r.transcribed_at.isoformat() if r.transcribed_at else None,
                'indexed_at': r.indexed_at.isoformat() if r.indexed_at else None,
                'last_run': r.last_run_id,
            }
            for r in rows
        ],
    })


@api_view(['GET'])
@permission_classes([IsStaffRole])
def get_passages(request):
    """Raw corpus dump for index inspection. Staff only - verbatim copyrighted textbook text."""
    lang = request.GET.get('language', None)
    items = CurriculumPassage.objects.filter(language=lang) if lang else CurriculumPassage.objects.all()
    data = [
        {
            'id': item.id,
            'chapter': item.chapter,
            'topic': item.topic,
            'language': item.language,
            'content': item.content,
            'source_ref': item.source_ref,
        }
        for item in items.order_by('id')[:MAX_PASSAGES]
    ]
    return Response({'count': len(data), 'passages': data})
