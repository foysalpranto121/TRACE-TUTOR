"""Local-only disposable PostgreSQL settings for teacher portal regression tests.
Run: python manage.py test --settings=trace_backend.qa_settings --noinput
Never points at the application's configured database or remote database hosts.
"""
import os
from pathlib import Path
from copy import deepcopy

# No real provider requests or live log writes in this test process.
for variable in ('OPENAI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'LOG_FILE'):
    os.environ[variable] = ''
from .settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

DATABASES = deepcopy(DATABASES)  # noqa: F405
if DATABASES['default']['HOST'] not in ('localhost', '127.0.0.1', '::1'):
    raise ImproperlyConfigured('QA tests require local PostgreSQL; remote databases are refused.')
DATABASES['default']['CONN_MAX_AGE'] = 0
DATABASES['default']['NAME'] = 'trace_teacher_qa_unused'
DATABASES['default']['TEST'] = {'NAME': 'test_trace_teacher_qa_20261009'}
CACHES = {name: {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                 'LOCATION': 'teacher-qa-' + name} for name in ('default', 'persistent')}
LOG_FILE = ''
LOGGING['handlers'].pop('file', None)  # noqa: F405
for config in LOGGING['loggers'].values():  # noqa: F405
    config['handlers'] = [name for name in config.get('handlers', []) if name != 'file']

QA_ARTIFACTS = Path(BASE_DIR).parent / 'docs' / 'teacher-portal-qa' / 'test-artifacts'  # noqa: F405
MEDIA_ROOT = QA_ARTIFACTS / 'media'
BACKUP_DIR = QA_ARTIFACTS / 'backups'
TEST_RUNNER = 'trace_backend.qa_runner.TeacherQARunner'
