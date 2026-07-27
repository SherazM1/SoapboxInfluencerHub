from __future__ import annotations

import os
from typing import Any

from core.db import dict_row, load_local_env, psycopg

CAMPAIGN_OPS_DATABASE_ENV_VAR = "CAMPAIGN_OPS_DATABASE_URL"


def get_campaign_ops_database_url() -> str | None:
    """Read the Campaign Operations Postgres URL from the environment."""
    load_local_env()
    return os.environ.get(CAMPAIGN_OPS_DATABASE_ENV_VAR) or None


def is_campaign_ops_database_available() -> bool:
    """Return whether Campaign Operations has a usable DB configuration."""
    return bool(psycopg and dict_row and get_campaign_ops_database_url())


def get_campaign_ops_database_status() -> dict[str, Any]:
    """Return safe Campaign Operations database configuration status."""
    database_url_detected = bool(get_campaign_ops_database_url())
    status: dict[str, Any] = {
        "env_var": CAMPAIGN_OPS_DATABASE_ENV_VAR,
        "database_url_detected": database_url_detected,
        "driver_available": bool(psycopg and dict_row),
        "connection_succeeded": False,
        "message": f"{CAMPAIGN_OPS_DATABASE_ENV_VAR} is missing.",
    }
    if not database_url_detected:
        return status
    if not status["driver_available"]:
        status["message"] = "PostgreSQL driver is not installed."
        return status

    connection = None
    try:
        connection = psycopg.connect(get_campaign_ops_database_url(), row_factory=dict_row)
        status["connection_succeeded"] = True
        status["message"] = "Campaign Operations database connection succeeded."
    except Exception:
        status["message"] = "Campaign Operations database connection failed."
    finally:
        if connection is not None:
            connection.close()
    return status


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
        return psycopg.connect(database_url, row_factory=dict_row)
    except Exception as exc:
        from core.campaign_ops.exceptions import CampaignOpsDatabaseError

        raise CampaignOpsDatabaseError("Campaign Operations database connection failed.") from exc
