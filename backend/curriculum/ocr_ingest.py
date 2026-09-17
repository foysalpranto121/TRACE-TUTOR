"""Gemini-vision OCR of the scanned NCTB PDFs in RAG/, cached page-by-page, then chunked and indexed."""
import io
import json
import re
import time
import logging
import threading
import unicodedata
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from trace_backend import gemini
from .models import CurriculumPassage, IngestRun, OcrPage
from .rag_engine import rag_engine_instance

logger = logging.getLogger(__name__)

RAG_DIR = Path(settings.BASE_DIR).parent / 'RAG'
OCR_DIR = Path(settings.BASE_DIR) / 'data' / 'ocr'
PAGES_PER_CALL = 8

# A page transcribed to less than this is treated as an OCR miss rather than a short page, and
# `--retry-empty` sends it back to the model. MAX_OCR_ATTEMPTS stops a genuinely blank page
# (a divider, a full-page figure) from being re-requested on every run for ever.
MIN_PAGE_CHARS = 200
MAX_OCR_ATTEMPTS = 2

# 'chaptered': the document is a textbook whose pages run through the six chapters in order, so a
#   chapter extends from its opening page to the next opener. A question bank is not: its pages are
#   labelled only by what they themselves say, never by carry-over.
# 'printed_page_offset': PDF page index minus the number printed on the page. Citations shown to
#   students are built from the PDF index; set this once the offset has been read off the physical
#   book (open the PDF at the first chapter's opening page and compare), so a student can find the
#   cited page. 0 means "cite the PDF index" and is the safe default until checked.
DOCS = {
    'HSC ICT (BV).pdf': {'language': 'bn', 'doc': 'NCTB HSC ICT Textbook (Bangla Version)', 'short': 'NCTB HSC ICT (BV)',
                         'chaptered': True, 'printed_page_offset': 0},
    'HSC ICT (EV).pdf': {'language': 'en', 'doc': 'NCTB HSC ICT Textbook (English Version)', 'short': 'NCTB HSC ICT (EV)',
                         'chaptered': True, 'printed_page_offset': 0},
    'HSC ICT QB 26.pdf': {'language': 'bn', 'doc': 'HSC ICT Board Question Bank 2026', 'short': 'HSC ICT QB 2026',
                          'chaptered': False, 'printed_page_offset': 0},
}
EXPECTED_CHAPTERS = 6
FILES_API_TIMEOUT_SECONDS = 180

DEFAULT_CHAPTER = 'NCTB HSC ICT'

CHAPTER_NAMES = {
    1: 'Chapter 1: ICT - World & Bangladesh Perspective',
    2: 'Chapter 2: Communication Systems & Networking',
    3: 'Chapter 3: Number Systems & Digital Devices',
    4: 'Chapter 4: Web Design & HTML',
    5: 'Chapter 5: Programming Language (C)',
    6: 'Chapter 6: Database Management System',
}

# Fallback only, for a document whose pages carry no "<ordinal> chapter" opener anywhere.
CHAPTER_TITLE_KEYS = {
    1: ['বিশ্ব ও বাংলাদেশ প্রেক্ষিত', 'world and bangladesh perspective'],
    2: ['কমিউনিকেশন সিস্টেমস ও নেটওয়ার্কিং', 'communication systems and networking'],
    3: ['সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস', 'number systems and digital devices'],
    4: ['ওয়েব ডিজাইন পরিচিতি এবং html', 'ওয়েব ডিজাইন পরিচিতি', 'introduction to web design and html', 'web design and html'],
    5: ['প্রোগ্রামিং ভাষা', 'programming language'],
    6: ['ডেটাবেজ ম্যানেজমেন্ট সিস্টেম', 'ডাটাবেজ ম্যানেজমেন্ট সিস্টেম', 'database management system'],
}

_BANGLA_ORDINALS = {'প্রথম': 1, 'দ্বিতীয়': 2, 'তৃতীয়': 3, 'চতুর্থ': 4, 'পঞ্চম': 5, 'ষষ্ঠ': 6}
_ENGLISH_ORDINALS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6}

