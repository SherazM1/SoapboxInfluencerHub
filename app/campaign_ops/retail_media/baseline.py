from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.campaign_ops.formatting import safe_text, title_label
from app.campaign_ops.influencer.planning_baseline import QuickLink, compact_date
from core.campaign_ops.enums import TaskStatus

RETAIL_MEDIA_LINK_ORDER = {
    "Program Tracksheet": 1,
    "Tracksheet": 2,
    "WPSR Weekly Update": 3,
    "Media Plan / Budget": 4,
    "Budget Tracker": 5,
    "RM Strategy": 6,
    "Optimization Log": 7,
    "Reporting Folder": 8,
    "Custom": 20,
}

RETAIL_MEDIA_MILESTONE_TYPE = "Retail Media"

@dataclass(frozen=True, slots=True)
class RetailMediaActionRow:
    source: str
    source_id: str
    display_date: date | None
    action: str
    status: str
    waiting_on: str | None = None
    note: str | None = None
    complete: bool = False
    hard_deadline: bool = False
    source_order: int = 0
    channel_id: str | None = None
    channel_label: str | None = None


def retail_media_quick_links(
    campaign: Any,
    resources: list[Any] | None = None,
    *,
    include_custom: bool = False,
) -> list[QuickLink]:
    links: list[tuple[int, QuickLink]] = []
    seen: set[tuple[str, str]] = set()

    def add(order: int, label: str, url: str | None) -> None:
        cleaned_url = str(url).strip() if url is not None else ""
        cleaned_label = label.strip()
        if not cleaned_label or not cleaned_url:
            return
        key = (cleaned_label.lower(), cleaned_url)
        if key in seen:
            return
        seen.add(key)
        links.append((order, QuickLink(cleaned_label, cleaned_url)))

    add(RETAIL_MEDIA_LINK_ORDER["Tracksheet"], "Tracksheet", getattr(campaign, "tracksheet_url", None))
    add(RETAIL_MEDIA_LINK_ORDER["Budget Tracker"], "Budget Tracker", getattr(campaign, "budget_tracker_url", None))
    add(RETAIL_MEDIA_LINK_ORDER["Optimization Log"], "Optimization Log", getattr(campaign, "optimization_log_url", None))

    for resource in resources or []:
        if not getattr(resource, "is_active", True):
            continue
        resource_type = safe_text(getattr(resource, "resource_type", "")).strip()
        title = safe_text(getattr(resource, "title", "")).strip()
        url = getattr(resource, "url", None)
        if resource_type == "Custom" and not include_custom and not _looks_like_retail_media_custom(title):
            continue
        order = RETAIL_MEDIA_LINK_ORDER.get(resource_type) or RETAIL_MEDIA_LINK_ORDER.get(title)
        if order is None and resource_type == "Custom":
            order = RETAIL_MEDIA_LINK_ORDER["Custom"]
        if order is None:
            continue
        label = title if resource_type == "Custom" and title else title or resource_type
        add(order, label, url)

    return [link for _, link in sorted(links, key=lambda item: (item[0], item[1].label.lower()))]


