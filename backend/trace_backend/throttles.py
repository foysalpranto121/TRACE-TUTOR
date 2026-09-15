"""Named rate limits for the endpoints that cost real money or real CPU.

DRF resolves a throttle's rate from settings.DEFAULT_THROTTLE_RATES via its `scope`,
so the numbers live in settings.py next to the rest of the tuning knobs.

These are keyed per user (all three endpoints require authentication), which is what
we want for a study: one participant hammering the tutor cannot exhaust the shared
Gemini quota for the rest of the cohort.
"""
from rest_framework.throttling import UserRateThrottle


class TutorThrottle(UserRateThrottle):
    """Each tutor turn is a Gemini generation call billed against the study's quota."""
    scope = 'tutor'


class CodeRunThrottle(UserRateThrottle):
    """Each run compiles and executes a program on the server."""
    scope = 'code-run'


class IngestThrottle(UserRateThrottle):
    """A full OCR pass costs hours of vision-model calls; it should be started rarely."""
    scope = 'ingest'