# A chapter opener is a short heading line, never a sentence. 60 characters comfortably fits
# "চতুর্থ অধ্যায়" and "Fourth Chapter" while excluding the prose that used to match.
HEADING_MAX_CHARS = 60

# Live view of the run in progress, for the status endpoint. It is process memory: a restart
# wipes it and a second worker never sees it. The durable record is the IngestRun row that
# _persist() mirrors it into from the ingest thread.
INGEST_STATE = {
    'running': False, 'stage': 'idle', 'current_doc': '', 'done_pages': 0, 'total_pages': 0,
    'indexed_chunks': 0, 'relabelled_chunks': 0, 'error': None, 'warnings': [], 'started_at': None,
    'finished_at': None, 'log': [], 'run_id': None,
}
_state_lock = threading.Lock()
_CURRENT_RUN = {'run': None, 'log': []}
MAX_PERSISTED_LOG_LINES = 2000


def _log(msg):
    logger.info(msg)
    line = f'{time.strftime("%H:%M:%S")} {msg}'
    with _state_lock:
        INGEST_STATE['log'] = (INGEST_STATE['log'] + [line])[-40:]
        if len(_CURRENT_RUN['log']) < MAX_PERSISTED_LOG_LINES:
            _CURRENT_RUN['log'].append(line)


def _set(**kw):
    with _state_lock:
        INGEST_STATE.update(kw)


def _persist(**fields):
    """Mirror the live state into the current IngestRun row.

    Called only from the thread that owns the run (the one inside run_ingest), never from the
    OCR worker threads, so the row is written by one connection and the workers stay free of
    database access. Worker threads only append to the in-memory log under the lock.
    """
    run = _CURRENT_RUN['run']
    if run is None:
        return
    with _state_lock:
        snap = dict(INGEST_STATE)
        run.log = list(_CURRENT_RUN['log'])
    run.stage = (snap.get('stage') or '')[:80]
    run.done_pages = snap.get('done_pages') or 0
    run.total_pages = snap.get('total_pages') or 0
    run.indexed_chunks = snap.get('indexed_chunks') or 0
    run.relabelled_chunks = snap.get('relabelled_chunks') or 0
    run.warnings = list(snap.get('warnings') or [])
    run.error = snap.get('error') or ''
    for name, value in fields.items():
        setattr(run, name, value)
    try:
        run.save()
    except Exception as e:  # the run itself must not die because its progress row could not be written
        logger.warning(f'IngestRun #{run.pk} progress not saved: {e}')


def _code_commit():
    try:
        from assessment.manifest import _git
        return (_git('rev-parse', 'HEAD') or '')[:40]
    except Exception:
        return ''


# ---------------------------------------------------------------- OCR cache
def cache_path(pdf_name):
    return OCR_DIR / (Path(pdf_name).stem + '.jsonl')


def load_cache_records(pdf_name):
    """page -> its most recent cache record. The cache is append-only, so a page that is
    transcribed again simply appends and the newer record wins."""
    path = cache_path(pdf_name)
    records = {}
    if path.exists():
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                records[int(rec['page'])] = rec
            except (ValueError, KeyError, TypeError) as e:
                # A crash mid-write leaves a torn final line. Losing that one page's transcription
                # is cheap to repair; making every reader of the cache, including the status
                # endpoint, fail is not.
                logger.warning(f'{path.name} line {number}: unreadable cache record skipped ({e})')
    return records


def corpus_version():
    """A token that changes whenever the corpus may have changed: the id of the last completed run.

    Anything derived from retrieval - the tutor answer cache, the research record of a turn - is
    keyed or stamped with it, so an answer can be traced to the corpus state that produced it.
    """
    try:
        run = IngestRun.objects.filter(status='done').order_by('-pk').values_list('pk', flat=True).first()
        return int(run or 0)
    except Exception:
        return 0


def load_cache(pdf_name):
    return {page: rec.get('text') or '' for page, rec in load_cache_records(pdf_name).items()}