def normalize_retail_media_actions(
    *,
    activations: list[Any],
    creative: list[Any],
    optimizations: list[Any],
    milestones: list[Any],
    channels: list[Any] | None = None,
) -> list[RetailMediaActionRow]:
    channel_labels = {
        str(getattr(channel, "id", "")): safe_text(getattr(channel, "channel_type", "")).strip()
        for channel in channels or []
        if safe_text(getattr(channel, "id", "")).strip()
    }
    rows: list[RetailMediaActionRow] = []

    for activation in activations:
        if not getattr(activation, "is_active", True):
            continue
        status = activation_status(activation)
        channel_id = _clean_id(getattr(activation, "channel_id", None))
        rows.append(RetailMediaActionRow(
            source="Activation",
            source_id=str(getattr(activation, "id", "")),
            display_date=getattr(activation, "start_date", None) or getattr(activation, "end_date", None),
            action=safe_text(getattr(activation, "activation_name", "")),
            status=status,
            waiting_on=getattr(activation, "waiting_on", None),
            note=getattr(activation, "latest_update", None),
            complete=status == "Complete",
            hard_deadline=bool(getattr(activation, "hard_deadline", False)),
            source_order=10,
            channel_id=channel_id,
            channel_label=channel_labels.get(channel_id or ""),
        ))

    for item in creative:
        if not getattr(item, "is_active", True):
            continue
        status = creative_status(item)
        channel_id = _clean_id(getattr(item, "channel_id", None))
        rows.append(RetailMediaActionRow(
            source="Creative",
            source_id=str(getattr(item, "id", "")),
            display_date=getattr(item, "due_date", None) or getattr(item, "submitted_date", None) or getattr(item, "approved_date", None),
            action=creative_action_name(item),
            status=status,
            note=getattr(item, "notes", None),
            complete=status in {"Approved", "Submitted", "Live", "Accepted"},
            source_order=20,
            channel_id=channel_id,
            channel_label=channel_labels.get(channel_id or ""),
        ))

    for update in optimizations:
        if not getattr(update, "is_active", True):
            continue
        channel_id = _clean_id(getattr(update, "channel_id", None))
        update_type = safe_text(getattr(update, "optimization_type", "")).strip()
        rows.append(RetailMediaActionRow(
            source="Optimization",
            source_id=str(getattr(update, "id", "")),
            display_date=getattr(update, "update_date", None),
            action=safe_text(getattr(update, "update_text", "")),
            status="Update",
            note=update_type or None,
            complete=True,
            source_order=30,
            channel_id=channel_id,
            channel_label=channel_labels.get(channel_id or ""),
        ))

    for milestone in milestones:
        if not retail_media_scoped_milestone(milestone):
            continue
        status = milestone_status(milestone)
        rows.append(RetailMediaActionRow(
            source="Milestone",
            source_id=str(getattr(milestone, "id", "")),
            display_date=getattr(milestone, "target_date", None) or getattr(milestone, "start_date", None) or getattr(milestone, "end_date", None),
            action=safe_text(getattr(milestone, "title", "")),
            status=status,
            complete=status == "Complete",
            hard_deadline=bool(getattr(milestone, "hard_deadline", False)),
            source_order=40,
        ))

    return sorted([row for row in rows if row.action], key=retail_media_action_sort_key)


def next_current_retail_media_action(rows: list[RetailMediaActionRow], *, today: date | None = None) -> RetailMediaActionRow | None:
    today = today or date.today()
    waiting = sorted([row for row in rows if _has_waiting(row) and not row.complete], key=retail_media_current_action_sort_key(today))
    if waiting:
        return waiting[0]
    overdue = sorted([row for row in rows if row.display_date and row.display_date < today and not row.complete], key=retail_media_current_action_sort_key(today))
    if overdue:
        return overdue[0]
    upcoming = sorted([row for row in rows if row.display_date and row.display_date >= today and not row.complete], key=retail_media_current_action_sort_key(today))
    if upcoming:
        return upcoming[0]
    undated = sorted([row for row in rows if row.display_date is None and not row.complete], key=retail_media_current_action_sort_key(today))
    if undated:
        return undated[0]
    return None


def current_status_text(campaign: Any) -> str:
    status = retail_status_label(getattr(campaign, "retail_media_status", None))
    if getattr(campaign, "is_paused", False):
        reason = safe_text(getattr(campaign, "pause_reason", ""))
        return f"PAUSED | {reason}" if reason != "-" else "PAUSED"
    waiting = safe_text(getattr(campaign, "waiting_on", ""))
    if waiting != "-":
        return f"{status} | Waiting on {waiting}" if status else f"Waiting on {waiting}"
    return status


def action_display_text(row: RetailMediaActionRow) -> str:
    prefix = f"{compact_date(row.display_date)} | " if row.display_date else ""
    channel = f" | {row.channel_label}" if row.channel_label else ""
    return f"{prefix}{row.action}{channel}"


