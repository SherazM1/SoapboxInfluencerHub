from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - keeps app usable without DB dependency.
    psycopg = None
    dict_row = None


def get_database_url() -> str | None:
    """Read the PostgreSQL connection string from the environment."""
    return os.environ.get("DATABASE_URL") or None


def is_database_available() -> bool:
    """Return whether the DB driver and connection string are available."""
    return bool(psycopg and dict_row and get_database_url())


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
