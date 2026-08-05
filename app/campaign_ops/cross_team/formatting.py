from __future__ import annotations

from datetime import date, datetime
from typing import Any


def label(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("_", " ").title()


def date_label(value: date | datetime | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        value = value.date()
    if not hasattr(value, "strftime"):
        return str(value)
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def csv_rows(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    import csv
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
