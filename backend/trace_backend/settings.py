import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR.parent / '.env')


def env_flag(name, default=False):
    return os.environ.get(name, '1' if default else '0').strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


# Off unless the environment says otherwise. DEBUG drives error pages, host checking,
# CORS and the Secure flag on cookies, so the safe value has to be the one you get by
# forgetting to set it. Put DEBUG=1 in backend/.env for local development.
DEBUG = env_flag('DEBUG', default=False)

# Anything not listed is refused by Django's host header check. Extend for a LAN
# deployment with e.g. ALLOWED_HOSTS=lab-server.school.edu,192.168.1.50
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS') or ['localhost', '127.0.0.1', '[::1]']

# Origins allowed to make browser requests. In development the Vite dev server on :3000
# proxies /api, so same-origin already covers it; these matter once the SPA is served
# from somewhere else.
TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')

SECRET_KEY = os.environ.get('SECRET_KEY', '').strip()
if not SECRET_KEY:
    if not DEBUG:
        # This key signs sessions and the trace_device research cookie. A shipped default
        # is public knowledge the moment the repository is, so refuse to start without one.
        raise ImproperlyConfigured(
            'SECRET_KEY is not set. Generate one with:\n'
            '  python -c "from django.core.management.utils import get_random_secret_key;'
            ' print(get_random_secret_key())"\n'
            'and put it in backend/.env (or set DEBUG=1 for local development).'
        )
    SECRET_KEY = 'django-insecure-development-only-key-do-not-deploy'

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
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Uploaded files (profile avatars). Django serves these itself in DEBUG. A single-site
# lab deployment can keep doing so with SERVE_MEDIA=1; anything internet-facing should
# put a real file server in front instead.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
AVATAR_MAX_BYTES = 5 * 1024 * 1024
SERVE_MEDIA = env_flag('SERVE_MEDIA', default=DEBUG)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Wide open in development (the dev server and the SPA are on different ports); pinned
# to the configured origins everywhere else.
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_CREDENTIALS = True
if not CORS_ALLOW_ALL_ORIGINS:
    CORS_ALLOWED_ORIGINS = env_list('CORS_ALLOWED_ORIGINS') or TRUSTED_ORIGINS

# ---------------------------------------------------------------------------
# Transport security.
#
# HTTPS_ONLY defaults to "on whenever DEBUG is off", which is the safe default but is
# also the setting most likely to lock you out: on a plain-http server SECURE_SSL_REDIRECT
# loops and Secure cookies are never sent, so nobody can log in. A proctored lab server
# on a closed network without TLS should set HTTPS_ONLY=0 deliberately.
# ---------------------------------------------------------------------------
HTTPS_ONLY = env_flag('HTTPS_ONLY', default=not DEBUG)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

# Behind a reverse proxy that terminates TLS, tell Django how to detect https.
if env_flag('BEHIND_TLS_PROXY', default=False):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if HTTPS_ONLY:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    # Fail closed. A view that forgets its @permission_classes is private, not public;
    # the handful of genuinely public endpoints (register, login) opt out explicitly.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # Rates alone do nothing - DRF only throttles when a throttle CLASS is in play, so
    # these two must stay listed here or every limit below is silently inert.
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',       # anonymous callers can only reach register/login/logout
        'user': '600/min',      # generous: the workspace polls while a student works
        'tutor': '30/min',      # scoped (trace_backend/throttles.py) - Gemini generation
        'code-run': '60/min',   # scoped - server-side compile and execute
        'ingest': '5/hour',     # scoped - a full OCR pass over the textbooks
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
# Code execution sandbox (tutor/sandbox.py).
#
# POST /api/code/run/ executes participant-written programs. CODE_SANDBOX picks the
# containment backend: 'auto' (best available), 'docker' (full isolation), 'rlimit'
# (POSIX resource caps only) or 'none'.
#
# CODE_SANDBOX_REQUIRED defaults to "on whenever DEBUG is off": with no sandbox
# available the endpoint refuses to run anything rather than executing unprotected.
# Build the image first:
#   docker build -f backend/tutor/sandbox.Dockerfile -t trace-tutor-runner:1 backend/tutor
# ---------------------------------------------------------------------------
CODE_SANDBOX = os.environ.get('CODE_SANDBOX', 'auto').strip().lower()
CODE_SANDBOX_REQUIRED = env_flag('CODE_SANDBOX_REQUIRED', default=not DEBUG)
CODE_SANDBOX_IMAGE = os.environ.get('CODE_SANDBOX_IMAGE', 'trace-tutor-runner:1')
CODE_SANDBOX_CPUS = os.environ.get('CODE_SANDBOX_CPUS', '1.0')
CODE_SANDBOX_STARTUP_GRACE = int(os.environ.get('CODE_SANDBOX_STARTUP_GRACE', '15'))

# Caps applied to the student's program.
CODE_RUN_MEMORY_MB = int(os.environ.get('CODE_RUN_MEMORY_MB', '256'))
CODE_RUN_CPU_SECONDS = int(os.environ.get('CODE_RUN_CPU_SECONDS', '5'))
CODE_RUN_MAX_PROCESSES = int(os.environ.get('CODE_RUN_MAX_PROCESSES', '64'))
CODE_RUN_MAX_FILE_MB = int(os.environ.get('CODE_RUN_MAX_FILE_MB', '4'))

# Compiling is legitimately heavier than running, so it gets its own, larger caps.
CODE_COMPILE_MEMORY_MB = int(os.environ.get('CODE_COMPILE_MEMORY_MB', '1024'))
CODE_COMPILE_CPU_SECONDS = int(os.environ.get('CODE_COMPILE_CPU_SECONDS', '60'))
CODE_COMPILE_MAX_PROCESSES = int(os.environ.get('CODE_COMPILE_MAX_PROCESSES', '128'))
CODE_COMPILE_MAX_FILE_MB = int(os.environ.get('CODE_COMPILE_MAX_FILE_MB', '64'))

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
# Tied to HTTPS_ONLY, not to DEBUG: a browser will not send a Secure cookie over plain
# http, so marking them Secure on a non-TLS lab server silently breaks every login.
SESSION_COOKIE_SECURE = HTTPS_ONLY
CSRF_COOKIE_NAME = 'trace_csrf'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = HTTPS_ONLY
CSRF_TRUSTED_ORIGINS = TRUSTED_ORIGINS

# Application cookies (trace_backend/middleware.py and accounts/views.py):
#   trace_device - signed, HttpOnly, 1 year. Anonymous device id attached to research telemetry so
#                  shared lab computers and returning devices can be told apart.
#   trace_lang   - readable by the SPA, 1 year. Preferred language, so the UI and the tutor keep
#                  speaking Bangla/English before login and after logout.
DEVICE_COOKIE_NAME = 'trace_device'
DEVICE_COOKIE_AGE = 60 * 60 * 24 * 365
LANG_COOKIE_NAME = 'trace_lang'
LANG_COOKIE_AGE = 60 * 60 * 24 * 365