def is_thin(text):
    """True when a page transcribed to too little text to be a real page of the book."""
    return len((text or '').strip()) < MIN_PAGE_CHARS


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
    # Labels missing or mismatched: the bodies can still be assigned in order, but only when
    # there are exactly as many as pages. With a page dropped, positional assignment would file
    # one page's text under another page's number and nothing downstream could tell; raising
    # instead hands the batch to the split-retry, which ends at single pages where order is moot.
    bodies = [parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)] or [text.strip()]
    if len(bodies) != len(page_numbers):
        raise ValueError(f'model returned {len(bodies)} page bodies for {len(page_numbers)} requested pages')
    return dict(zip(page_numbers, bodies))


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
        deadline = time.monotonic() + FILES_API_TIMEOUT_SECONDS
        while uploaded.state.name == 'PROCESSING':
            if time.monotonic() > deadline:
                # Without a deadline a stuck upload wedges a worker for ever, the pool never shuts
                # down, and INGEST_STATE['running'] stays true until the process is restarted.
                raise RuntimeError(f'upload of pages {page_numbers[0]}-{page_numbers[-1]} still processing '
                                   f'after {FILES_API_TIMEOUT_SECONDS}s')
            time.sleep(1.5)
            uploaded = client.files.get(name=uploaded.name)
        lang_hint = 'Bangla (with English technical terms and code)' if doc_language == 'bn' else 'English'
        prompt = (
            f'This PDF contains {len(page_numbers)} scanned textbook pages, in order. '
            f'Transcribe EVERY page verbatim in {lang_hint}, exactly as printed: headings, paragraphs, bullet lists, '
            'tables (as plain text rows), and all program code / HTML exactly. Do not summarize, translate, or add commentary. '
            'Skip page headers/footers, watermarks and website URLs. '
            # The labels are enumerated rather than given as a range because a retry batch collects
            # scattered pages, so "PAGE 1 through PAGE 104" would describe 104 pages, not eight.
            'Label each page with its own line, in this exact order: '
            + ', '.join(f'"=== PAGE {p} ==="' for p in page_numbers) + '. '
            'Ignore any page number printed on the page itself. Output plain text only.'
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


def ocr_pdf(pdf_name, page_range=None, workers=3, retry_empty=False):
    """OCR the pages of one PDF that are not cached yet. Returns dict page->text for the whole cache.

    With retry_empty, pages already cached as near-empty are sent back to the model instead of
    counting as done - without it a page the model returned nothing for stays blank for ever.
    """
    from pypdf import PdfReader
    pdf_path = RAG_DIR / pdf_name
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    client = gemini.get_client()
    if client is None:
        raise RuntimeError('GEMINI_API_KEY is not configured; OCR ingestion needs Gemini.')

    total = len(PdfReader(str(pdf_path)).pages)
    lo, hi = (1, total) if not page_range else (max(1, page_range[0]), min(total, page_range[1]))
    records = load_cache_records(pdf_name)
    cached = {p: rec.get('text') or '' for p, rec in records.items()}
    in_scope = range(lo, hi + 1)
    thin = set()
    if retry_empty:
        thin = {p for p, rec in records.items()
                if p in in_scope and is_thin(rec.get('text')) and _attempts_of(rec) < MAX_OCR_ATTEMPTS}
    todo = [p for p in in_scope if p not in cached or p in thin]
    _set(current_doc=pdf_name, total_pages=hi - lo + 1, done_pages=(hi - lo + 1) - len(todo))
    _log(f'{pdf_name}: {total} pages, {len(cached)} cached, {len(todo)} to OCR'
         + (f' ({len(thin)} cached-but-empty being retried)' if thin else ''))
    if not todo:
        return _finish_ocr(pdf_name, in_scope)

    batches = [todo[i:i + PAGES_PER_CALL] for i in range(0, len(todo), PAGES_PER_CALL)]
    lang = DOCS.get(pdf_name, {}).get('language', 'bn')
    lock = threading.Lock()
    lost = []   # single pages that failed even on their own, appended under `lock`

    def work(batch):
        """Transcribe one batch, halving it and retrying if the request is rejected as a whole.

        Some scanned pages are heavy enough that a batch containing them is refused with 503 while
        the same pages succeed one at a time. Splitting recovers them instead of leaving them blank,
        and returns the pages actually transcribed so a partial recovery is not counted as a loss.
        A quota refusal is account-wide, so splitting it would only spend the remaining quota on
        the same refusal fifteen times over; that one propagates straight to the breaker.
        """
        try:
            pages = _transcribe_batch(client, pdf_path, batch, lang)
        except Exception as error:
            if len(batch) == 1:
                with lock:
                    lost.append(batch[0])
                raise
            if _is_quota_error(error):
                raise
            mid = len(batch) // 2
            done, errors = [], []
            for half in (batch[:mid], batch[mid:]):
                try:
                    done.extend(work(half))
                except Exception as sub_error:
                    errors.append(sub_error)
            if not done:
                raise errors[0]
            if errors:
                _log(f'{pdf_name}: pages {batch[0]}-{batch[-1]} partly recovered by splitting ({len(done)}/{len(batch)})')
            return done
        out = []
        for p in batch:
            previous = records.get(p)
            text = pages[p]
            if previous is not None and len(text.strip()) < len((previous.get('text') or '').strip()):
                # A retry that comes back with less than the cache already holds keeps the
                # better transcription; only the attempt count moves on.
                text = previous.get('text') or ''
            out.append({'page': p, 'text': text, 'attempt': (_attempts_of(previous) + 1) if previous else 1})
        _append_cache(pdf_name, out, lock)
        return batch

    failed, consecutive_failures = [], 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, b): b for b in batches}
        for fut in as_completed(futures):
            batch = futures[fut]
            try:
                done_pages = fut.result()
            except Exception as e:
                failed.append(batch)
                consecutive_failures += 1
                _log(f'{pdf_name}: OCR pages {batch[0]}-{batch[-1]} FAILED: {str(e)[:160]}')
                _persist()
                if consecutive_failures >= 3 or _is_quota_error(e):
                    reason = 'quota exhausted' if _is_quota_error(e) else '3 consecutive OCR failures (network)'
                    _log(f'{pdf_name}: {reason} - pausing OCR for this document; cached pages will still be indexed. Re-run ingestion later to resume.')
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                continue
            consecutive_failures = 0
            with _state_lock:
                INGEST_STATE['done_pages'] += len(done_pages)
            _log(f'{pdf_name}: OCR pages {batch[0]}-{batch[-1]} done ({INGEST_STATE["done_pages"]}/{INGEST_STATE["total_pages"]})')
            _persist()
    # Everything asked for that is still not in the cache: whole failed batches, pages lost inside
    # a split, and batches the breaker cancelled before they ran.
    now_cached = load_cache_records(pdf_name)
    missing = sorted(p for p in todo if p not in now_cached or (p in thin and _attempts_of(now_cached[p]) == _attempts_of(records.get(p))))
    if missing:
        with _state_lock:
            INGEST_STATE['warnings'].append(f'{pdf_name}: {len(missing)} page(s) not OCRed yet: {missing[:12]}')
    return _finish_ocr(pdf_name, in_scope)


