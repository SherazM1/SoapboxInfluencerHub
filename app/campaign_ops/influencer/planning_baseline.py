from __future__ import annotations

from datetime import date


def compact_date(value: date | None, *, reference_year: int | None = None) -> str:
    if value is None:
        return ""
    if reference_year is not None and value.year != reference_year:
        return f"{value.month}/{value.day}/{value.year}"
    return f"{value.month}/{value.day}"
