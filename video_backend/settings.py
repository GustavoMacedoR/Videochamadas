import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'replace-me-with-a-secure-key'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'rest_framework',
    'calls',
    'corsheaders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
]

ROOT_URLCONF = 'video_backend.urls'

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

WSGI_APPLICATION = 'video_backend.wsgi.application'
ASGI_APPLICATION = 'video_backend.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True
USE_L10N = True
USE_TZ = True

STATIC_URL = '/static/'

# Where `manage.py collectstatic` will copy files to. Must be a filesystem path
# and match the volume mounted by docker-compose (we use /app/static in compose).
STATIC_ROOT = BASE_DIR / 'static'

# Media files (recordings upload)
MEDIA_URL = '/video/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Automatic cleanup for media/recordings
RECORDINGS_AUTO_CLEANUP_ENABLED = os.environ.get('RECORDINGS_AUTO_CLEANUP_ENABLED', '1').strip().lower() in {'1', 'true', 'yes', 'on'}
try:
    RECORDINGS_AUTO_CLEANUP_INTERVAL_MINUTES = max(1, int(os.environ.get('RECORDINGS_AUTO_CLEANUP_INTERVAL_MINUTES', '30')))
except (TypeError, ValueError):
    RECORDINGS_AUTO_CLEANUP_INTERVAL_MINUTES = 30
# Age-based retention: only delete recordings older than this (hours). Default: 168h = 7 days.
try:
    RECORDINGS_MAX_AGE_HOURS = max(1, int(os.environ.get('RECORDINGS_MAX_AGE_HOURS', '168')))
except (TypeError, ValueError):
    RECORDINGS_MAX_AGE_HOURS = 168

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'calls': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Channels - use in-memory layer for simplicity (no Redis required)

# Configure CHANNEL_LAYERS: prefer Redis when CHANNEL_REDIS_URL is provided
_redis_url = os.environ.get('CHANNEL_REDIS_URL')
if _redis_url:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [_redis_url],
            },
        }
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer'
        }
    }

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True
