"""Keep RAG/OCR test artifacts separate from existing research files."""
from django.conf import settings
from django.test.runner import DiscoverRunner


class TeacherQARunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        from curriculum import rag_engine, ocr_ingest
        rag_engine.CHROMA_DIR = settings.QA_ARTIFACTS / 'chroma'
        ocr_ingest.OCR_DIR = settings.QA_ARTIFACTS / 'ocr'
        ocr_ingest.RAG_DIR = settings.QA_ARTIFACTS / 'pdf'
        settings.QA_ARTIFACTS.mkdir(parents=True, exist_ok=True)
