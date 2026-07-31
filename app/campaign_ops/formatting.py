from __future__ import annotations

from datetime import date, datetime
from typing import Any

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
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d")


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


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
