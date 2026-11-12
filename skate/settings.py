from datetime import timedelta
import os 
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

load_dotenv()
# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY=os.environ.get("SECRET_KEY")
# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG") == "True"

USE_CLOUDINARY = os.environ.get("USE_CLOUDINARY", "False").lower() == "true"

_cloudinary_cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
_cloudinary_api_key = os.environ.get("CLOUDINARY_API_KEY")
_cloudinary_api_secret = os.environ.get("CLOUDINARY_API_SECRET")

if _cloudinary_cloud_name and _cloudinary_api_key and _cloudinary_api_secret:
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": _cloudinary_cloud_name,
        "API_KEY": _cloudinary_api_key,
        "API_SECRET": _cloudinary_api_secret,
        "SECURE": True,
    }

HOST = os.environ.get("HOST", "")
ADMIN_URL = os.getenv("ADMIN_URL", "admin/")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

_host = os.environ.get("HOST", "")
if _host and _host.startswith("https://"):
    _host = _host[8:]
if _host:
    ALLOWED_HOSTS.append(_host)

# Render sets the name of the service in this variable, so the service
# answers even when HOST was not configured.
_render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if _render_hostname and _render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_hostname)

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

if _host:
    CSRF_TRUSTED_ORIGINS.append("https://" + _host)

if _render_hostname:
    CSRF_TRUSTED_ORIGINS.append("https://" + _render_hostname)

if DEBUG:
    # The local development server can be reached over plain HTTP or over
    # HTTPS (see the "runsslserver" management command). Both origins have to
    # be trusted for POST/PUT/DELETE requests to pass the CSRF check.
    CSRF_TRUSTED_ORIGINS += [
        "http://localhost:8000",
        "https://localhost:8000",
        "http://127.0.0.1:8000",
        "https://127.0.0.1:8000",
        "http://localhost:8443",
        "https://localhost:8443",
        "http://127.0.0.1:8443",
        "https://127.0.0.1:8443",
    ]

# The OpenStreetMap tile usage policy asks that the browser sends a
# valid HTTP Referer to the tile servers. Django defaults to
# "same-origin", which drops the Referer on every cross origin request.
# "strict-origin-when-cross-origin" sends the origin of the page, so
# the tile server can still identify the application.
SECURE_REFERRER_POLICY = os.environ.get(
    "SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin"
)


# Production security settings
# Active when DEBUG=False

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')



# Application definition

INSTALLED_APPS = [
    'drf_spectacular',
    'rest_framework',
    'skate',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
   # 'django.contrib.sites' #fix /admin endpoint 
]

if USE_CLOUDINARY:
    INSTALLED_APPS += ['cloudinary_storage', 'cloudinary']



MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'skate.urls'

# The project has its own login page, Django has to send the
# unauthenticated visitors there instead of the default one.
LOGIN_URL = "/profile/"
LOGIN_REDIRECT_URL = "/profile/"

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'skate.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME'),
            'USER': os.environ.get("DB_USER"),
            'PASSWORD': os.environ.get("DB_PASSWORD"),
            'HOST': os.environ.get("DB_HOST"),
            'PORT': os.environ.get("DB_PORT")
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    "OPTIONS": {
        "min_length": 8
    }
    
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]



REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 10,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema'
    ,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',  
        'user': '1000/day',  
        'geocode': os.environ.get("GEOCODE_THROTTLE_RATE", "30/min"),
        'overpass': os.environ.get("OVERPASS_DISCOVERY_THROTTLE_RATE", "60/min"),
    },
}

AUTH_USER_MODEL='skate.User'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'



