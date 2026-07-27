from __future__ import annotations

from datetime import date


def trim_or_none(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def validate_date_order(start_date: date | None, target_end_date: date | None) -> str | None:
    if start_date and target_end_date and target_end_date < start_date:
        return "Target end date cannot precede start date."
    return None
