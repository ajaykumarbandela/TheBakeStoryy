from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Import dj_database_url only if needed
try:
    import dj_database_url
except ImportError:
    dj_database_url = None

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-your-secret-key-here-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['*']  # For testing, allows all hosts. For production, use your EC2 public DNS/IP.

# Security settings for production (disabled SSL redirect for testing)
if not DEBUG:
    SECURE_SSL_REDIRECT = False  # Set to True only when you have HTTPS configured
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',  # Added for chatbot API
    'bakery',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Add WhiteNoise for static files
    'corsheaders.middleware.CorsMiddleware',  # Added for chatbot API - must be before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'bakery_project.urls'

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

WSGI_APPLICATION = 'bakery_project.wsgi.application'

# Database configuration
# Use PostgreSQL in production (via DATABASE_URL), SQLite locally
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and dj_database_url:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files configuration
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = []

# Media files (uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# WhiteNoise configuration for static files in production
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',  # Allow access for chatbot
    ],
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'


# Razorpay Configuration
# Use environment variables for live mode (rzp_live_*), test mode (rzp_test_*)
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')  
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')    

# AWS DynamoDB Configuration
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')  
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_REGION_NAME = os.environ.get('AWS_REGION_NAME', 'ap-south-1') 
DYNAMODB_CONTACT_TABLE = 'bakery_contacts' 

# SMS Notification Settings
ADMIN_PHONE_NUMBER = '+918074691873'  
BAKERY_NAME = 'Heavenly Bakery'
SMS_NOTIFICATIONS_ENABLED = False
# AWS SES Email Configuration (Professional Email Service)
# For local development, use console backend
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django_ses.SESBackend'
    AWS_SES_REGION_NAME = 'ap-south-1'  
    AWS_SES_REGION_ENDPOINT = 'email.ap-south-1.amazonaws.com'
    AWS_SES_FROM_EMAIL = 'btechmuthyam@gmail.com'  # verified in AWS SES

# Email Notification Settings
EMAIL_HOST_USER = 'btechmuthyam@gmail.com'  # Your email
ADMIN_EMAIL = 'btechmuthyam@gmail.com'  # Where you want to receive notifications
EMAIL_NOTIFICATIONS_ENABLED = True  

# Order Notification Settings
ORDER_NOTIFICATION_EMAIL = 'btechmuthyam@gmail.com'  # Where to receive order notifications
ORDER_EMAIL_NOTIFICATIONS_ENABLED = True  
ORDER_SMS_NOTIFICATIONS_ENABLED = False  
BAKERY_BUSINESS_NAME = 'Heavenly Bakery'
BAKERY_BUSINESS_PHONE = '8074691873'

# CORS Settings for Chatbot API (allows requests from HTML file)
CORS_ALLOW_ALL_ORIGINS = True  # For development only
# For production, use:
# CORS_ALLOWED_ORIGINS = [
#     "https://yourdomain.com",
# ]
BAKERY_BUSINESS_ADDRESS = 'Chaitanyapuri, Dilsukhnagar, Hyderabad'
BAKERY_BUSINESS_EMAIL = 'btechmuthyam@gmail.com'