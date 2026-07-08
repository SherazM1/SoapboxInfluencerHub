from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - keeps app usable without DB dependency.
    psycopg = None
    dict_row = None

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - keeps deployed env-only config usable.
    load_dotenv = None


_DOTENV_LOADED = False
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_local_env() -> bool:
    """Load local development secrets from .env without overriding real env vars."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return True
    _DOTENV_LOADED = True
    if load_dotenv is None:
        return False
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return False
    return bool(load_dotenv(dotenv_path=env_path, override=False))


def get_database_url() -> str | None:
    """Read the PostgreSQL connection string from the environment."""
    load_local_env()
    return os.environ.get("DATABASE_URL") or None


def is_database_available() -> bool:
    """Return whether the DB driver and connection string are available."""
    return bool(psycopg and dict_row and get_database_url())


def get_database_status() -> dict[str, Any]:
    """Return debug-safe DB configuration and connectivity status."""
    database_url_detected = bool(get_database_url())
    status: dict[str, Any] = {
        "dotenv_supported": load_dotenv is not None,
        "database_url_detected": database_url_detected,
        "driver_available": bool(psycopg and dict_row),
        "connection_succeeded": False,
        "message": "DATABASE_URL is missing.",
    }
    if not database_url_detected:
        return status
    if not status["driver_available"]:
        status["message"] = "PostgreSQL driver is not installed."
        return status

    connection = None
    try:
        connection = psycopg.connect(get_database_url(), row_factory=dict_row)
        status["connection_succeeded"] = True
        status["message"] = "Database connection succeeded."
    except Exception:
        status["message"] = "Database connection failed."
    finally:
        if connection is not None:
            connection.close()
    return status


@contextmanager
def get_db_connection() -> Iterator[object | None]:
    """Open a PostgreSQL connection, or yield None if DB is not configured."""
    if not is_database_available():
        yield None
        return

    connection = None
    try:
        connection = psycopg.connect(get_database_url(), row_factory=dict_row)
        yield connection
    except Exception:
        yield None
    finally:
        if connection is not None:
            connection.close()


def maybe_init_database() -> bool:
    """Create historical campaign tables if the configured database is reachable."""
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    if not schema_path.exists():
        return False

    with get_db_connection() as connection:
        if connection is None:
            return False
        try:
            with connection.cursor() as cursor:
                cursor.execute(schema_path.read_text(encoding="utf-8"))
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            return False
