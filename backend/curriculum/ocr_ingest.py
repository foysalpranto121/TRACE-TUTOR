"""Gemini-vision OCR of the scanned NCTB PDFs in RAG/, cached page-by-page, then chunked and indexed."""
import io
import json
import re
import time
import logging
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db import close_old_connections

from trace_backend import gemini
from .models import CurriculumPassage
from .rag_engine import rag_engine_instance

logger = logging.getLogger(__name__)

RAG_DIR = Path(settings.BASE_DIR).parent / 'RAG'
OCR_DIR = Path(settings.BASE_DIR) / 'data' / 'ocr'
PAGES_PER_CALL = 8

DOCS = {
    'HSC ICT (BV).pdf': {'language': 'bn', 'doc': 'NCTB HSC ICT Textbook (Bangla Version)', 'short': 'NCTB HSC ICT (BV)'},
    'HSC ICT (EV).pdf': {'language': 'en', 'doc': 'NCTB HSC ICT Textbook (English Version)', 'short': 'NCTB HSC ICT (EV)'},
    'HSC ICT QB 26.pdf': {'language': 'bn', 'doc': 'HSC ICT Board Question Bank 2026', 'short': 'HSC ICT QB 2026'},
}

CHAPTERS = [
    ('Chapter 1: ICT - World & Bangladesh Perspective', ['বিশ্ব ও বাংলাদেশ প্রেক্ষিত', 'world and bangladesh perspective']),
    ('Chapter 2: Communication Systems & Networking', ['কমিউনিকেশন সিস্টেমস ও নেটওয়ার্কিং', 'communication systems and networking']),
    ('Chapter 3: Number Systems & Digital Devices', ['সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস', 'number systems and digital devices']),
    ('Chapter 4: Web Design & HTML', ['ওয়েব ডিজাইন পরিচিতি এবং html', 'ওয়েব ডিজাইন পরিচিতি', 'introduction to web design and html', 'web design and html']),
    ('Chapter 5: Programming Language (C)', ['প্রোগ্রামিং ভাষা', 'programming language']),
    ('Chapter 6: Database Management System', ['ডেটাবেজ ম্যানেজমেন্ট সিস্টেম', 'ডাটাবেজ ম্যানেজমেন্ট সিস্টেম', 'database management system']),
]

INGEST_STATE = {
    'running': False, 'stage': 'idle', 'current_doc': '', 'done_pages': 0, 'total_pages': 0,
    'indexed_chunks': 0, 'error': None, 'warnings': [], 'started_at': None, 'finished_at': None, 'log': [],
}
_state_lock = threading.Lock()


def _log(msg):
    logger.info(msg)
    with _state_lock:
        INGEST_STATE['log'] = (INGEST_STATE['log'] + [f'{time.strftime("%H:%M:%S")} {msg}'])[-40:]


def _set(**kw):
    with _state_lock:
        INGEST_STATE.update(kw)


# ---------------------------------------------------------------- OCR cache
def cache_path(pdf_name):
    return OCR_DIR / (Path(pdf_name).stem + '.jsonl')


def load_cache(pdf_name):
    path = cache_path(pdf_name)
    pages = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            pages[int(rec['page'])] = rec['text']
    return pages


def _append_cache(pdf_name, records, lock):
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    with lock:
        with open(cache_path(pdf_name), 'a', encoding='utf-8') as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + '\n')


# ---------------------------------------------------------------- OCR calls
_PAGE_RE = re.compile(r'^\s*=+\s*PAGE\s+(\d+)\s*=+\s*$', re.M)


def _parse_pages(text, page_numbers):
    parts = _PAGE_RE.split(text)
    # parts: [preamble, num, body, num, body, ...]
    found = {}
    for i in range(1, len(parts) - 1, 2):
        try:
            found[int(parts[i])] = parts[i + 1].strip()
        except ValueError:
            continue
    if found and all(p in found for p in page_numbers):
        return {p: found[p] for p in page_numbers}
    # Labels missing or mismatched: assign bodies sequentially.
    bodies = [parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)] or [text.strip()]
    out = {}
    for p, body in zip(page_numbers, bodies):
        out[p] = body
    for p in page_numbers:
        out.setdefault(p, '')
    return out


