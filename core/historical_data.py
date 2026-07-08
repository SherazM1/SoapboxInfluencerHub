from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.db import get_db_connection, maybe_init_database

EXCEL_DATA_COLUMNS = [
    "Program",
    "Date",
    "# of Influencers",
    "Engagements",
    "Organic Impressions",
    "Impressions Per Influencer",
    "Engagements Per Influencer",
    "Paid Impressions",
    "Paid Spend (Impressions)",
    "Impressions per $1 Spend",
    "Paid Engagement",
    "Paid Spend (Engagement)",
    "Engagements per $1",
    "Paid Clicks",
    "Paid Spend (Clicks)",
    "Clicks per $1",
]

__all__ = [
    "EXCEL_DATA_COLUMNS",
    "fetch_historical_campaign_view",
]


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _optional_number(numerator)
    denominator_value = _optional_number(denominator)
    if numerator_value is None or denominator_value is None:
        return None
    if denominator_value <= 0:
        return None
    return numerator_value / denominator_value


def _format_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and not _is_blank(row[key]):
            return row[key]
    return None


def derive_campaign_metrics(row: dict[str, Any]) -> dict[str, float | None]:
    """Compute Excel Data-sheet derived columns from raw source fields."""
    return {
        "impressions_per_influencer": _safe_ratio(
            row.get("organic_impressions"), row.get("influencer_count")
        ),
        "engagements_per_influencer": _safe_ratio(
            row.get("engagements"), row.get("influencer_count")
        ),
        "impressions_per_dollar": _safe_ratio(
            row.get("paid_impressions"), row.get("paid_spend_impressions")
        ),
        "engagements_per_dollar": _safe_ratio(
            row.get("paid_engagements"), row.get("paid_spend_engagements")
        ),
        "clicks_per_dollar": _safe_ratio(
            row.get("paid_clicks"), row.get("paid_spend_clicks")
        ),
    }


def parse_campaign_date(value: Any) -> date | None:
    """Parse a campaign date from UI, Excel, or DB-shaped values."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue
    return None


def normalize_campaign_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw Historical Data form/import values for DB writes."""
    normalized = build_seed_campaign_payload(payload)
    normalized["campaign_date"] = parse_campaign_date(normalized["campaign_date"])
    normalized["client_name"] = _first_present(payload, "Client", "client_name")
    normalized["notes"] = _first_present(payload, "Notes", "notes")
    return normalized


def validate_campaign_payload(payload: dict[str, Any]) -> list[str]:
    """Validate required raw/source fields before a DB write."""
    errors = []
    if not payload.get("program_name"):
        errors.append("Program is required.")
    if payload.get("campaign_date") is None:
        errors.append("Date is required.")
    required_numeric_fields = {
        "influencer_count": "# of Influencers is required.",
        "engagements": "Engagements is required.",
        "organic_impressions": "Organic Impressions is required.",
    }
    for key, message in required_numeric_fields.items():
        if payload.get(key) is None:
            errors.append(message)
        elif payload[key] < 0:
            errors.append(message.replace("is required", "must be 0 or greater"))
    nullable_numeric_fields = (
        "paid_impressions",
        "paid_spend_impressions",
        "paid_engagements",
        "paid_spend_engagements",
        "paid_clicks",
        "paid_spend_clicks",
    )
    for key in nullable_numeric_fields:
        if payload.get(key) is not None and payload[key] < 0:
            errors.append(f"{key} must be 0 or greater.")
    return errors


def fetch_active_campaign_rows(year: int | None = None) -> list[dict[str, Any]]:
    """Fetch all active historical campaigns for benchmark calculations."""
    maybe_init_database()
    params: list[Any] = []
    year_filter = ""
    if year is not None:
        year_filter = "and c.campaign_year = %s"
        params.append(year)
    query = """
        select
            c.id,
            c.program_name,
            c.campaign_date,
            c.campaign_year,
            c.client_name,
            c.notes,
            m.influencer_count,
            m.engagements,
            m.organic_impressions,
            m.paid_impressions,
            m.paid_spend_impressions,
            m.paid_engagements,
            m.paid_spend_engagements,
            m.paid_clicks,
            m.paid_spend_clicks
        from campaigns c
        join campaign_metrics m on m.campaign_id = c.id
        where c.is_active = true
        {year_filter}
        order by c.campaign_date asc, c.program_name asc
    """
    query = query.format(year_filter=year_filter)
    with get_db_connection() as connection:
        if connection is None:
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []


def fetch_campaign_years() -> list[int]:
    """Fetch active campaign years for Historical Data filtering."""
    maybe_init_database()
    query = """
        select distinct campaign_year
        from campaigns
        where is_active = true
        order by campaign_year asc
    """
    with get_db_connection() as connection:
        if connection is None:
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return [int(row["campaign_year"]) for row in cursor.fetchall()]
        except Exception:
            return []


