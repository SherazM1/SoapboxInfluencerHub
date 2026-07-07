from __future__ import annotations

from datetime import date
from typing import Any

from core.db import get_db_connection, maybe_init_database


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe_ratio(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _number(numerator)
    denominator_value = _number(denominator)
    if denominator_value <= 0:
        return None
    return numerator_value / denominator_value


def _format_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")


def fetch_active_campaign_rows() -> list[dict[str, Any]]:
    """Fetch all active historical campaigns for benchmark calculations."""
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
        where c.is_active = true
        order by c.campaign_date desc, c.program_name asc
    """
    with get_db_connection() as connection:
        if connection is None:
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []


def fetch_historical_campaign_view() -> list[dict[str, Any]]:
    """Fetch historical campaign rows formatted for the Streamlit table."""
    rows = fetch_active_campaign_rows()
    return [
        {
            "Program": row["program_name"],
            "Date": _format_date(row["campaign_date"]),
            "Year": row["campaign_year"],
            "Client": row.get("client_name") or "",
            "Influencers": _number(row["influencer_count"]),
            "Engagements": _number(row["engagements"]),
            "Organic Impressions": _number(row["organic_impressions"]),
            "Paid Impressions": _number(row["paid_impressions"]),
            "Paid Spend (Impressions)": _number(row["paid_spend_impressions"]),
            "Paid Engagements": _number(row["paid_engagements"]),
            "Paid Spend (Engagements)": _number(row["paid_spend_engagements"]),
            "Paid Clicks": _number(row["paid_clicks"]),
            "Paid Spend (Clicks)": _number(row["paid_spend_clicks"]),
        }
        for row in rows
    ]


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
        organic = _safe_ratio(row["organic_impressions"], row["influencer_count"])
        engagements = _safe_ratio(row["engagements"], row["influencer_count"])
        paid_impressions = _safe_ratio(
            row["paid_impressions"], row["paid_spend_impressions"]
        )
        paid_clicks = _safe_ratio(row["paid_clicks"], row["paid_spend_clicks"])
        paid_engagements = _safe_ratio(
            row["paid_engagements"], row["paid_spend_engagements"]
        )

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
    if any(not values for values in series.values()):
        return None
    return series


def build_seed_campaign_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one future Excel/Data-sheet row for insertion code."""
    return {
        "program_name": row.get("Program") or row.get("program_name"),
        "campaign_date": row.get("Date") or row.get("campaign_date"),
        "influencer_count": row.get("# of Influencers") or row.get("influencer_count"),
        "engagements": row.get("Engagements") or row.get("engagements"),
        "organic_impressions": row.get("Organic Impressions")
        or row.get("organic_impressions"),
        "paid_impressions": row.get("Paid Impressions") or row.get("paid_impressions"),
        "paid_spend_impressions": row.get("Paid Spend (Impressions)")
        or row.get("paid_spend_impressions"),
        "paid_engagements": row.get("Paid Engagement")
        or row.get("paid_engagements"),
        "paid_spend_engagements": row.get("Paid Spend (Engagements)")
        or row.get("paid_spend_engagements"),
        "paid_clicks": row.get("Paid Clicks") or row.get("paid_clicks"),
        "paid_spend_clicks": row.get("Paid Spend (Clicks)")
        or row.get("paid_spend_clicks"),
    }
