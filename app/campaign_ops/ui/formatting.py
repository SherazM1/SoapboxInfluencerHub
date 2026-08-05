from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse


EMPTY_VALUE = "Not set"


def readable_label(value: Any, empty: str = EMPTY_VALUE) -> str:
    if value is None or value == "":
        return empty
    return str(value).replace("_", " ").replace("/", " / ").strip().title()


def format_display_date(value: date | datetime | None, empty: str = EMPTY_VALUE) -> str:
    if value is None:
        return empty
    if isinstance(value, datetime):
        value = value.date()
    return f"{value.strftime('%b')} {value.day}, {value.year}"


def format_display_datetime(value: datetime | None, empty: str = EMPTY_VALUE) -> str:
    if value is None:
        return empty
    return f"{value.strftime('%b')} {value.day}, {value.year} {value.strftime('%I:%M %p').lstrip('0')}"


def format_currency(value: int | float | Decimal | None, empty: str = EMPTY_VALUE) -> str:
    if value is None:
        return empty
    return f"${float(value):,.2f}"


def format_boolean(value: bool | None, true_label: str = "Yes", false_label: str = "No") -> str:
    if value is None:
        return EMPTY_VALUE
    return true_label if value else false_label


def is_test_record(title: str | None) -> bool:
    return bool(title and title.strip().upper().startswith("TEST -"))


def display_record_title(title: str | None) -> str:
    value = str(title or EMPTY_VALUE)
    return f"{value} [Test]" if is_test_record(value) else value


def safe_link_label(url: str | None, label: str = "Open Link") -> str:
    if not url:
        return "No Link"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "Invalid Link"
    return label