def fetch_campaign_by_id(campaign_id: Any) -> dict[str, Any] | None:
    """Fetch one active campaign and metrics row for editing."""
    maybe_init_database()
    query = """
        select
            c.id,
            c.program_name,
            c.campaign_date,
            c.campaign_year,
            c.client_name,
            c.notes,
            m.influencer_count,
            m.engagements,
            m.organic_impressions,
            m.paid_impressions,
            m.paid_spend_impressions,
            m.paid_engagements,
            m.paid_spend_engagements,
            m.paid_clicks,
            m.paid_spend_clicks
        from campaigns c
        join campaign_metrics m on m.campaign_id = c.id
        where c.is_active = true and c.id = %s
    """
    with get_db_connection() as connection:
        if connection is None:
            return None
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (campaign_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception:
            return None


def format_historical_campaign_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch historical campaign rows formatted like the Excel Data sheet."""
    display_rows: list[dict[str, Any]] = []
    for row in rows:
        derived = derive_campaign_metrics(row)
        display_rows.append(
            {
                "Program": row["program_name"],
                "Date": _format_date(row["campaign_date"]),
                "# of Influencers": _number(row["influencer_count"]),
                "Engagements": _number(row["engagements"]),
                "Organic Impressions": _number(row["organic_impressions"]),
                "Impressions Per Influencer": derived["impressions_per_influencer"],
                "Engagements Per Influencer": derived["engagements_per_influencer"],
                "Paid Impressions": _optional_number(row["paid_impressions"]),
                "Paid Spend (Impressions)": _optional_number(
                    row["paid_spend_impressions"]
                ),
                "Impressions per $1 Spend": derived["impressions_per_dollar"],
                "Paid Engagement": _optional_number(row["paid_engagements"]),
                "Paid Spend (Engagement)": _optional_number(
                    row["paid_spend_engagements"]
                ),
                "Engagements per $1": derived["engagements_per_dollar"],
                "Paid Clicks": _optional_number(row["paid_clicks"]),
                "Paid Spend (Clicks)": _optional_number(row["paid_spend_clicks"]),
                "Clicks per $1": derived["clicks_per_dollar"],
            }
        )
    return display_rows


def fetch_historical_campaign_view(year: int | None = None) -> list[dict[str, Any]]:
    """Fetch historical campaign rows formatted like the Excel Data sheet."""
    return format_historical_campaign_rows(fetch_active_campaign_rows(year))


def insert_campaign_with_metrics(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Insert one active campaign and its source metric fields."""
    normalized = normalize_campaign_payload(payload)
    errors = validate_campaign_payload(normalized)
    if errors:
        return False, errors
    if not maybe_init_database():
        return False, ["Database is not configured or reachable."]

    with get_db_connection() as connection:
        if connection is None:
            return False, ["Database connection is not available."]
        try:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        insert into campaigns (
                            program_name, campaign_date, client_name, notes
                        )
                        values (%s, %s, %s, %s)
                        returning id
                        """,
                        (
                            normalized["program_name"],
                            normalized["campaign_date"],
                            normalized["client_name"],
                            normalized["notes"],
                        ),
                    )
                    campaign_id = cursor.fetchone()["id"]
                    cursor.execute(
                        """
                        insert into campaign_metrics (
                            campaign_id,
                            influencer_count,
                            engagements,
                            organic_impressions,
                            paid_impressions,
                            paid_spend_impressions,
                            paid_engagements,
                            paid_spend_engagements,
                            paid_clicks,
                            paid_spend_clicks
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            campaign_id,
                            normalized["influencer_count"],
                            normalized["engagements"],
                            normalized["organic_impressions"],
                            normalized["paid_impressions"],
                            normalized["paid_spend_impressions"],
                            normalized["paid_engagements"],
                            normalized["paid_spend_engagements"],
                            normalized["paid_clicks"],
                            normalized["paid_spend_clicks"],
                        ),
                    )
            return True, []
        except Exception:
            connection.rollback()
            return False, ["Campaign could not be saved. Check for duplicates or invalid values."]


