import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_config():
    # Environment variables take precedence; never search a parent directory for .env.
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return {
        "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL"),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "SECRET_KEY": os.getenv("SECRET_KEY"),
        "APP_STORAGE_ROOT": os.getenv("APP_STORAGE_ROOT", "./data"),
        "PORT": os.getenv("PORT", "8080"),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        # Multipart overhead is outside the 10 MiB file itself.
        "MAX_CONTENT_LENGTH": 10 * 1024 * 1024 + 128 * 1024,
        "MAX_JSON_CONTENT_LENGTH": 128 * 1024,
    }


def validate_config(config):
    secret = config.get("SECRET_KEY")
    if not secret or secret == "CHANGE_ME" or len(secret) < 32:
        raise ValueError("Set SECRET_KEY to a random string of at least 32 characters in .env or the environment.")
    try:
        url = make_url(config.get("SQLALCHEMY_DATABASE_URI") or "")
    except Exception:
        raise ValueError("Set DATABASE_URL to a valid PostgreSQL URL.") from None
    if url.get_backend_name() != "postgresql" or not url.database:
        raise ValueError("DATABASE_URL must point to a PostgreSQL database.")
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Use postgresql+psycopg:// in DATABASE_URL.")
    config["SQLALCHEMY_DATABASE_URI"] = url
    try:
        port = int(config["PORT"])
    except (TypeError, ValueError):
        raise ValueError("PORT must be an integer between 1 and 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535.")
    config["PORT"] = port
    root = Path(config["APP_STORAGE_ROOT"]).expanduser()
    config["APP_STORAGE_ROOT"] = (PROJECT_ROOT / root).resolve() if not root.is_absolute() else root.resolve()
