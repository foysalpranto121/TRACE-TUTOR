"""Read-only views of the corpus pipeline for the Django admin at /django-admin/.

Nothing here is editable: these rows are produced by the ingestion pipeline and are the audit
record of how the corpus was built. Editing them by hand would make the record lie.
"""
from django.contrib import admin

from .models import CurriculumPassage, IngestRun, OcrPage


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(IngestRun)
class IngestRunAdmin(ReadOnlyAdmin):
    list_display = ('id', 'started_at', 'finished_at', 'status', 'stage', 'trigger', 'triggered_by',
                    'documents', 'page_range', 'done_pages', 'total_pages', 'indexed_chunks',
                    'relabelled_chunks', 'vector_count_after')
    list_filter = ('status', 'trigger', 'ocr', 'reindex', 'retry_empty')
    date_hierarchy = 'started_at'
    search_fields = ('error', 'code_commit')
    readonly_fields = [f.name for f in IngestRun._meta.fields]


@admin.register(OcrPage)
class OcrPageAdmin(ReadOnlyAdmin):
    list_display = ('document', 'page', 'chapter', 'chars', 'thin', 'attempts', 'indexed_chunks',
                    'transcribed_at', 'indexed_at', 'last_run')
    list_filter = ('document', 'thin', 'chapter', 'attempts')
    search_fields = ('chapter',)
    ordering = ('document', 'page')
    list_per_page = 250


@admin.register(CurriculumPassage)
class CurriculumPassageAdmin(ReadOnlyAdmin):
    list_display = ('chroma_id', 'chapter', 'language', 'source_ref', 'created_at')
    list_filter = ('chapter', 'language')
    search_fields = ('content', 'source_ref', 'chroma_id')
    list_per_page = 100
