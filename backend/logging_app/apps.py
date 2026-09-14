import logging

from django.apps import AppConfig
from django.core.management import call_command
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


def _ensure_cache_table(sender, using='default', **kwargs):
    """The `persistent` cache is a database table; create it right after migrations so a fresh
    deployment only ever needs `manage.py migrate`. Idempotent - skips tables that exist."""
    try:
        call_command('createcachetable', database=using, verbosity=0)
    except Exception as exc:  # never block migrations on the cache table
        logger.warning('createcachetable failed: %s', exc)


class LoggingAppConfig(AppConfig):
    name = 'logging_app'

    def ready(self):
        from . import signals  # noqa: F401 - registers the dashboard cache invalidation receivers
        post_migrate.connect(_ensure_cache_table, sender=self, dispatch_uid='trace.createcachetable')
