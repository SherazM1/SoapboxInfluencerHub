from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.campaign_ops.formatting import title_label

if TYPE_CHECKING:
    from core.campaign_ops.models import MilestoneListRow


def insights_status_label(value: str | None) -> str:
    return title_label(value)


def timeline_date_label(milestone: MilestoneListRow | Any) -> str:
    if milestone.target_date and not milestone.start_date and not milestone.end_date:
        return f"{milestone.target_date.month}/{milestone.target_date.day}"
    if milestone.start_date and milestone.end_date:
        return f"{milestone.start_date.month}/{milestone.start_date.day} - {milestone.end_date.month}/{milestone.end_date.day}"
    if milestone.target_date:
        return f"{milestone.target_date.month}/{milestone.target_date.day}"
    if milestone.start_date:
        return f"{milestone.start_date.month}/{milestone.start_date.day}"
    if milestone.end_date:
        return f"{milestone.end_date.month}/{milestone.end_date.day}"
    return "-"
