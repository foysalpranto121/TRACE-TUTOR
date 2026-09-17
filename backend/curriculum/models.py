from django.conf import settings
from django.db import models


class CurriculumPassage(models.Model):
    chapter = models.CharField(max_length=100) # e.g. "Chapter 5: C Programming"
    topic = models.CharField(max_length=100)   # e.g. "Loops & Iteration"
    language = models.CharField(max_length=5, default='bn')
    content = models.TextField()
    source_ref = models.CharField(max_length=100) # e.g. "NCTB Board Book Page 142"
    chroma_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.chapter} - {self.topic} ({self.source_ref})"


class IngestRun(models.Model):
    """One invocation of the OCR + indexing pipeline, kept for good.

    The live progress of a run is a dict in process memory (INGEST_STATE), which a restart wipes
    and a second worker never sees. This row is the durable record: what was asked for, who asked,
    what it produced, what went wrong. Runs are rare and short, so the full log is stored.
    """
    TRIGGERS = [('api', 'Researcher dashboard'), ('command', 'manage.py ingest_rag')]
    STATUSES = [('running', 'Running'), ('done', 'Done'), ('error', 'Error')]

    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default='running', db_index=True)
    stage = models.CharField(max_length=80, blank=True, default='')
    trigger = models.CharField(max_length=10, choices=TRIGGERS, default='command')
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='ingest_runs')

    # What was asked for.
    documents = models.JSONField(default=list)          # PDF names inside RAG/
    page_range = models.CharField(max_length=20, blank=True, default='')   # "140-170" or ""
    ocr = models.BooleanField(default=True)
    reindex = models.BooleanField(default=False)
    retry_empty = models.BooleanField(default=False)
    workers = models.PositiveSmallIntegerField(default=3)

    # What it produced.
    done_pages = models.PositiveIntegerField(default=0)
    total_pages = models.PositiveIntegerField(default=0)
    indexed_chunks = models.PositiveIntegerField(default=0)
    relabelled_chunks = models.PositiveIntegerField(default=0)
    vector_count_after = models.PositiveIntegerField(null=True, blank=True)
    warnings = models.JSONField(default=list)
    error = models.TextField(blank=True, default='')
    log = models.JSONField(default=list)

    # What produced it, so a run can be re-explained later.
    embedding_model = models.CharField(max_length=80, blank=True, default='')
    ocr_model = models.CharField(max_length=80, blank=True, default='')
    code_commit = models.CharField(max_length=40, blank=True, default='')

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'Ingest #{self.pk} {self.status} ({", ".join(self.documents) or "no documents"})'


class OcrPage(models.Model):
    """The transcription and indexing status of one page of one source PDF.

    The transcribed text itself stays in the on-disk cache (backend/data/ocr/*.jsonl), because it
    is an expensive vision-model output and a copyrighted textbook. What a researcher needs to
    observe is whether each page came back, how much text it yielded, how many attempts it took,
    which chapter it was filed under and how many chunks of it are in the index - and that lives here.
    """
    document = models.CharField(max_length=100, db_index=True)   # PDF name inside RAG/
    page = models.PositiveIntegerField()
    chars = models.PositiveIntegerField(default=0)
    thin = models.BooleanField(default=False, db_index=True)     # transcribed to almost nothing
    attempts = models.PositiveSmallIntegerField(default=0)
    chapter = models.CharField(max_length=100, blank=True, default='')
    indexed_chunks = models.PositiveSmallIntegerField(default=0)
    transcribed_at = models.DateTimeField(null=True, blank=True)
    indexed_at = models.DateTimeField(null=True, blank=True)
    last_run = models.ForeignKey(IngestRun, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='pages')

    class Meta:
        ordering = ['document', 'page']
        constraints = [
            models.UniqueConstraint(fields=['document', 'page'], name='uniq_ocr_page_per_document'),
        ]

    def __str__(self):
        return f'{self.document} p.{self.page}'
