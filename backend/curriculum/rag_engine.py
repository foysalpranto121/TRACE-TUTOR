import re
import logging
from pathlib import Path

from django.conf import settings

from trace_backend import gemini, llm
from .models import CurriculumPassage

from django.conf import settings
from trace_backend.cache import cache_key, tiered_get_or_set

logger = logging.getLogger(__name__)

CHROMA_DIR = Path(settings.BASE_DIR) / 'chroma_store'
COLLECTION_NAME = 'nctb_passages'

_TOKEN_RE = re.compile(r'[\wঀ-৿]+', re.UNICODE)


def tokenize(text):
    return [t.lower() for t in _TOKEN_RE.findall(text or '') if len(t) > 1]


class RAGEngine:
    def __init__(self):
        self._collection = None
        self.last_backend = 'none'
        self.default_passages = [
            {
                "id": "seed_bn_01",
                "chapter": "অধ্যায় ৫: প্রোগ্রামিং ভাষা",
                "topic": "লুপ এবং পুনরাবৃত্তি",
                "language": "bn",
                "passage": "C প্রোগ্রামিংয়ে কোনো নির্দিষ্ট স্টেটমেন্টগুচ্ছ নির্দিষ্ট সংখ্যকবার বা শর্ত সত্য থাকা পর্যন্ত বারবার কার্যকর করার জন্য লুপ কন্ট্রোল স্টেটমেন্ট (for, while, do-while) ব্যবহৃত হয়।",
                "source_ref": "Seed passage (index not built yet)",
            },
            {
                "id": "seed_en_01",
                "chapter": "Chapter 5: Programming Language",
                "topic": "Loop Control Structures",
                "language": "en",
                "passage": "Loop control structures allow repeated execution of statements until a given condition becomes false. The for loop consists of initialization, condition checking, and counter update.",
                "source_ref": "Seed passage (index not built yet)",
            },
        ]

    # ---- vector store -------------------------------------------------
    def collection(self):
        if self._collection is None:
            import chromadb
            CHROMA_DIR.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME, metadata={'hnsw:space': 'cosine'}
            )
        return self._collection

    def vector_count(self):
        try:
            return self.collection().count()
        except Exception as e:
            logger.warning(f'Chroma unavailable: {e}')
            return 0

    def existing_ids(self, ids):
        if not ids:
            return set()
        try:
            return set(self.collection().get(ids=list(ids), include=[])['ids'])
        except Exception as e:
            # Returning "nothing is indexed" makes the caller re-embed everything, which is the
            # expensive path. Make sure that at least shows up in the log.
            logger.warning(f'Chroma lookup of {len(ids)} ids failed, treating them as not indexed: {e}')
            return set()

    def delete_ids(self, ids):
        """Remove chunks from the vector store. Returns how many were requested, 0 on failure."""
        ids = list(ids)
        if not ids:
            return 0
        try:
            self.collection().delete(ids=ids)
            return len(ids)
        except Exception as e:
            logger.warning(f'Chroma delete of {len(ids)} ids failed: {e}')
            return 0

    def index_passages(self, items):
        """items: list of {id, text, metadata}. Embeds with Gemini and upserts into Chroma."""
        if not items:
            return 0
        vectors = gemini.embed_texts([it['text'] for it in items], task_type='RETRIEVAL_DOCUMENT')
        self.collection().upsert(
            ids=[it['id'] for it in items],
            embeddings=vectors,
            documents=[it['text'] for it in items],
            metadatas=[it['metadata'] for it in items],
        )
        return len(items)

    def update_metadata(self, items):
        """Refresh the metadata of chunks that are already indexed, leaving their vectors alone.

        Chroma's update accepts metadata without embeddings, so correcting a label costs no API
        call - which is what makes it safe to repair the index on a resumed run.
        """
        if not items:
            return 0
        try:
            self.collection().update(
                ids=[it['id'] for it in items],
                metadatas=[it['metadata'] for it in items],
            )
            return len(items)
        except Exception as e:
            logger.warning(f'Metadata refresh failed for {len(items)} chunks: {e}')
            return 0

    def clear_index(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self._collection = None

    # ---- retrieval ----------------------------------------------------
    def retrieve(self, query, k=5, language=None):
        query = (query or '').strip()
        if not query:
            return []
        results = []
        if self.vector_count() > 0:
            try:
                results = self._vector_retrieve(query, k, language)
                self.last_backend = 'vector'
            except Exception as e:
                logger.warning(f'Vector retrieval failed, using keyword fallback: {e}')
        if not results:
            results = self._keyword_retrieve(query, k, language)
            self.last_backend = 'keyword'
        return results

    def _query_embedding(self, query):
        """Embedding a query is a Gemini call; the vector for a given text never changes, so it is kept in
        the persistent cache (memory in front). Retrieval itself still runs against the live index."""
        key = cache_key('query-embedding', 'v1', gemini.embed_model_name(), getattr(gemini, 'EMBED_DIMENSIONS', None), query)
        vec, _tier = tiered_get_or_set(
            key,
            lambda: [float(x) for x in gemini.embed_texts([query], task_type='RETRIEVAL_QUERY')[0]],
            settings.QUERY_EMBEDDING_CACHE_SECONDS,
            memory_timeout=3600,
        )
        return vec

    def _vector_retrieve(self, query, k, language):
        qvec = self._query_embedding(query)
        kwargs = {
            'query_embeddings': [qvec],
            'n_results': min(k, max(1, self.vector_count())),
            'include': ['documents', 'metadatas', 'distances'],
        }
        if language:
            kwargs['where'] = {'language': language}
        res = self.collection().query(**kwargs)
        out = []
        for doc, meta, dist in zip(res['documents'][0], res['metadatas'][0], res['distances'][0]):
            out.append(self._shape(
                id=res['ids'][0][len(out)],
                passage=doc,
                meta=meta,
                similarity=max(0.0, min(1.0, 1.0 - float(dist))),
            ))
        return out

    def _keyword_retrieve(self, query, k, language):
        q_tokens = set(tokenize(query))
        candidates = []
        try:
            qs = CurriculumPassage.objects.all()
            if language:
                qs = qs.filter(language=language)
            for p in qs.iterator():
                candidates.append({
                    'id': p.chroma_id or str(p.id),
                    'passage': p.content,
                    'meta': {
                        'chapter': p.chapter, 'topic': p.topic, 'language': p.language,
                        'source_ref': p.source_ref, 'doc': '', 'page': 0,
                    },
                })
        except Exception as e:
            logger.warning(f'DB passage lookup failed: {e}')
        if not candidates:
            for p in self.default_passages:
                if language and p['language'] != language:
                    continue
                candidates.append({'id': p['id'], 'passage': p['passage'], 'meta': {
                    'chapter': p['chapter'], 'topic': p['topic'], 'language': p['language'],
                    'source_ref': p['source_ref'], 'doc': 'seed', 'page': 0}})
        scored = []
        for c in candidates:
            c_tokens = set(tokenize(c['passage']))
            overlap = len(q_tokens & c_tokens)
            if overlap == 0 and q_tokens:
                continue
            score = overlap / (len(q_tokens) or 1)
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored and candidates:
            scored = [(0.0, c) for c in candidates[:k]]
        return [self._shape(c['id'], c['passage'], c['meta'], min(0.95, 0.35 + s * 0.6)) for s, c in scored[:k]]

    @staticmethod
    def _shape(id, passage, meta, similarity):
        meta = meta or {}
        return {
            'id': id,
            'chapter': meta.get('chapter', ''),
            'topic': meta.get('topic', ''),
            'language': meta.get('language', ''),
            'doc': meta.get('doc', ''),
            'page': meta.get('page', 0),
            'passage': passage,
            'source_ref': meta.get('source_ref', ''),
            'similarity_score': round(float(similarity), 3),
        }

    # ---- compatibility API used by views ------------------------------
    def search_passages(self, query, language=None, k=8):
        return self.retrieve(query, k=k, language=language)

    def get_grounded_passage(self, query, language=None):
        top = self.retrieve(query, k=1, language=language)
        if not top:
            return ''
        return f"{top[0]['passage']} [Source: {top[0]['source_ref']}]"

    def status(self):
        try:
            db_count = CurriculumPassage.objects.count()
        except Exception:
            db_count = 0
        return {
            'vector_count': self.vector_count(),
            'db_passage_count': db_count,
            'embedding_model': gemini.embed_model_name(),
            'llm_provider': llm.provider(),
            'llm_model': llm.model_name(),
            'llm_configured': llm.configured(),
            'gemini_configured': gemini.api_key() is not None,
            'last_retrieval_backend': self.last_backend,
        }


rag_engine_instance = RAGEngine()