def _attempts_of(rec):
    """How many times a cached page has been sent to the model. A record written before attempts
    were tracked is one transcription, not zero: the read and write sides must agree on that, or
    every legacy page gets an extra paid retry."""
    if not rec:
        return 0
    return int(rec.get('attempt') or 1)


def _is_quota_error(error):
    text = str(error)
    return '429' in text or 'RESOURCE_EXHAUSTED' in text or 'quota' in text.lower()


def _finish_ocr(pdf_name, in_scope):
    """Common tail of ocr_pdf: report blank pages in scope, mirror page rows, return the cache."""
    final = load_cache(pdf_name)
    records = load_cache_records(pdf_name)
    still_thin = sorted(p for p in in_scope if p in final and is_thin(final[p]))
    if still_thin:
        exhausted = [p for p in still_thin if _attempts_of(records.get(p)) >= MAX_OCR_ATTEMPTS]
        retryable = [p for p in still_thin if p not in exhausted]
        msg = (f'{pdf_name}: {len(still_thin)} page(s) transcribed to almost nothing: {still_thin[:12]}'
               + (f'; {len(retryable)} retryable with --retry-empty' if retryable else '')
               + (f'; {len(exhausted)} given up after {MAX_OCR_ATTEMPTS} attempts' if exhausted else ''))
        _log(msg)
        with _state_lock:
            INGEST_STATE['warnings'].append(msg)
    sync_pages(pdf_name)
    _persist()
    return final