def update_campaign_with_metrics(
    campaign_id: Any, payload: dict[str, Any]
) -> tuple[bool, list[str]]:
    """Update one active campaign and its source metric fields."""
    normalized = normalize_campaign_payload(payload)
    errors = validate_campaign_payload(normalized)
    if errors:
        return False, errors
    if not maybe_init_database():
        return False, ["Database is not configured or reachable."]

    with get_db_connection() as connection:
        if connection is None:
            return False, ["Database connection is not available."]
        try:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        update campaigns
                        set
                            program_name = %s,
                            campaign_date = %s,
                            client_name = %s,
                            notes = %s
                        where id = %s and is_active = true
                        """,
                        (
                            normalized["program_name"],
                            normalized["campaign_date"],
                            normalized["client_name"],
                            normalized["notes"],
                            campaign_id,
                        ),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError("Campaign was not found.")
                    cursor.execute(
                        """
                        update campaign_metrics
                        set
                            influencer_count = %s,
                            engagements = %s,
                            organic_impressions = %s,
                            paid_impressions = %s,
                            paid_spend_impressions = %s,
                            paid_engagements = %s,
                            paid_spend_engagements = %s,
                            paid_clicks = %s,
                            paid_spend_clicks = %s
                        where campaign_id = %s
                        """,
                        (
                            normalized["influencer_count"],
                            normalized["engagements"],
                            normalized["organic_impressions"],
                            normalized["paid_impressions"],
                            normalized["paid_spend_impressions"],
                            normalized["paid_engagements"],
                            normalized["paid_spend_engagements"],
                            normalized["paid_clicks"],
                            normalized["paid_spend_clicks"],
                            campaign_id,
                        ),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError("Campaign metrics were not found.")
            return True, []
        except ValueError as error:
            connection.rollback()
            return False, [str(error)]
        except Exception:
            connection.rollback()
            return False, ["Campaign could not be updated. Check for duplicates or invalid values."]


def archive_campaign(campaign_id: Any) -> tuple[bool, list[str]]:
    """Soft-delete one campaign from active Historical Data and benchmarks."""
    if not maybe_init_database():
        return False, ["Database is not configured or reachable."]

    with get_db_connection() as connection:
        if connection is None:
            return False, ["Database connection is not available."]
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "update campaigns set is_active = false where id = %s and is_active = true",
                    (campaign_id,),
                )
                if cursor.rowcount == 0:
                    connection.rollback()
                    return False, ["Campaign was not found."]
            connection.commit()
            return True, []
        except Exception:
            connection.rollback()
            return False, ["Campaign could not be archived."]


def compute_benchmark_series(
    campaign_rows: list[dict[str, Any]],
) -> dict[str, list[float]]:
    """Compute benchmark series from raw historical campaign values."""
    series: dict[str, list[float]] = {
        "organic_impressions": [],
        "engagements": [],
        "paid_impressions": [],
        "paid_clicks": [],
        "paid_engagements": [],
    }
    for row in campaign_rows:
        derived = derive_campaign_metrics(row)
        organic = derived["impressions_per_influencer"]
        engagements = derived["engagements_per_influencer"]
        paid_impressions = derived["impressions_per_dollar"]
        paid_clicks = derived["clicks_per_dollar"]
        paid_engagements = derived["engagements_per_dollar"]

        if organic is not None:
            series["organic_impressions"].append(organic)
        if engagements is not None:
            series["engagements"].append(engagements)
        if paid_impressions is not None:
            series["paid_impressions"].append(paid_impressions * 1000)
        if paid_clicks is not None:
            series["paid_clicks"].append(paid_clicks * 1000)
        if paid_engagements is not None:
            series["paid_engagements"].append(paid_engagements * 1000)
    return series


def load_historical_benchmarks_from_db() -> dict[str, list[float]] | None:
    """Load benchmark series from all active DB campaigns."""
    rows = fetch_active_campaign_rows()
    if not rows:
        return None
    series = compute_benchmark_series(rows)
    if not any(series.values()):
        return None
    return series


def build_seed_campaign_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one future Excel/Data-sheet row for insertion code."""
    payload = {
        "program_name": _first_present(row, "Program", "program_name"),
        "campaign_date": _first_present(row, "Date", "campaign_date"),
        "influencer_count": _optional_number(
            _first_present(row, "# of Influencers", "influencer_count")
        ),
        "engagements": _optional_number(
            _first_present(row, "Engagements", "engagements")
        ),
        "organic_impressions": _optional_number(
            _first_present(row, "Organic Impressions", "organic_impressions")
        ),
        "paid_impressions": _optional_number(
            _first_present(row, "Paid Impressions", "paid_impressions")
        ),
        "paid_spend_impressions": _optional_number(
            _first_present(row, "Paid Spend (Impressions)", "paid_spend_impressions")
        ),
        "paid_engagements": _optional_number(
            _first_present(row, "Paid Engagement", "paid_engagements")
        ),
        "paid_spend_engagements": _optional_number(
            _first_present(
                row,
                "Paid Spend (Engagement)",
                "Paid Spend (Engagements)",
                "paid_spend_engagements",
                "paid_engagements_spend",
            )
        ),
        "paid_clicks": _optional_number(
            _first_present(row, "Paid Clicks", "paid_clicks")
        ),
        "paid_spend_clicks": _optional_number(
            _first_present(row, "Paid Spend (Clicks)", "paid_spend_clicks")
        ),
    }
    payload.update(derive_campaign_metrics(payload))
    return payload
