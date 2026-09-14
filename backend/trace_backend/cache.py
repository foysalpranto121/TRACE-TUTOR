"""Helpers over Django's cache framework.

settings.CACHES defines two tiers:
  memory     - LocMemCache: per process, microseconds, gone on restart.
  persistent - DatabaseCache (`trace_cache` table in PostgreSQL): shared, survives restarts.

`tiered_get_or_set` reads memory first, then the database, and only then computes the value
(writing it back to both). Tutor answers and query embeddings use it so repeated questions are
instant and spend no Gemini quota.
"""
import hashlib
import json
import logging

from django.core.cache import caches

logger = logging.getLogger(__name__)

memory = caches['default']
persistent = caches['persistent']

_MISSING = object()


def cache_key(namespace, *parts):
    """Stable short key for JSON-serialisable parts. Prompts are long and full of characters cache
    backends dislike, so the parts are hashed."""
    raw = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return f"{namespace}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _persistent_get(key):
    try:
        return persistent.get(key, _MISSING)
    except Exception as exc:  # table missing / database down: behave like a miss
        logger.warning('persistent cache read failed for %s: %s', key, exc)
        return _MISSING


def _persistent_set(key, value, timeout):
    try:
        persistent.set(key, value, timeout)
    except Exception as exc:
        logger.warning('persistent cache write failed for %s: %s', key, exc)


def tiered_get_or_set(key, producer, persistent_timeout, memory_timeout=300, should_store=lambda value: True):
    """Return (value, tier); tier is 'memory', 'persistent' or 'computed'."""
    value = memory.get(key, _MISSING)
    if value is not _MISSING:
        return value, 'memory'
    value = _persistent_get(key)
    if value is not _MISSING:
        memory.set(key, value, memory_timeout)
        return value, 'persistent'
    value = producer()
    if should_store(value):
        _persistent_set(key, value, persistent_timeout)
        memory.set(key, value, memory_timeout)
    return value, 'computed'