# ---------------------------------------------------------------- chapter structure
def _norm(text):
    """NFC, lowercased, with markdown decoration stripped.

    The model returns Bangla in whichever normalisation it likes: 'য়' arrives both precomposed
    (U+09DF) and decomposed (U+09AF U+09BC), and it sometimes wraps a heading in asterisks. Raw
    string comparison therefore misses real headings, which is how chapters 4-6 lost their labels.
    """
    text = unicodedata.normalize('NFC', text or '').lower()
    return re.sub(r'[*_#`>|]+', ' ', text)


_ENGLISH_NUMBER_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}


def _build_openers():
    pats = []
    for word, num in _BANGLA_ORDINALS.items():
        pats.append((num, re.compile(_norm(word) + r'\s+' + _norm('অধ্যায়'))))
    for word, num in _ENGLISH_ORDINALS.items():
        pats.append((num, re.compile(r'\b' + word + r'\s+chapter\b')))        # "Fourth Chapter"
    for word, num in _ENGLISH_NUMBER_WORDS.items():
        pats.append((num, re.compile(r'\bchapter\s+' + word + r'\b')))        # "Chapter Four"
    for num in CHAPTER_NAMES:
        pats.append((num, re.compile(r'\bchapter\s*[-:–]?\s*0?' + str(num) + r'\b')))  # "Chapter 4"
    return pats


_CHAPTER_OPENERS = _build_openers()


def _heading_lines(page_text, limit=6):
    for raw in (page_text or '').splitlines()[:limit]:
        line = _norm(raw).strip()
        if line and len(line) <= HEADING_MAX_CHARS:
            yield line


def _openers_on(page_text, limit=6):
    """Every distinct chapter number named on a short heading line within the first `limit` lines."""
    found = []
    for line in _heading_lines(page_text, limit=limit):
        for num, pattern in _CHAPTER_OPENERS:
            if pattern.search(line) and num not in found:
                found.append(num)
    return found


CONTENTS_PAGE_WINDOW = 30
_SECTION_NUMBER_RE = re.compile(r'^[0-9০-৯]+(?:[.][0-9০-৯]+)*[.)]?\s*')


def chapter_start(page_text):
    """The chapter number this page opens, or None.

    Only a short heading line counts. Page 122 of the Bangla book calls Javascript "the most
    popular programming language" in the middle of a paragraph; that must not open Chapter 5.
    A page that names several chapters on short lines near its top is a table of contents, and
    taking it as an opener would file the real opening page a few pages later as a repeat.
    """
    found = _openers_on(page_text)
    if len(found) != 1:
        return None
    if len(_openers_on(page_text, limit=CONTENTS_PAGE_WINDOW)) > 1:
        return None
    return found[0]


def chapter_by_title(page_text):
    """The chapter whose printed title heads this page, or None.

    The title must BE the heading line, or begin it: a title that merely appears inside a short
    line (a bullet, a caption, an exercise) is the kind of match that used to relabel chapters.
    """
    for line in _heading_lines(page_text, limit=5):
        # "৫.১ প্রোগ্রামিং ভাষা" is a section heading that names its chapter; drop the number.
        bare = _SECTION_NUMBER_RE.sub('', line).strip(' :-.,()[]"\'')
        for num, keys in CHAPTER_TITLE_KEYS.items():
            for key in keys:
                k = _norm(key).strip()
                if bare == k or bare.startswith(k + ' ') or bare.startswith(k + ':'):
                    return num
    return None


_BANGLA_DIGITS = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
_SECTION_HEADING_RE = re.compile(r'^([1-6])\.(\d{1,2})(?:\.\d{1,2})*[.)]?\s+\S')


def chapter_by_section_number(page_text):
    """The chapter a page's section headings belong to, or None.

    "৫.১ প্রোগ্রামিং ভাষার ধারণা" is a heading of section 1 of chapter 5. The leading digit is the
    only mark of the chapter that repeats on every page of it, which makes it the signal that can
    rescue a chapter whose opening page came back blank from the model.
    """
    for line in _heading_lines(page_text, limit=8):
        match = _SECTION_HEADING_RE.match(line.translate(_BANGLA_DIGITS))
        if match:
            return int(match.group(1))
    return None


