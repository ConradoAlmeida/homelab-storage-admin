from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if h.strip()
]
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# Layout do NAS (precisa bater com o agente)
SITE_NAME = os.environ.get("SITE_NAME", "Homelab Storage")
APP_CONTAINER = os.environ.get("APP_CONTAINER", "homelab-storage-admin")
STORAGE_ROOT = os.environ.get("STORAGE_ROOT", "/mnt/nas")
SNAPSHOT_ROOT = os.environ.get("SNAPSHOT_ROOT", "/mnt/nas/.snapshots")
BACKUP_ROOT = os.environ.get("BACKUP_ROOT", "/mnt/backup")
JELLYFIN_ROOT = os.environ.get("JELLYFIN_ROOT", "/mnt/jellyfin")
ALLOWED_PATH_PREFIXES = tuple(
    p.strip().rstrip("/") + "/"
    for p in os.environ.get("ALLOWED_PATH_PREFIXES", f"{STORAGE_ROOT}/").split(",")
    if p.strip()
)
DF_MOUNTS = tuple(
    m.strip()
    for m in os.environ.get(
        "DF_MOUNTS", f"/,{STORAGE_ROOT},{BACKUP_ROOT},{JELLYFIN_ROOT}"
    ).split(",")
    if m.strip()
)
SNAPSHOT_BACKEND = os.environ.get("SNAPSHOT_BACKEND", "auto").strip().lower()
SNAPSHOT_DENYLIST = tuple(
    s.strip()
    for s in os.environ.get("SNAPSHOT_DENYLIST", "").split(",")
    if s.strip()
)
BIND_ADDR = os.environ.get("BIND_ADDR", "127.0.0.1")
BIND_PORT = int(os.environ.get("BIND_PORT", "8060"))
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))
SERVICES_FILE = Path(os.environ.get("SERVICES_FILE", str(DATA_DIR / "services.ini")))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "history",
    "storage",
    "backups",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SessaoCredenciaisMiddleware",
    "core.middleware.GestaoUsuariosCredenciaisMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.homelab",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

SQLITE_PATH = os.environ.get("DJANGO_SQLITE_PATH")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": SQLITE_PATH or (DATA_DIR / "db.sqlite3"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Unix socket do agente privilegiado (host)
AGENT_SOCKET = os.environ.get("AGENT_SOCKET", "/run/homelab-storage-admin/agent.sock")
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "90"))

# Credenciais (moyaserver). Vazio no Pi: mantém o login local.
CREDENTIALS_URL = os.environ.get("CREDENTIALS_URL", "").rstrip("/")
CREDENTIALS_API_TOKEN = os.environ.get("CREDENTIALS_API_TOKEN", "")
CREDENTIALS_APP = os.environ.get("CREDENTIALS_APP", "storage")
# Explícito por host: desliga só a gestão de identidade que o Credenciais assume.
# O Pi mantém 0; o moyaserver configura 1 no host.env.
CREDENTIALS_MANAGE_USERS = os.environ.get("CREDENTIALS_MANAGE_USERS", "0") == "1"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = os.environ.get("DJANGO_SECURE_COOKIES", "0") == "1"
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
