import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from backend or root
env_path = BASE_DIR / '.env'
if not env_path.exists():
    env_path = BASE_DIR.parent / '.env'
load_dotenv(dotenv_path=env_path)

def clean_env(key, default=""):
    val = os.getenv(key, default)
    if val is None:
        return default
    val = str(val).strip()
    if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
        val = val[1:-1]
    return val

SECRET_KEY = clean_env(
    'SECRET_KEY',
    'django-insecure-6u-&vm^ra+%_nf9oe18%1yqwqpst)dqq6eh3+-(69jfk$9jruh'
)

PLATFORM = clean_env('PLATFORM', 'DEV')
DEBUG = PLATFORM == 'DEV'

allowed_hosts_str = clean_env('ALLOWED_HOSTS', '*')
if allowed_hosts_str == '*':
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(',') if h.strip()]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'corsheaders',
    'rest_framework',
    
    # Local apps
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

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

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# Database Configuration (PostgreSQL)
DB_NAME = clean_env('POSTGRES_DB', 'tododb')
DB_USER = clean_env('POSTGRES_USER', 'postgres')
DB_PASSWORD = clean_env('POSTGRES_PASSWORD', '123')
DB_HOST = clean_env('POSTGRES_HOST', '127.0.0.1')
DB_PORT = clean_env('POSTGRES_PORT', '5432')

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
    }
}

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
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# Google Cloud Storage Configuration
GS_PROJECT_ID = clean_env('GS_PROJECT_ID', 'magnusforum-452015')
GS_BUCKET_NAME = clean_env('GS_BUCKET_NAME', 'magnus-placement-test')
GOOGLE_STORAGE_JSON_NAME = clean_env('GOOGLE_STORAGE_JSON_NAME', 'credential.json')
CURRENT_PLATFORM = clean_env('CURRENT_PLATFORM', 'DEV')