def _transcribe_batch(client, pdf_path, page_numbers, doc_language):
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    for p in page_numbers:
        writer.add_page(reader.pages[p - 1])
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)

    uploaded = client.files.upload(file=buf, config={'mime_type': 'application/pdf', 'display_name': f'{pdf_path.stem}_{page_numbers[0]}'})
    try:
        while uploaded.state.name == 'PROCESSING':
            time.sleep(1.5)
            uploaded = client.files.get(name=uploaded.name)
        lang_hint = 'Bangla (with English technical terms and code)' if doc_language == 'bn' else 'English'
        prompt = (
            f'This PDF contains {len(page_numbers)} scanned textbook pages, in order. '
            f'Transcribe EVERY page verbatim in {lang_hint}, exactly as printed: headings, paragraphs, bullet lists, '
            'tables (as plain text rows), and all program code / HTML exactly. Do not summarize, translate, or add commentary. '
            'Skip page headers/footers, watermarks and website URLs. '
            f'Label the pages sequentially as "=== PAGE {page_numbers[0]} ===" through "=== PAGE {page_numbers[-1]} ===" '
            '(one label line before each page, in the given order, ignoring any printed page numbers). Output plain text only.'
        )
        try:
            resp, model = gemini.generate_content([uploaded, prompt], {'temperature': 0.0})
        except Exception as e:
            raise RuntimeError(f'OCR failed for pages {page_numbers[0]}-{page_numbers[-1]}: {e}')
        return _parse_pages(resp.text or '', page_numbers)
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass


def ocr_pdf(pdf_name, page_range=None, workers=3):
    """OCR the pages of one PDF that are not cached yet. Returns dict page->text for the whole cache."""
    from pypdf import PdfReader
    pdf_path = RAG_DIR / pdf_name
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    client = gemini.get_client()
    if client is None:
        raise RuntimeError('GEMINI_API_KEY is not configured; OCR ingestion needs Gemini.')

    total = len(PdfReader(str(pdf_path)).pages)
    lo, hi = (1, total) if not page_range else (max(1, page_range[0]), min(total, page_range[1]))
    cached = load_cache(pdf_name)
    todo = [p for p in range(lo, hi + 1) if p not in cached]
    _set(current_doc=pdf_name, total_pages=hi - lo + 1, done_pages=(hi - lo + 1) - len(todo))
    _log(f'{pdf_name}: {total} pages, {len(cached)} cached, {len(todo)} to OCR')
    if not todo:
        return cached

    batches = [todo[i:i + PAGES_PER_CALL] for i in range(0, len(todo), PAGES_PER_CALL)]
    lang = DOCS.get(pdf_name, {}).get('language', 'bn')
    lock = threading.Lock()

    def work(batch):
        pages = _transcribe_batch(client, pdf_path, batch, lang)
        _append_cache(pdf_name, [{'page': p, 'text': pages[p]} for p in batch], lock)
        return batch

    failed, consecutive_failures = [], 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, b): b for b in batches}
        for fut in as_completed(futures):
            batch = futures[fut]
            try:
                fut.result()
            except Exception as e:
                failed.append(batch)
                consecutive_failures += 1
                _log(f'{pdf_name}: OCR pages {batch[0]}-{batch[-1]} FAILED: {str(e)[:160]}')
                if consecutive_failures >= 3:
                    _log(f'{pdf_name}: 3 consecutive OCR failures (quota or network) - pausing OCR for this document; cached pages will still be indexed. Re-run ingestion later to resume.')
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                continue
            consecutive_failures = 0
            with _state_lock:
                INGEST_STATE['done_pages'] += len(batch)
            _log(f'{pdf_name}: OCR pages {batch[0]}-{batch[-1]} done ({INGEST_STATE["done_pages"]}/{INGEST_STATE["total_pages"]})')
    if failed:
        with _state_lock:
            INGEST_STATE['warnings'].append(f'{pdf_name}: {sum(len(b) for b in failed)} page(s) not OCRed yet')
    return load_cache(pdf_name)


# ---------------------------------------------------------------- chunk + index
def detect_chapter(page_text, previous):
    head = '\n'.join(page_text.splitlines()[:4]).lower()
    for name, keys in CHAPTERS:
        if any(k in head for k in keys):
            return name
    return previous


