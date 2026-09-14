from django.conf import settings
from django.core.cache import caches
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .rag_engine import rag_engine_instance
from .ocr_ingest import INGEST_STATE, start_background_ingest, DOCS, RAG_DIR, load_cache
from .models import CurriculumPassage


@api_view(['POST'])
@permission_classes([AllowAny])
def search_curriculum(request):
    query = request.data.get('query', '')
    language = request.data.get('language', None)
    k = int(request.data.get('k', 8))

    results = rag_engine_instance.search_passages(query, language=language, k=k)
    return Response({
        'query': query,
        'results_count': len(results),
        'retrieval_backend': rag_engine_instance.last_backend,
        'passages': results,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def ingest_curriculum(request):
    pdfs = request.data.get('pdfs') or None
    page_range = request.data.get('pages') or None
    if page_range:
        lo, hi = str(page_range).split('-')
        page_range = (int(lo), int(hi))
    started = start_background_ingest(
        pdf_names=pdfs, page_range=page_range,
        workers=int(request.data.get('workers', 3)),
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
@permission_classes([AllowAny])
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
@permission_classes([AllowAny])
def get_passages(request):
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
        for item in items[:500]
    ]
    return Response({'count': len(data), 'passages': data})
