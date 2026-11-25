import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name):
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "nur-fuer-entwicklung")
DEBUG = os.environ.get("DEBUG", "0") == "1"
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS") or ["*"]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "projects",
    "tickets",
    "kb",
    "api",
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
                "core.context_processors.nav",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "NAME": os.environ.get("POSTGRES_DB", "helpdesk"),
            "USER": os.environ.get("POSTGRES_USER", "helpdesk"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        }
    }
else:
    # Ohne Datenbank-Angaben (z. B. lokal ohne Docker) wird SQLite verwendet.
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Zwischenspeicher in der Datenbank, damit die Anmeldesperre für alle
# Serverprozesse gemeinsam gilt.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "helpdesk_cache",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "de"
TIME_ZONE = os.environ.get("TIME_ZONE", "Europe/Vienna")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Erscheinungsbild ----------------------------------------------------------
# Grundeinstellung: helpdesk (neutral), ebner oder forstenlechner
BRAND = os.environ.get("BRAND", "helpdesk").strip().lower() or "helpdesk"
# Optional je Adresse ein anderes Design, z. B.
# BRAND_HOSTS=ebner.ticket=ebner,forstenlechner.ticket=forstenlechner
BRAND_HOSTS = {
    host.strip().lower(): key.strip().lower()
    for host, _, key in (item.partition("=") for item in env_list("BRAND_HOSTS"))
    if host.strip() and key.strip()
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "helpdesk@example.com")

# --- Dateianhänge -------------------------------------------------------------
MEDIA_ROOT = BASE_DIR / "media"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Virenscan für Uploads über einen ClamAV-Dienst (leer = aus)
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "")
CLAMAV_PORT = int(os.environ.get("CLAMAV_PORT") or 3310)

# --- Zielzeiten (SLA) ---------------------------------------------------------
def _clock(value, fallback):
    from datetime import time

    try:
        hour, minute = (value or fallback).split(":")
        return time(int(hour), int(minute))
    except ValueError:
        hour, minute = fallback.split(":")
        return time(int(hour), int(minute))


# Zielzeiten nur innerhalb der Geschäftszeiten zählen (1) oder rund um die Uhr (0)
SLA_BUSINESS_HOURS = os.environ.get("SLA_BUSINESS_HOURS", "1") == "1"
BUSINESS_OPEN = _clock(os.environ.get("BUSINESS_OPEN"), "08:00")
BUSINESS_CLOSE = _clock(os.environ.get("BUSINESS_CLOSE"), "17:00")
# Arbeitstage: 1 = Montag ... 7 = Sonntag
BUSINESS_DAYS = {
    int(d) - 1 for d in env_list("BUSINESS_DAYS") if d.isdigit() and 1 <= int(d) <= 7
} or {0, 1, 2, 3, 4}
_sla_defaults = (
    {"urgent": 4, "high": 8, "normal": 24, "low": 56}
    if SLA_BUSINESS_HOURS
    else {"urgent": 4, "high": 8, "normal": 72, "low": 168}
)
SLA_HOURS = {
    key: float(os.environ.get(f"SLA_HOURS_{key.upper()}") or default)
    for key, default in _sla_defaults.items()
}

# Zielzeit bis zur ersten Antwort an den Melder
_response_defaults = {"urgent": 1, "high": 2, "normal": 8, "low": 16}
SLA_RESPONSE_HOURS = {
    key: float(os.environ.get(f"SLA_RESPONSE_HOURS_{key.upper()}") or default)
    for key, default in _response_defaults.items()
}
# Gesetzliche Feiertage automatisch eintragen: AT, DE oder leer für keine
HOLIDAY_COUNTRY = os.environ.get("HOLIDAY_COUNTRY", "AT").strip().upper()

# --- Zeiterfassung, Aufbewahrung, Anmeldeschutz -------------------------------
# Eine vergessene Uhr wird nach so vielen Stunden automatisch gestoppt.
TIMER_MAX_HOURS = float(os.environ.get("TIMER_MAX_HOURS") or 10)
# Abgeschlossene Tickets nach so vielen Tagen löschen (0 = nie)
RETENTION_DAYS = int(os.environ.get("RETENTION_DAYS") or 0)
# Gelöste Tickets nach so vielen Tagen automatisch schließen (0 = nie)
AUTO_CLOSE_DAYS = int(os.environ.get("AUTO_CLOSE_DAYS", "").strip() or 7)
# "Wartet auf Rückmeldung": Melder nach so vielen Tagen erinnern (0 = nie) ...
WAITING_REMINDER_DAYS = int(os.environ.get("WAITING_REMINDER_DAYS", "").strip() or 3)
# ... und das Ticket nach so vielen Tagen ohne Antwort schließen (0 = nie)
WAITING_CLOSE_DAYS = int(os.environ.get("WAITING_CLOSE_DAYS", "").strip() or 10)
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS") or 5)
LOGIN_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES") or 15)