def chunk_page(text, max_words=170, overlap_words=25):
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    chunks, current = [], []
    count = 0
    for para in paragraphs:
        words = para.split()
        if count + len(words) > max_words and current:
            chunks.append('\n\n'.join(current))
            tail = ' '.join('\n\n'.join(current).split()[-overlap_words:])
            current, count = ([tail] if tail else []), len(tail.split())
        current.append(para)
        count += len(words)
    if current:
        chunks.append('\n\n'.join(current))
    return [c for c in chunks if len(c.split()) >= 8]


def index_pdf_cache(pdf_name, page_range=None, reindex=False):
    info = DOCS.get(pdf_name, {'language': 'bn', 'doc': Path(pdf_name).stem, 'short': Path(pdf_name).stem})
    pages = load_cache(pdf_name)
    if not pages:
        return 0
    stem = Path(pdf_name).stem.replace(' ', '_')
    chapter = 'NCTB HSC ICT'
    pending, indexed, skipped = [], 0, 0

    def flush():
        nonlocal pending, indexed, skipped
        if not pending:
            return True
        if not reindex:
            already = rag_engine_instance.existing_ids([it['id'] for it in pending])
            skipped += len(already)
            pending = [it for it in pending if it['id'] not in already]
        try:
            indexed += rag_engine_instance.index_passages(pending)
        except Exception as e:
            _log(f'{pdf_name}: embedding failed ({str(e)[:140]}) - stopping indexing of this document; re-run later to resume')
            with _state_lock:
                INGEST_STATE['warnings'].append(f'{pdf_name}: indexing incomplete (embedding quota/network)')
            pending = []
            return False
        with _state_lock:
            INGEST_STATE['indexed_chunks'] += len(pending)
        pending = []
        return True

    for page in sorted(pages):
        if page_range and not (page_range[0] <= page <= page_range[1]):
            continue
        text = pages[page]
        chapter = detect_chapter(text, chapter)
        for idx, chunk in enumerate(chunk_page(text)):
            chroma_id = f'{stem}_p{page}_c{idx + 1}'
            source_ref = f'{info["short"]} p.{page}'
            obj, created = CurriculumPassage.objects.update_or_create(
                chroma_id=chroma_id,
                defaults={
                    'chapter': chapter,
                    'topic': f'{info["short"]} page {page}',
                    'language': info['language'],
                    'content': chunk,
                    'source_ref': source_ref,
                },
            )
            pending.append({'id': chroma_id, 'text': chunk, 'metadata': {
                'chapter': chapter, 'topic': obj.topic, 'language': info['language'],
                'source_ref': source_ref, 'doc': info['doc'], 'page': page,
            }})
            if len(pending) >= 32 and not flush():
                return indexed
    flush()
    _log(f'{pdf_name}: indexed {indexed} new chunks ({skipped} already indexed)')
    return indexed


def run_ingest(pdf_names=None, page_range=None, workers=3, ocr=True, reindex=False):
    pdf_names = pdf_names or [n for n in DOCS if (RAG_DIR / n).exists()]
    _set(running=True, stage='starting', error=None, warnings=[], started_at=time.time(), finished_at=None, indexed_chunks=0, done_pages=0, total_pages=0)
    total = 0
    try:
        if reindex:
            rag_engine_instance.clear_index()
            _log('Cleared existing vector index')
        for name in pdf_names:
            if ocr:
                _set(stage=f'ocr:{name}')
                ocr_pdf(name, page_range=page_range, workers=workers)
            _set(stage=f'index:{name}')
            total += index_pdf_cache(name, page_range=page_range, reindex=reindex)
        _set(stage='done')
        _log(f'Ingestion complete. Vector count now {rag_engine_instance.vector_count()}')
    except Exception as e:
        logger.exception('Ingestion failed')
        _set(stage='error', error=str(e))
        _log(f'ERROR: {e}')
        raise
    finally:
        _set(running=False, finished_at=time.time())
        close_old_connections()
    return total


def start_background_ingest(**kwargs):
    with _state_lock:
        if INGEST_STATE['running']:
            return False
        INGEST_STATE['running'] = True

    def target():
        try:
            run_ingest(**kwargs)
        except Exception:
            pass

    threading.Thread(target=target, daemon=True, name='rag-ingest').start()
    return True