def spend_budget_values(campaign: Any) -> tuple[Any, Any]:
    budget = getattr(campaign, "overall_budget", None)
    spend = getattr(campaign, "total_spend", None)
    if budget is None:
        budget = getattr(campaign, "channel_budget_total", None)
    if spend is None:
        spend = getattr(campaign, "channel_spend_total", None)
    return budget, spend


def over_budget(campaign: Any) -> bool:
    budget, spend = spend_budget_values(campaign)
    return bool(budget and spend is not None and float(spend) > float(budget))


def retail_status_label(value: str | None) -> str:
    return title_label(value)


def activation_status(activation: Any) -> str:
    raw = safe_text(getattr(activation, "status", "")).lower()
    if getattr(activation, "completed_at", None) or raw in {"complete", "completed"}:
        return "Complete"
    if safe_text(getattr(activation, "waiting_on", "")) != "-" or "waiting" in raw:
        return "Waiting"
    if raw in {"live", "optimizing"}:
        return "Live"
    if raw in {"in_progress", "planning", "ready_to_launch"}:
        return "In Progress"
    return title_label(raw) or "Not Started"


def creative_status(item: Any) -> str:
    approval = safe_text(getattr(item, "approval_status", "")).lower()
    submission = safe_text(getattr(item, "submission_status", "")).lower()
    platform = safe_text(getattr(item, "platform_status", "")).lower()
    if approval == "approved" or getattr(item, "approved_date", None):
        return "Approved"
    if submission in {"submitted", "accepted"} or getattr(item, "submitted_date", None):
        return "Accepted" if submission == "accepted" else "Submitted"
    if platform == "live" or submission == "live":
        return "Live"
    if "review" in approval:
        return "In Review"
    if approval == "changes_requested":
        return "Changes Requested"
    if approval == "rejected" or submission == "rejected":
        return "Rejected"
    return title_label(approval or submission) or "Not Started"


def creative_action_name(item: Any) -> str:
    name = safe_text(getattr(item, "creative_name", "")).strip()
    ctype = safe_text(getattr(item, "creative_type", "")).strip()
    if ctype and ctype != "-":
        return f"{name} | {ctype}" if name and name != "-" else ctype
    return name


def milestone_status(milestone: Any) -> str:
    raw = safe_text(getattr(milestone, "status", "")).lower()
    if raw == TaskStatus.COMPLETED.value or getattr(milestone, "completed_at", None):
        return "Complete"
    if "waiting" in raw:
        return "Waiting"
    if raw == TaskStatus.IN_PROGRESS.value:
        return "In Progress"
    return title_label(raw) or "Upcoming"


def retail_media_scoped_milestone(milestone: Any) -> bool:
    return safe_text(getattr(milestone, "milestone_type", "")).strip() == RETAIL_MEDIA_MILESTONE_TYPE


def retail_media_action_sort_key(row: RetailMediaActionRow) -> tuple[bool, date, int, str]:
    return (row.display_date is None, row.display_date or date.max, row.source_order, row.action.lower())


def retail_media_current_action_sort_key(today: date):
    def key(row: RetailMediaActionRow) -> tuple[int, bool, date, int, str]:
        if _has_waiting(row) and not row.complete:
            rank = 0
        elif row.display_date and row.display_date < today and not row.complete:
            rank = 1
        elif row.display_date and not row.complete:
            rank = 2
        elif not row.complete:
            rank = 3
        else:
            rank = 4
        return (rank, row.display_date is None, row.display_date or date.max, row.source_order, row.action.lower())

    return key


def _has_waiting(row: RetailMediaActionRow) -> bool:
    waiting_text = str(row.waiting_on).strip() if row.waiting_on is not None else ""
    return bool(waiting_text) or row.status == "Waiting"


def _clean_id(value: Any) -> str | None:
    cleaned = str(value).strip() if value is not None else ""
    return cleaned or None


def _looks_like_retail_media_custom(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in ("tracksheet", "media", "wpsr", "budget", "strategy", "optimization", "reporting"))