def _place_consistently(starts, page, num):
    """Whether (page, num) can be added to the ordered chapter starts without breaking monotonic order."""
    before = [n for pg, n in starts if pg < page]
    after = [n for pg, n in starts if pg > page]
    if before and max(before) >= num:
        return False
    if after and min(after) <= num:
        return False
    return True


def chapter_spans(pages, chaptered=True):
    """Map every cached page number to its chapter name, resolved over the document as a whole.

    A chapter runs from the page that opens it to the page before the next one opens, so a page is
    labelled by the structure of the book rather than by whatever the preceding page happened to
    mention. Chapter numbers only move forward: a cross-reference cannot reopen a chapter that has
    already been seen, and cannot wind the book back to an earlier one.

    Openers are authoritative. A chapter with no opener - its opening page came back blank from
    the model - is rescued from its section numbering ("৫.১ ...") or its printed title, but only
    where that evidence sits consistently between the openers already placed, so a fallback can
    never contradict the book's own structure.

    A document that is not chaptered (a question bank) gets no carry-over at all: each page is
    labelled by what it itself says, or not at all.
    """
    ordered = sorted(p for p in pages if isinstance(p, int))
    if not chaptered:
        return {p: CHAPTER_NAMES[n] if (n := chapter_start(pages[p]) or chapter_by_section_number(pages[p])
                                        or chapter_by_title(pages[p])) else DEFAULT_CHAPTER
                for p in ordered}
    starts, seen = [], set()
    for finder in (chapter_start, chapter_by_section_number, chapter_by_title):
        for p in ordered:
            num = finder(pages[p])
            if num is None or num in seen or not _place_consistently(starts, p, num):
                continue
            starts.append((p, num))
            seen.add(num)
            starts.sort()
    starts.sort()
    spans, idx, current = {}, 0, DEFAULT_CHAPTER
    for p in ordered:
        while idx < len(starts) and starts[idx][0] <= p:
            current = CHAPTER_NAMES[starts[idx][1]]
            idx += 1
        spans[p] = current
    return spans


def chapters_resolved(spans):
    """The chapter numbers a span map actually assigned, for reporting what a document is missing."""
    names = set(spans.values())
    return sorted(num for num, name in CHAPTER_NAMES.items() if name in names)


def detect_chapter(page_text, previous):
    """Single-page fallback kept for callers that have no whole-document view."""
    num = chapter_start(page_text) or chapter_by_title(page_text)
    return CHAPTER_NAMES[num] if num else previous


# ---------------------------------------------------------------- page status rows
def _doc_info(pdf_name):
    info = dict(DOCS.get(pdf_name) or {'language': 'bn', 'doc': Path(pdf_name).stem, 'short': Path(pdf_name).stem})
    info.setdefault('chaptered', True)
    info.setdefault('printed_page_offset', 0)
    return info


def _chunk_page_number(chroma_id, prefix):
    match = re.match(re.escape(prefix) + r'(\d+)_c\d+$', chroma_id or '')
    return int(match.group(1)) if match else None


