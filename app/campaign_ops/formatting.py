from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.campaign_ops.ui.formatting import (
    format_currency as format_display_currency,
    format_display_date,
    format_display_datetime,
)
from core.campaign_ops.enums import (
    AssignmentRole,
    CrossStage,
    ProgramStatus,
    RiskLevel,
    TaskStatus,
    UserRole,
    WorkstreamType,
)


def title_label(value: str | None) -> str:
    if not value:
        return "-"
    return str(value).replace("_", " ").replace("/", " / ").title()


def enum_options(enum_type: type) -> list[str]:
    return [item.value for item in enum_type]


def enum_label_map(enum_type: type) -> dict[str, str]:
    return {item.value: title_label(item.value) for item in enum_type}


def format_date(value: date | datetime | None) -> str:
    return format_display_date(value, empty="-")


def format_datetime(value: datetime | None) -> str:
    return format_display_datetime(value, empty="-")


def format_currency(value: float | int | None) -> str:
    return format_display_currency(value, empty="-")


def format_list(values: list[str] | tuple[str, ...] | None) -> str:
    if not values:
        return "-"
    return ", ".join(title_label(value) for value in values)


def safe_text(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


ROLE_LABELS = enum_label_map(UserRole)
WORKFLOW_LABELS = enum_label_map(WorkstreamType)
STATUS_LABELS = enum_label_map(ProgramStatus)
CROSS_STAGE_LABELS = enum_label_map(CrossStage)
RISK_LABELS = enum_label_map(RiskLevel)
TASK_STATUS_LABELS = enum_label_map(TaskStatus)
ASSIGNMENT_ROLE_LABELS = enum_label_map(AssignmentRole)
