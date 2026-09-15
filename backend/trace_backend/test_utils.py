"""Shared base class for API tests."""
from django.core.cache import caches
from django.test import TestCase


class ApiTestCase(TestCase):
    """Django's TestCase, with the caches emptied before each test.

    Two kinds of state otherwise leak between test methods and produce failures that
    look like product bugs:

    * Rate-limit history. DRF keeps it in the default cache, which is a process-wide
      LocMemCache, so the twenty-first registration in a whole test run gets a 429 and
      the assertion failure points at registration rather than at the leaked state.
    * Memoised payloads - dashboard summaries, RAG status, tutor answers - which would
      let one test observe another test's data.

    Subclasses that define setUp must call super().setUp().
    """

    def setUp(self):
        super().setUp()
        for alias in ('default', 'persistent'):
            caches[alias].clear()
