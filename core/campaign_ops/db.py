from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from core.db import dict_row, load_local_env, psycopg

CAMPAIGN_OPS_DATABASE_ENV_VAR = "CAMPAIGN_OPS_DATABASE_URL"
REQUIRED_SCHEMA_TABLES = ("schema_migrations", "campaign_ops_users")
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_STATEMENT_TIMEOUT_MS = 15000
DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS = 15000


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


def get_campaign_ops_database_url() -> str | None:
    """Read the Campaign Operations Postgres URL from the environment."""
    load_local_env()
    return os.environ.get(CAMPAIGN_OPS_DATABASE_ENV_VAR) or None


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
            options=(
                f"-c statement_timeout={DEFAULT_STATEMENT_TIMEOUT_MS} "
                f"-c idle_in_transaction_session_timeout={DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS}"
            ),
        )
    except Exception as exc:
        from core.campaign_ops.exceptions import CampaignOpsDatabaseError

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
        initialized = campaign_ops_schema_is_initialized(connection)
    except Exception:
        return CampaignOpsSetupStatus(
            state="unreachable",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=False,
            schema_initialized=False,
            message="Campaign Operations database connection failed.",
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
