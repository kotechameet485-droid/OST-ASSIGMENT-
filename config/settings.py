"""
Django settings for OpenSourceLens project.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import os
import sys
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

from django.core.exceptions import ImproperlyConfigured

INSECURE_SECRET_KEYS = {
    'django-insecure-opensourcelens-dev-key-default',
    'django-insecure-opensourcelens-dev-key-change-in-production',
    'replace-with-your-strong-random-django-secret-key',
}

IS_TESTING = 'test' in sys.argv

# Security settings: In production, DEBUG defaults to False unless explicitly enabled.
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

if DEBUG or IS_TESTING:
    SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-opensourcelens-dev-key-default')
else:
    SECRET_KEY = os.getenv('SECRET_KEY', '').strip()
    if not SECRET_KEY:
        raise ImproperlyConfigured("The SECRET_KEY environment variable must be explicitly configured in production when DEBUG=False.")
    if SECRET_KEY in INSECURE_SECRET_KEYS or SECRET_KEY.startswith('django-insecure-') or len(SECRET_KEY) < 32:
        raise ImproperlyConfigured("A secure, non-default SECRET_KEY with at least 32 characters must be configured in production.")

raw_allowed_hosts = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,.vercel.app')
ALLOWED_HOSTS = [host.strip() for host in raw_allowed_hosts.split(',') if host.strip()]
if '.vercel.app' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('.vercel.app')
if 'testserver' not in ALLOWED_HOSTS and (DEBUG or IS_TESTING):
    ALLOWED_HOSTS.append('testserver')

raw_csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', 'https://*.vercel.app,http://localhost:8000,http://127.0.0.1:8000')
CSRF_TRUSTED_ORIGINS = []
for origin in [o.strip() for o in raw_csrf_origins.split(',') if o.strip()]:
    if not origin.startswith(('http://', 'https://')):
        origin = f"https://{origin}"
    CSRF_TRUSTED_ORIGINS.append(origin)
if 'https://*.vercel.app' not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append('https://*.vercel.app')

# Security HTTP headers and cookie flags
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# In production (DEBUG=False and not testing), HTTPS security flags are enabled by default.
ENABLE_HTTPS_SECURITY = os.getenv('ENABLE_HTTPS_SECURITY', str(not DEBUG and not IS_TESTING)).lower() in ('true', '1', 'yes')
if not DEBUG and not IS_TESTING and ENABLE_HTTPS_SECURITY:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # OpenSourceLens Apps
    'dashboard.apps.DashboardConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

try:
    import whitenoise
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
except ImportError:
    pass

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'config.wsgi.application'
# ASGI_APPLICATION is omitted to ensure Vercel uses the standard WSGI entrypoint config.wsgi:application

def parse_database_url(url: str, default_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely parses database connection URLs for PostgreSQL and SQLite.
    Properly decodes percent-encoded usernames and passwords, extracts host/port,
    and isolates query parameters (such as sslmode) into OPTIONS without leaking credentials.
    """
    from urllib.parse import urlparse, unquote, parse_qs
    if not url or not isinstance(url, str):
        raise ImproperlyConfigured("DATABASE_URL must be a non-empty string.")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ('postgres', 'postgresql', 'sqlite', 'sqlite3'):
        raise ImproperlyConfigured(
            f"Unsupported database scheme: '{parsed.scheme}'. "
            "OpenSourceLens production supports 'postgresql://' or 'postgres://'."
        )

    if 'sqlite' in parsed.scheme:
        db_path = parsed.path[1:] if parsed.path.startswith('/') else parsed.path
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': db_path or str(BASE_DIR / 'db.sqlite3'),
        }

    options: Dict[str, Any] = dict(default_options or {})
    if parsed.query:
        query_params = parse_qs(parsed.query)
        for key in ('sslmode', 'channel_binding', 'sslrootcert', 'target_session_attrs'):
            if key in query_params and query_params[key]:
                options[key] = query_params[key][0]

    raw_path = parsed.path[1:] if parsed.path.startswith('/') else parsed.path
    db_name = unquote(raw_path) if raw_path else ''
    if not db_name:
        raise ImproperlyConfigured("DATABASE_URL must specify a database name.")

    db_config: Dict[str, Any] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': db_name,
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or '127.0.0.1',
        'PORT': str(parsed.port) if parsed.port else '5432',
    }
    if options:
        db_config['OPTIONS'] = options
    return db_config


# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_NAME = os.getenv('DB_NAME', 'opensourcelens')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = os.getenv('DB_PORT', '5432')
USE_SQLITE = os.getenv('USE_SQLITE', 'False').lower() in ('true', '1', 'yes')

if IS_TESTING or USE_SQLITE or 'sqlite3' in DB_ENGINE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
elif DATABASE_URL:
    sslmode_env = os.getenv('DB_SSLMODE', '').strip()
    default_opts = {'sslmode': sslmode_env} if sslmode_env else {}
    DATABASES = {
        'default': parse_database_url(DATABASE_URL, default_options=default_opts),
    }
else:
    # Managed PostgreSQL via individual DB_* variables
    db_options_pg: Dict[str, Any] = {}
    sslmode_env = os.getenv('DB_SSLMODE', '').strip()
    if sslmode_env:
        db_options_pg['sslmode'] = sslmode_env
    default_db_pg: Dict[str, Any] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
    if db_options_pg:
        default_db_pg['OPTIONS'] = db_options_pg
    DATABASES = {
        'default': default_db_pg,
    }

# In-memory caching for repeated API lookups and analysis data
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'opensourcelens-cache',
    }
}
ANALYSIS_CACHE_FRESHNESS_MINUTES = int(os.getenv('ANALYSIS_CACHE_FRESHNESS_MINUTES', '60'))

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

try:
    import whitenoise  # noqa: F401
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }
except ImportError:
    pass

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# GitHub API Configuration
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN', '').strip()
GITHUB_API_BASE_URL = os.getenv('GITHUB_API_BASE_URL', 'https://api.github.com').rstrip('/')
GITHUB_API_TIMEOUT = int(os.getenv('GITHUB_API_TIMEOUT', '12'))

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '[%(asctime)s] %(levelname)s in %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'loggers': {
        'dashboard': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
