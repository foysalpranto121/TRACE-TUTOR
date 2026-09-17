from django.core.management.base import BaseCommand

from curriculum.ocr_ingest import run_ingest, DOCS, RAG_DIR


class Command(BaseCommand):
    help = 'OCR the scanned NCTB PDFs in RAG/ with Gemini, then chunk + embed them into the vector index.'

    def add_arguments(self, parser):
        parser.add_argument('--pdf', action='append', help='PDF file name inside RAG/ (repeatable). Default: all known.')
        parser.add_argument('--pages', help='Page range to process, e.g. 140-160')
        parser.add_argument('--workers', type=int, default=3)
        parser.add_argument('--index-only', action='store_true', help='Skip OCR; index whatever is already cached')
        parser.add_argument('--reindex', action='store_true', help='Drop the vector index before indexing')
        parser.add_argument('--retry-empty', action='store_true',
                            help='Re-OCR pages already cached as near-empty instead of counting them as done')

    def handle(self, *args, **opts):
        pdfs = opts['pdf'] or [n for n in DOCS if (RAG_DIR / n).exists()]
        page_range = None
        if opts['pages']:
            lo, hi = opts['pages'].split('-')
            page_range = (int(lo), int(hi))
        total = run_ingest(pdf_names=pdfs, page_range=page_range, workers=opts['workers'],
                           ocr=not opts['index_only'], reindex=opts['reindex'],
                           retry_empty=opts['retry_empty'])
        self.stdout.write(self.style.SUCCESS(f'Indexed {total} chunks from {", ".join(pdfs)}'))
