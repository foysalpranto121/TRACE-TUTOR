import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR.parent / '.env')

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-trace-tutor-research-key-2026')

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',

    # TRACE Tutor core apps
    'accounts',
    'curriculum',
    'tutor',
    'logging_app',
    'assessment',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'trace_backend.middleware.TraceCookiesMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'trace_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'trace_backend.wsgi.application'

# Database Setup: PostgreSQL with fallback to SQLite
DB_NAME = os.environ.get('DB_NAME', 'trace_tutor_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')

if os.environ.get('USE_POSTGRES') == '1':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': DB_NAME,
            'USER': DB_USER,
            'PASSWORD': DB_PASSWORD,
            'HOST': DB_HOST,
            'PORT': DB_PORT,
            # Reuse connections across requests; fail fast if the server is down instead of hanging a request.
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {'connect_timeout': 10},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {'timeout': 30},
        }
    }

    # WAL lets the background RAG ingest write while request threads read, instead of "database is locked".
    from django.db.backends.signals import connection_created

    def _sqlite_pragmas(sender, connection, **kwargs):
        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                cursor.execute('PRAGMA journal_mode=WAL;')
                cursor.execute('PRAGMA busy_timeout=30000;')

    connection_created.connect(_sqlite_pragmas)

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Teachers and researchers must present this code at registration; students never see it.
# No default: a committed fallback is public the moment the repository is, and this code is
# what stands between a stranger and every exam paper plus all participant data. Unset means
# staff registration is refused outright (see accounts/views.py), never "any code will do".
STAFF_ACCESS_CODE = os.environ.get('STAFF_ACCESS_CODE', '')

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

# Uploaded files (profile avatars). Served by Django in DEBUG; put a real file server in front for production.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
AVATAR_MAX_BYTES = 5 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '600/min',
        'user': '1200/min',
    },
}

# ---------------------------------------------------------------------------
# Caching - two tiers (see trace_backend/cache.py):
#   default    : in-process memory (LocMemCache). Hot, short-lived data - dashboard summaries,
#                RAG status, the item bank. Microsecond reads; cleared on restart.
#   persistent : DatabaseCache table `trace_cache` in PostgreSQL. Durable, shared between
#                processes - Gemini tutor answers and query embeddings, so a repeated question
#                costs no API quota and survives restarts. Created by `manage.py createcachetable`
#                (run automatically after `migrate`, see logging_app/apps.py).
# ---------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'trace-tutor-memory',
        'TIMEOUT': 300,
        'OPTIONS': {'MAX_ENTRIES': 5000},
    },
    'persistent': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'trace_cache',
        'TIMEOUT': 60 * 60 * 24,
        'OPTIONS': {'MAX_ENTRIES': 20000, 'CULL_FREQUENCY': 4},
    },
}
TUTOR_ANSWER_CACHE_SECONDS = int(os.environ.get('TUTOR_ANSWER_CACHE_SECONDS', 60 * 60 * 24 * 7))
QUERY_EMBEDDING_CACHE_SECONDS = 60 * 60 * 24 * 30
DASHBOARD_CACHE_SECONDS = 60
RAG_STATUS_CACHE_SECONDS = 15

# ---------------------------------------------------------------------------
# Sessions & cookies. API clients authenticate with DRF tokens; Django sessions (admin) are
# written through to the database with the memory cache in front (cached_db).
# ---------------------------------------------------------------------------
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_NAME = 'trace_session'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_NAME = 'trace_csrf'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if o.strip()]

# Application cookies (trace_backend/middleware.py and accounts/views.py):
#   trace_device - signed, HttpOnly, 1 year. Anonymous device id attached to research telemetry so
#                  shared lab computers and returning devices can be told apart.
#   trace_lang   - readable by the SPA, 1 year. Preferred language, so the UI and the tutor keep
#                  speaking Bangla/English before login and after logout.
DEVICE_COOKIE_NAME = 'trace_device'
DEVICE_COOKIE_AGE = 60 * 60 * 24 * 365
LANG_COOKIE_NAME = 'trace_lang'
LANG_COOKIE_AGE = 60 * 60 * 24 * 365