def sync_pages(pdf_name):
    """Mirror one document's page cache and its presence in the vector index into OcrPage rows.

    Idempotent and cheap (one query per document, one bulk write), so it runs after every OCR
    and indexing stage and can be re-run at any time to backfill. 'indexed_chunks' is counted from
    what the vector store actually holds, not from the relational rows, because a passage row is
    written before its embedding succeeds and the two can legitimately differ after a quota abort.
    """
    records = load_cache_records(pdf_name)
    if not records:
        return 0
    pages = {p: r.get('text') or '' for p, r in records.items()}
    chapters = chapter_spans(pages, chaptered=_doc_info(pdf_name)['chaptered'])
    prefix = f'{Path(pdf_name).stem.replace(" ", "_")}_p'
    candidate_ids = list(CurriculumPassage.objects.filter(chroma_id__startswith=prefix)
                         .values_list('chroma_id', flat=True))
    in_index = rag_engine_instance.existing_ids(candidate_ids) if candidate_ids else set()
    per_page = Counter(n for n in (_chunk_page_number(cid, prefix) for cid in in_index) if n is not None)

    now = timezone.now()
    run = _CURRENT_RUN['run']
    existing = {row.page: row for row in OcrPage.objects.filter(document=pdf_name)}
    to_create, to_update = [], []
    for page, rec in records.items():
        text = rec.get('text') or ''
        row = existing.get(page)
        fresh = row is None
        if fresh:
            row = OcrPage(document=pdf_name, page=page)
        attempts = _attempts_of(rec)
        indexed = per_page.get(page, 0)
        changed = fresh or attempts != row.attempts or indexed != row.indexed_chunks
        if fresh or attempts != row.attempts:
            row.transcribed_at = now
        if indexed != row.indexed_chunks:
            row.indexed_at = now if indexed else None
        row.chars = len(text.strip())
        row.thin = is_thin(text)
        row.attempts = attempts
        row.chapter = chapters.get(page, DEFAULT_CHAPTER)
        row.indexed_chunks = indexed
        if changed and run is not None:
            row.last_run = run
        (to_create if fresh else to_update).append(row)
    if to_create:
        OcrPage.objects.bulk_create(to_create)
    if to_update:
        OcrPage.objects.bulk_update(
            to_update,
            ['chars', 'thin', 'attempts', 'chapter', 'indexed_chunks', 'transcribed_at', 'indexed_at', 'last_run'],
        )
    return len(to_create) + len(to_update)


# ---------------------------------------------------------------- chunk + index


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
    info = _doc_info(pdf_name)
    pages = load_cache(pdf_name)
    if not pages:
        return 0
    stem = Path(pdf_name).stem.replace(' ', '_')
    chapters = chapter_spans(pages, chaptered=info['chaptered'])
    if info['chaptered']:
        resolved = chapters_resolved(chapters)
        missing = [n for n in CHAPTER_NAMES if n not in resolved]
        if missing:
            # A chapter with no opener and no rescuable title is folded into its predecessor,
            # which is exactly the failure that emptied Chapter 6 once. Say so where it is kept.
            msg = f'{pdf_name}: only {len(resolved)} of {EXPECTED_CHAPTERS} chapters resolved; missing {missing}'
            _log(msg)
            with _state_lock:
                INGEST_STATE['warnings'].append(msg)
    pending, indexed, skipped, relabelled, removed = [], 0, 0, 0, 0

    def flush():
        nonlocal pending, indexed, skipped, relabelled
        if not pending:
            return True
        if not reindex:
            already = rag_engine_instance.existing_ids([it['id'] for it in pending])
            # Chapter labels are recomputed from the whole document on every run, so a chunk that is
            # already indexed can still be carrying a wrong one. Refreshing its metadata costs no
            # embedding call, so a resumed run repairs the pages it skips. A chunk whose TEXT changed
            # (a page re-transcribed) is not skipped: its vector describes text that no longer exists.
            unchanged = [it for it in pending if it['id'] in already and not it['changed']]
            refreshed = rag_engine_instance.update_metadata(unchanged)
            if refreshed < len(unchanged):
                with _state_lock:
                    INGEST_STATE['warnings'].append(
                        f'{pdf_name}: {len(unchanged) - refreshed} already-indexed chunk(s) could not be relabelled')
            relabelled += refreshed
            skipped += len(unchanged)
            pending = [it for it in pending if it['id'] not in already or it['changed']]
            with _state_lock:
                INGEST_STATE['relabelled_chunks'] += refreshed
        try:
            indexed += rag_engine_instance.index_passages(pending)
        except Exception as e:
            _log(f'{pdf_name}: embedding failed ({str(e)[:140]}) - stopping indexing of this document; re-run later to resume')
            with _state_lock:
                INGEST_STATE['warnings'].append(f'{pdf_name}: indexing incomplete (embedding quota/network)')
            pending = []
            _persist()
            return False
        with _state_lock:
            INGEST_STATE['indexed_chunks'] += len(pending)
        pending = []
        _persist()
        return True

    for page in sorted(pages):
        if page_range and not (page_range[0] <= page <= page_range[1]):
            continue
        text = pages[page]
        chapter = chapters.get(page, DEFAULT_CHAPTER)
        page_prefix = f'{stem}_p{page}_c'
        previous = dict(CurriculumPassage.objects.filter(chroma_id__startswith=page_prefix)
                        .values_list('chroma_id', 'content'))
        printed = page - info['printed_page_offset']
        source_ref = f'{info["short"]} p.{printed}'
        new_ids = []
        for idx, chunk in enumerate(chunk_page(text)):
            chroma_id = f'{page_prefix}{idx + 1}'
            new_ids.append(chroma_id)
            obj, _created = CurriculumPassage.objects.update_or_create(
                chroma_id=chroma_id,
                defaults={
                    'chapter': chapter,
                    'topic': f'{info["short"]} page {printed}',
                    'language': info['language'],
                    'content': chunk,
                    'source_ref': source_ref,
                },
            )
            pending.append({'id': chroma_id, 'text': chunk, 'changed': previous.get(chroma_id) != chunk, 'metadata': {
                'chapter': chapter, 'topic': obj.topic, 'language': info['language'],
                'source_ref': source_ref, 'doc': info['doc'], 'page': page,
            }})
        # A page re-transcribed into fewer chunks leaves its old higher-numbered chunks behind,
        # still carrying the old text. Remove them from both stores.
        stale = [cid for cid in previous if cid not in new_ids]
        if stale:
            rag_engine_instance.delete_ids(stale)
            CurriculumPassage.objects.filter(chroma_id__in=stale).delete()
            removed += len(stale)
        if len(pending) >= 32 and not flush():
            sync_pages(pdf_name)
            return indexed
    flush()
    _log(f'{pdf_name}: indexed {indexed} new chunks ({skipped} already indexed, {relabelled} relabelled'
         + (f', {removed} stale removed' if removed else '') + ')')
    sync_pages(pdf_name)
    return indexed