# --- E-Mail-Eingang (IMAP) ----------------------------------------------------
IMAP_HOST = os.environ.get("IMAP_HOST", "")
IMAP_SSL = os.environ.get("IMAP_SSL", "1") == "1"
IMAP_PORT = int(os.environ.get("IMAP_PORT") or (993 if IMAP_SSL else 143))
IMAP_USER = os.environ.get("IMAP_USER", "")
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "")
IMAP_FOLDER = os.environ.get("IMAP_FOLDER", "INBOX")
MAIL_POLL_SECONDS = int(os.environ.get("MAIL_POLL_SECONDS") or 60)
MAIL_ALLOWED_DOMAINS = [d.lower() for d in env_list("MAIL_ALLOWED_DOMAINS")]
# Microsoft 365 ohne Kennwort-Anmeldung: App-Registrierung statt IMAP_PASSWORD
IMAP_OAUTH_TENANT = os.environ.get("IMAP_OAUTH_TENANT", "")
IMAP_OAUTH_CLIENT_ID = os.environ.get("IMAP_OAUTH_CLIENT_ID", "")
IMAP_OAUTH_CLIENT_SECRET = os.environ.get("IMAP_OAUTH_CLIENT_SECRET", "")

# --- Betrieb hinter einem Reverse Proxy mit HTTPS -----------------------------
if os.environ.get("BEHIND_HTTPS_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# --- Anmeldung ----------------------------------------------------------------
# Lokale Konten funktionieren immer (z. B. der Administrator aus der .env).
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# LDAP / Active Directory: aktiv, sobald LDAP_SERVER_URI gesetzt ist.
if os.environ.get("LDAP_SERVER_URI"):
    import ldap
    from django_auth_ldap.config import (
        GroupOfNamesType,
        LDAPGroupQuery,
        LDAPSearch,
        NestedActiveDirectoryGroupType,
    )

    AUTHENTICATION_BACKENDS.insert(0, "django_auth_ldap.backend.LDAPBackend")
    AUTH_LDAP_SERVER_URI = os.environ["LDAP_SERVER_URI"]
    AUTH_LDAP_BIND_DN = os.environ.get("LDAP_BIND_DN", "")
    AUTH_LDAP_BIND_PASSWORD = os.environ.get("LDAP_BIND_PASSWORD", "")
    AUTH_LDAP_START_TLS = os.environ.get("LDAP_START_TLS", "0") == "1"
    AUTH_LDAP_CONNECTION_OPTIONS = {ldap.OPT_REFERRALS: 0}
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        os.environ.get("LDAP_USER_BASE", ""),
        ldap.SCOPE_SUBTREE,
        os.environ.get("LDAP_USER_FILTER") or "(sAMAccountName=%(user)s)",
    )
    AUTH_LDAP_USER_ATTR_MAP = {
        "first_name": "givenName",
        "last_name": "sn",
        "email": "mail",
    }
    AUTH_LDAP_ALWAYS_UPDATE_USER = True

    _staff_group = os.environ.get("LDAP_STAFF_GROUP", "")
    _admin_group = os.environ.get("LDAP_ADMIN_GROUP", "")
    if _staff_group or _admin_group:
        _is_ad = os.environ.get("LDAP_GROUP_TYPE", "ad").lower() == "ad"
        AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
            os.environ.get("LDAP_GROUP_BASE") or os.environ.get("LDAP_USER_BASE", ""),
            ldap.SCOPE_SUBTREE,
            "(objectClass=group)" if _is_ad else "(objectClass=groupOfNames)",
        )
        AUTH_LDAP_GROUP_TYPE = (
            NestedActiveDirectoryGroupType() if _is_ad else GroupOfNamesType()
        )
        AUTH_LDAP_USER_FLAGS_BY_GROUP = {}
        if _staff_group and _admin_group:
            AUTH_LDAP_USER_FLAGS_BY_GROUP["is_staff"] = LDAPGroupQuery(
                _staff_group
            ) | LDAPGroupQuery(_admin_group)
        elif _staff_group or _admin_group:
            AUTH_LDAP_USER_FLAGS_BY_GROUP["is_staff"] = _staff_group or _admin_group
        if _admin_group:
            AUTH_LDAP_USER_FLAGS_BY_GROUP["is_superuser"] = _admin_group

# Single Sign-On per OpenID Connect (Microsoft Entra ID, Keycloak, Authentik ...):
# aktiv, sobald OIDC_CLIENT_ID gesetzt ist.
SSO_ENABLED = bool(os.environ.get("OIDC_CLIENT_ID"))
OIDC_STAFF_GROUP = os.environ.get("OIDC_STAFF_GROUP", "")
OIDC_GROUPS_CLAIM = os.environ.get("OIDC_GROUPS_CLAIM") or "groups"
if SSO_ENABLED:
    INSTALLED_APPS.append("mozilla_django_oidc")
    AUTHENTICATION_BACKENDS.append("core.oidc.HelpdeskOIDCBackend")
    OIDC_RP_CLIENT_ID = os.environ["OIDC_CLIENT_ID"]
    OIDC_RP_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
    OIDC_OP_AUTHORIZATION_ENDPOINT = os.environ.get("OIDC_AUTHORIZATION_ENDPOINT", "")
    OIDC_OP_TOKEN_ENDPOINT = os.environ.get("OIDC_TOKEN_ENDPOINT", "")
    OIDC_OP_USER_ENDPOINT = os.environ.get("OIDC_USER_ENDPOINT", "")
    OIDC_OP_JWKS_ENDPOINT = os.environ.get("OIDC_JWKS_ENDPOINT", "")
    OIDC_RP_SIGN_ALGO = os.environ.get("OIDC_SIGN_ALGO") or "RS256"
    OIDC_RP_SCOPES = os.environ.get("OIDC_SCOPES") or "openid email profile"
    OIDC_USERNAME_ALGO = "core.oidc.generate_username"
