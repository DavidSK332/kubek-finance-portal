"""Environment-only secrets. The same values must reach web and worker."""
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def settings():
    production = os.getenv("APP_ENV", "development") == "production"
    database_url = os.getenv("DATABASE_URL") or f"sqlite:///{ROOT / 'instance' / 'portal.db'}"
    if database_url.startswith(("postgres://", "postgresql://")):
        database_url = "postgresql+psycopg://" + database_url.split("://", 1)[1]
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    return {
        "PRODUCTION": production,
        "SECRET_KEY": os.getenv("SECRET_KEY", ""),
        "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", ""),
        "BASE_URL": base_url,
        "TRUSTED_HOSTS": [urlparse(base_url).hostname] if production else None,
        "SQLALCHEMY_DATABASE_URI": database_url,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "MAX_CONTENT_LENGTH": 128 * 1024,
        "SESSION_COOKIE_SECURE": production,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=4),
        "WTF_CSRF_TIME_LIMIT": 4 * 60 * 60,
        "RATELIMIT_STORAGE_URI": os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        "RATELIMIT_HEADERS_ENABLED": True,
        "TRUST_PROXY": os.getenv("TRUST_PROXY", "0") == "1",
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "EMAIL_BACKEND": os.getenv("EMAIL_BACKEND", "disabled"),
        "MAIL_FROM": os.getenv("MAIL_FROM", ""),
        "SMTP_HOST": os.getenv("SMTP_HOST", ""),
        "SMTP_PORT": int(os.getenv("SMTP_PORT", "587")),
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": os.getenv("SMTP_PASSWORD", ""),
        "SMTP_SECURITY": os.getenv("SMTP_SECURITY", "starttls"),
        "SENDGRID_API_KEY": os.getenv("SENDGRID_API_KEY", ""),
        "ORGANIZATION_NAME": os.getenv("ORGANIZATION_NAME", "KUBEK Finance"),
        "CONTROLLER_NAME": os.getenv("CONTROLLER_NAME", ""),
        "CONTROLLER_ADDRESS": os.getenv("CONTROLLER_ADDRESS", ""),
        "PRIVACY_EMAIL": os.getenv("PRIVACY_EMAIL", ""),
        "RETENTION_DAYS": int(os.getenv("RETENTION_DAYS", "180")),
        "PRIVACY_VERSION": "2026-10-18-v1",
        "MAX_JOB_ATTEMPTS": 3,
    }
