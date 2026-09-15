import re

from django.conf import settings
from django.core.cache import caches
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsResearcher, IsStaffRole
from trace_backend.throttles import IngestThrottle

from .rag_engine import rag_engine_instance
from .ocr_ingest import INGEST_STATE, start_background_ingest, DOCS, RAG_DIR, load_cache
from .models import CurriculumPassage

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
        })
    return {'engine': rag_engine_instance.status(), 'ingest': dict(INGEST_STATE), 'documents': docs}


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