def run_ingest(pdf_names=None, page_range=None, workers=3, ocr=True, reindex=False, retry_empty=False,
               trigger='command', triggered_by_id=None):
    pdf_names = pdf_names or [n for n in DOCS if (RAG_DIR / n).exists()]
    _set(running=True, stage='starting', error=None, warnings=[], started_at=time.time(), finished_at=None,
         indexed_chunks=0, relabelled_chunks=0, done_pages=0, total_pages=0, run_id=None)
    run = IngestRun.objects.create(
        trigger=trigger, triggered_by_id=triggered_by_id,
        documents=list(pdf_names), page_range=f'{page_range[0]}-{page_range[1]}' if page_range else '',
        ocr=ocr, reindex=reindex, retry_empty=retry_empty, workers=workers,
        embedding_model=gemini.embed_model_name(), ocr_model=gemini.model_name() or '',
        code_commit=_code_commit(),
    )
    with _state_lock:
        _CURRENT_RUN['run'] = run
        _CURRENT_RUN['log'] = []
        INGEST_STATE['run_id'] = run.pk
    total = 0
    status = 'done'
    try:
        if reindex:
            rag_engine_instance.clear_index()
            _log('Cleared existing vector index')
        for name in pdf_names:
            if ocr:
                _set(stage=f'ocr:{name}')
                _persist()
                ocr_pdf(name, page_range=page_range, workers=workers, retry_empty=retry_empty)
            _set(stage=f'index:{name}')
            _persist()
            total += index_pdf_cache(name, page_range=page_range, reindex=reindex)
        _set(stage='done')
        _log(f'Ingestion complete. Vector count now {rag_engine_instance.vector_count()}')
    except Exception as e:
        logger.exception('Ingestion failed')
        _set(stage='error', error=str(e))
        _log(f'ERROR: {e}')
        status = 'error'
        raise
    finally:
        _set(running=False, finished_at=time.time())
        _persist(status=status, finished_at=timezone.now(), vector_count_after=rag_engine_instance.vector_count())
        with _state_lock:
            _CURRENT_RUN['run'] = None
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
        finally:
            # The thread that opened the connection releases it. This must not happen inside
            # run_ingest: on the main thread it would close the caller's own transaction.
            close_old_connections()

    threading.Thread(target=target, daemon=True, name='rag-ingest').start()
    return True