SPECTACULAR_SETTINGS = {
    'TITLE': 'Skate API',
    'DESCRIPTION': 'API documentation',
    'VERSION': '1.0.0',

    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,

    'SECURITY': [{
        'BearerAuth': [],
    }],

    'COMPONENTS': {
        'securitySchemes': {
            'BearerAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}


# OpenStreetMap / Overpass API configuration
#
# Used by the `import_osm_skateparks` management command. The endpoint
# and timings can be overridden through the environment without touching
# the code. No credentials are required: the Overpass API is a public
# service, but it does require a descriptive User-Agent.

OVERPASS_API_URL = os.environ.get(
    "OVERPASS_API_URL", "https://overpass-api.de/api/interpreter"
)
# The other public instances of the service. They are used when the
# main one can not be reached, for example when the network of the
# server blocks it. The list is read from the environment, separated by
# commas.
OVERPASS_MIRRORS = [
    url.strip()
    for url in os.environ.get("OVERPASS_MIRRORS", "").split(",")
    if url.strip()
]
OVERPASS_TIMEOUT = int(os.environ.get("OVERPASS_TIMEOUT", "120"))
OVERPASS_MAX_RETRIES = int(os.environ.get("OVERPASS_MAX_RETRIES", "3"))
OVERPASS_RETRY_BACKOFF = float(os.environ.get("OVERPASS_RETRY_BACKOFF", "3"))
OVERPASS_USER_AGENT = os.environ.get(
    "OVERPASS_USER_AGENT",
    "RollingUp-SkateSpots/1.0 (https://rolling-up.onrender.com)",
)

# Nominatim is used only to turn a place name into a bounding box when
# the Overpass `geocodeArea` specialiser is not available.
NOMINATIM_API_URL = os.environ.get(
    "NOMINATIM_API_URL", "https://nominatim.openstreetmap.org/search"
)
NOMINATIM_TIMEOUT = int(os.environ.get("NOMINATIM_TIMEOUT", "30"))
NOMINATIM_USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    os.environ.get(
        "OVERPASS_USER_AGENT",
        "RollingUp-SkateSpots/1.0 (https://rolling-up.onrender.com)",
    ),
)

# Location search used by the spot form to find a place by name.
#
# The requests go through the backend (`/api/geocode/search/`) so the
# application identifies itself properly, the answers are cached and the
# number of requests can be throttled.
GEOCODE_MIN_QUERY_LENGTH = int(os.environ.get("GEOCODE_MIN_QUERY_LENGTH", "3"))
GEOCODE_MAX_RESULTS = int(os.environ.get("GEOCODE_MAX_RESULTS", "8"))
GEOCODE_CACHE_SECONDS = int(os.environ.get("GEOCODE_CACHE_SECONDS", "86400"))
GEOCODE_LANGUAGE = os.environ.get("GEOCODE_LANGUAGE", "es")
GEOCODE_THROTTLE_RATE = os.environ.get("GEOCODE_THROTTLE_RATE", "30/min")

# Maximum number of requests per second the whole application sends to
# Nominatim. The Nominatim usage policy allows an absolute maximum of
# one request per second for the whole site, not per user, so this
# limit is applied globally in `skate.geocode.services`.
NOMINATIM_MAX_REQUESTS_PER_SECOND = float(
    os.environ.get("NOMINATIM_MAX_REQUESTS_PER_SECOND", "1")
)

# Map tiles.
#
# Two providers are supported and the choice is a setting, so it can be
# changed without a new release.
#
#  * The standard OpenStreetMap tiles. They need no key and they are
#    free, but their usage policy asks for a few things:
#    https://operations.osmfoundation.org/policies/tiles/
#    The dark look of the interface is done with a CSS filter.
#
#  * The CARTO basemaps. They have their own styles and they look good
#    for an interface, but CARTO asks for an API key since September
#    2026 and for the credit of both OpenStreetMap and CARTO:
#    https://carto.com/basemaps/apikey/
#    Without a key the server answers with a placeholder tile that says
#    "API KEY REQUIRED" instead of the map.
#    The raster tiles of CARTO only go up to zoom 18, a bigger value
#    makes the server answer "Forbidden".
OSM_TILE_URL = os.environ.get(
    "OSM_TILE_URL",
    "https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png",
)
OSM_TILE_MAX_ZOOM = int(os.environ.get("OSM_TILE_MAX_ZOOM", "18"))

# Only needed by a provider that uses subdomains, such as CARTO. The
# standard OpenStreetMap tiles do not use any and the usage policy asks
# for exactly `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.
OSM_TILE_SUBDOMAINS = os.environ.get("OSM_TILE_SUBDOMAINS", "abcd")

# The key of the tile provider. CARTO requires one, the standard
# OpenStreetMap tiles do not.
OSM_TILE_API_KEY = os.environ.get("OSM_TILE_API_KEY", "")

# Where the tiles are served from. The tiles of a provider that needs
# a key go through the application, so the key never reaches the
# browser.
TILE_PROXY_PATH = os.environ.get(
    "TILE_PROXY_PATH", "/tiles/{z}/{x}/{y}{r}.png"
)

# Where the map opens when nothing else is known. It is the centre of
# the spots that are in the database.
MAP_DEFAULT_CENTER = (
    float(os.environ.get("MAP_DEFAULT_LAT", "20.6767")),
    float(os.environ.get("MAP_DEFAULT_LON", "-103.3475")),
)
MAP_DEFAULT_ZOOM = int(os.environ.get("MAP_DEFAULT_ZOOM", "9"))

# A contact address published by the application. The tile and the
# geocoding policies ask for a way to reach the operator.
OSM_CONTACT_EMAIL = os.environ.get(
    "OSM_CONTACT_EMAIL", "rollingup.app@gmail.com"
)

# Username of the service account that owns OSM imported spots.
OSM_SERVICE_USER = os.environ.get("OSM_SERVICE_USER", "osm_importer")

# Google OAuth 2.0 (sign in with Google)
#
# The browser is sent to Google and comes back to
# /auth/google/callback/, which verifies the ID token and issues the
# same JWT the normal login issues. The client secret never leaves the
# server. GOOGLE_REDIRECT_URI has to be registered in Google Cloud
# Console; when it is empty the callback URL is derived from HOST.
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "")

# Google Places API (New)
#
# Only the Nearby Search and the Place Photos endpoints are used. The
# key is a credential and stays on the server: the browser reads the
# photographs through the photo proxy of the application.
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
GOOGLE_PLACES_TIMEOUT = int(os.environ.get("GOOGLE_PLACES_TIMEOUT", "30"))
GOOGLE_PLACES_SEARCH_RADIUS = int(
    os.environ.get("GOOGLE_PLACES_SEARCH_RADIUS", "5000")
)
GOOGLE_PLACES_MAX_RESULTS = int(
    os.environ.get("GOOGLE_PLACES_MAX_RESULTS", "20")
)
GOOGLE_PLACES_MAX_PAGES = int(os.environ.get("GOOGLE_PLACES_MAX_PAGES", "3"))
GOOGLE_PLACES_PHOTO_MAX_WIDTH = int(
    os.environ.get("GOOGLE_PLACES_PHOTO_MAX_WIDTH", "1200")
)
# Google allows place content to be cached for at most 30 days. The
# importer stores a bounded copy and stamps it with this expiry.
GOOGLE_PLACES_DATA_TTL_SECONDS = int(
    os.environ.get("GOOGLE_PLACES_DATA_TTL_SECONDS", str(60 * 60 * 24 * 30))
)
# Photographs are proxied and may be cached by the browser for a day.
# They are never written to the media storage of the application.
GOOGLE_PLACES_PHOTO_CACHE_SECONDS = int(
    os.environ.get("GOOGLE_PLACES_PHOTO_CACHE_SECONDS", str(60 * 60 * 24))
)
GOOGLE_PLACES_DEDUPE_RADIUS_METERS = float(
    os.environ.get("GOOGLE_PLACES_DEDUPE_RADIUS_METERS", "120")
)

# Live discovery for the map and the feed.
#
# These requests never write to the database. The answer is cached so
# rapid map movement does not hammer the public Overpass instance, and a
# stale copy is kept as a fallback for a temporary outage.
OVERPASS_DISCOVERY_DEFAULT_RADIUS = int(
    os.environ.get("OVERPASS_DISCOVERY_DEFAULT_RADIUS", "10000")
)
OVERPASS_DISCOVERY_MAX_RADIUS = int(
    os.environ.get("OVERPASS_DISCOVERY_MAX_RADIUS", "50000")
)
OVERPASS_DISCOVERY_MAX_RESULTS = int(
    os.environ.get("OVERPASS_DISCOVERY_MAX_RESULTS", "200")
)
OVERPASS_DISCOVERY_MAX_VIEWPORT_SPAN = float(
    os.environ.get("OVERPASS_DISCOVERY_MAX_VIEWPORT_SPAN", "1.5")
)
OVERPASS_DISCOVERY_CACHE_SECONDS = int(
    os.environ.get("OVERPASS_DISCOVERY_CACHE_SECONDS", "86400")
)
OVERPASS_DISCOVERY_STALE_SECONDS = int(
    os.environ.get("OVERPASS_DISCOVERY_STALE_SECONDS", "86400")
)
OVERPASS_DISCOVERY_THROTTLE_RATE = os.environ.get(
    "OVERPASS_DISCOVERY_THROTTLE_RATE", "60/min"
)

# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'skate' / 'static']

STORAGES = {
    "default": {
        "BACKEND": (
            "cloudinary_storage.storage.MediaCloudinaryStorage"
            if USE_CLOUDINARY
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

