from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Any
from urllib.parse import parse_qs, urlparse

from core.db import dict_row, load_local_env, psycopg

CAMPAIGN_OPS_DATABASE_ENV_VAR = "CAMPAIGN_OPS_DATABASE_URL"
REQUIRED_SCHEMA_TABLES = ("schema_migrations", "campaign_ops_users")
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CampaignOpsSetupStatus:
    """Safe Campaign Operations setup status for UI and tests."""

    state: str
    database_url_detected: bool
    driver_available: bool
    connection_succeeded: bool
    schema_initialized: bool
    message: str

    @property
    def is_initialized(self) -> bool:
        """Return whether Campaign Operations schema is ready for repository queries."""
        return self.state == "initialized"


def _url_diagnostics(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {
            "url_detected": False,
            "url_non_empty": False,
        }
    parsed = urlparse(database_url)
    query = parse_qs(parsed.query)
    return {
        "url_detected": True,
        "url_non_empty": bool(database_url.strip()),
        "scheme": parsed.scheme or None,
        "host": parsed.hostname,
        "port": parsed.port,
        "database_present": bool((parsed.path or "").strip("/")),
        "username_present": bool(parsed.username),
        "password_present": bool(parsed.password),
        "sslmode": (query.get("sslmode") or [None])[0],
        "connect_timeout": DEFAULT_CONNECT_TIMEOUT_SECONDS,
    }


def _safe_exception_message(exc: BaseException) -> str:
    message = str(exc)
    database_url = get_campaign_ops_database_url()
    if database_url:
        message = message.replace(database_url, "<redacted-url>")
    return message[:1000]


def log_safe_connection_error(stage: str, exc: BaseException, database_url: str | None = None) -> None:
    """Log connection diagnostics without credentials or full connection URLs."""
    LOGGER.exception(
        "Campaign Operations database connection diagnostic",
        extra={
            "stage": stage,
            "exception_type": type(exc).__name__,
            "safe_message": _safe_exception_message(exc),
            "url": _url_diagnostics(database_url),
            "driver": getattr(psycopg, "__version__", None),
        },
    )


def get_campaign_ops_database_url() -> str | None:
    """Read the Campaign Operations Postgres URL from the environment."""
    load_local_env()
    raw_value = os.environ.get(CAMPAIGN_OPS_DATABASE_ENV_VAR)
    if raw_value is None:
        return None
    return raw_value.strip() or None


def is_campaign_ops_database_available() -> bool:
    """Return whether Campaign Operations has a usable DB configuration."""
    return bool(psycopg and dict_row and get_campaign_ops_database_url())


def get_campaign_ops_database_status() -> dict[str, Any]:
    """Return safe Campaign Operations database configuration status."""
    setup_status = get_campaign_ops_setup_status()
    return {
        "env_var": CAMPAIGN_OPS_DATABASE_ENV_VAR,
        "database_url_detected": setup_status.database_url_detected,
        "driver_available": setup_status.driver_available,
        "connection_succeeded": setup_status.connection_succeeded,
        "schema_initialized": setup_status.schema_initialized,
        "state": setup_status.state,
        "message": setup_status.message,
    }


def connect_to_campaign_ops_database() -> Any:
    """Open a Campaign Operations Postgres connection."""
    database_url = get_campaign_ops_database_url()
    if not database_url:
        from core.campaign_ops.exceptions import CampaignOpsDatabaseError

        raise CampaignOpsDatabaseError(f"{CAMPAIGN_OPS_DATABASE_ENV_VAR} is not configured.")
    if psycopg is None or dict_row is None:
        from core.campaign_ops.exceptions import CampaignOpsDatabaseError

        raise CampaignOpsDatabaseError("PostgreSQL driver is not installed.")
    try:
        return psycopg.connect(
            database_url,
            row_factory=dict_row,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS,
            application_name="kkg_influencerhub_campaign_ops",
        )
    except Exception as exc:
        from core.campaign_ops.exceptions import CampaignOpsDatabaseError

        log_safe_connection_error("connect", exc, database_url)
        raise CampaignOpsDatabaseError("Campaign Operations database connection failed.") from exc


def table_exists(connection: Any, table_name: str) -> bool:
    """Check for a table using Postgres metadata, not application table queries."""
    with connection.cursor() as cursor:
        cursor.execute("select to_regclass(%s) as table_name", (f"public.{table_name}",))
        row = cursor.fetchone()
    return bool(row and row["table_name"])


def campaign_ops_schema_is_initialized(connection: Any | None = None) -> bool:
    """Return whether required Campaign Operations schema tables exist."""
    if connection is not None:
        return all(table_exists(connection, table_name) for table_name in REQUIRED_SCHEMA_TABLES)

    owned_connection = connect_to_campaign_ops_database()
    try:
        return campaign_ops_schema_is_initialized(owned_connection)
    finally:
        owned_connection.close()


def get_campaign_ops_setup_status() -> CampaignOpsSetupStatus:
    """Distinguish missing config, unreachable DB, missing schema, and initialized states."""
    database_url_detected = bool(get_campaign_ops_database_url())
    driver_available = bool(psycopg and dict_row)
    if not database_url_detected:
        return CampaignOpsSetupStatus(
            state="missing_env",
            database_url_detected=False,
            driver_available=driver_available,
            connection_succeeded=False,
            schema_initialized=False,
            message=f"{CAMPAIGN_OPS_DATABASE_ENV_VAR} is missing.",
        )
    if not driver_available:
        return CampaignOpsSetupStatus(
            state="unreachable",
            database_url_detected=True,
            driver_available=False,
            connection_succeeded=False,
            schema_initialized=False,
            message="PostgreSQL driver is not installed.",
        )

    connection = None
    try:
        connection = connect_to_campaign_ops_database()
    except Exception:
        return CampaignOpsSetupStatus(
            state="unreachable",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=False,
            schema_initialized=False,
            message="Campaign Operations database connection failed.",
        )
    try:
        initialized = campaign_ops_schema_is_initialized(connection)
    except Exception as exc:
        log_safe_connection_error("setup_status_schema_check", exc, get_campaign_ops_database_url())
        return CampaignOpsSetupStatus(
            state="uninitialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=False,
            message="Campaign Operations database is reachable but schema status could not be verified.",
        )
    finally:
        if connection is not None:
            connection.close()

    if not initialized:
        return CampaignOpsSetupStatus(
            state="uninitialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=False,
            message="Campaign Operations database is reachable but schema is not initialized.",
        )
    return CampaignOpsSetupStatus(
        state="initialized",
        database_url_detected=True,
        driver_available=True,
        connection_succeeded=True,
        schema_initialized=True,
        message="Campaign Operations database is initialized.",
    )


def is_undefined_table_error(exc: BaseException) -> bool:
    """Return whether an exception represents a missing Postgres table."""
    if psycopg is None:
        return False
    undefined_table = getattr(getattr(psycopg, "errors", None), "UndefinedTable", None)
    return bool(undefined_table and isinstance(exc, undefined_table))
