from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.campaign_ops.formatting import safe_text, title_label
from app.campaign_ops.influencer.planning_baseline import compact_date
from core.campaign_ops.enums import TaskStatus


@dataclass(frozen=True, slots=True)
class ContentActionRow:
    source: str
    source_id: str
    group_id: str | None
    group_name: str
    display_date: date | None
    action: str
    status: str
    waiting_on: str | None = None
    note: str | None = None
    complete: bool = False
    source_order: int = 0


def normalize_content_actions(
    *,
    groups: list[Any],
    deliverables: list[Any],
    submissions: list[Any],
    monitoring_updates: list[Any],
    milestones: list[Any],
) -> list[ContentActionRow]:
    group_names = {str(getattr(group, "id", "")): safe_text(getattr(group, "group_name", "")).strip() for group in groups}
    rows: list[ContentActionRow] = []

    for deliverable in deliverables:
        if not getattr(deliverable, "is_active", True):
            continue
        status = deliverable_status(deliverable)
        rows.append(ContentActionRow(
            source="Deliverable",
            source_id=str(getattr(deliverable, "id", "")),
            group_id=_clean_id(getattr(deliverable, "sku_group_id", None)),
            group_name=_group_name(getattr(deliverable, "sku_group_id", None), group_names),
            display_date=getattr(deliverable, "due_date", None) or getattr(deliverable, "delivered_date", None) or getattr(deliverable, "approved_date", None),
            action=safe_text(getattr(deliverable, "deliverable_name", "")),
            status=status,
            waiting_on=getattr(deliverable, "waiting_on", None),
            note=deliverable_note(deliverable),
            complete=status in {"Delivered", "Approved", "Complete"},
            source_order=10,
        ))

    for submission in submissions:
        if not getattr(submission, "is_active", True):
            continue
        status = submission_status(submission)
        action = " | ".join(part for part in [safe_text(getattr(submission, "retailer_or_platform", "")), safe_text(getattr(submission, "submission_type", ""))] if part)
        rows.append(ContentActionRow(
            source="Submission",
            source_id=str(getattr(submission, "id", "")),
            group_id=_clean_id(getattr(submission, "sku_group_id", None)),
            group_name=_group_name(getattr(submission, "sku_group_id", None), group_names),
            display_date=getattr(submission, "expected_live_date", None) or getattr(submission, "submitted_date", None) or getattr(submission, "approved_date", None) or getattr(submission, "published_date", None),
            action=action or "Submission",
            status=status,
            waiting_on=getattr(submission, "waiting_on", None),
            note=submission_note(submission),
            complete=status in {"Submitted", "Approved", "Published", "Complete"},
            source_order=20,
        ))

    for update in monitoring_updates:
        if not getattr(update, "is_active", True):
            continue
        rows.append(ContentActionRow(
            source="Monitoring",
            source_id=str(getattr(update, "id", "")),
            group_id=_clean_id(getattr(update, "sku_group_id", None)),
            group_name=_group_name(getattr(update, "sku_group_id", None), group_names),
            display_date=getattr(update, "update_date", None),
            action=safe_text(getattr(update, "update_text", "")),
            status=title_label(getattr(update, "publication_state", None)) if getattr(update, "publication_state", None) else "Update",
            note=safe_text(getattr(update, "update_type", "")) or None,
            complete=True,
            source_order=30,
        ))

    for milestone in milestones:
        if not getattr(milestone, "is_active", True):
            continue
        status = milestone_status(milestone)
        rows.append(ContentActionRow(
            source="Milestone",
            source_id=str(getattr(milestone, "id", "")),
            group_id=None,
            group_name="General",
            display_date=getattr(milestone, "target_date", None) or getattr(milestone, "start_date", None) or getattr(milestone, "end_date", None),
            action=safe_text(getattr(milestone, "title", "")),
            status=status,
            complete=status == "Complete",
            source_order=40,
        ))

    return sorted([row for row in rows if row.action], key=content_action_sort_key)


def next_current_action(rows: list[ContentActionRow], fallback_title: str | None = None, fallback_date: date | None = None) -> ContentActionRow | None:
    candidates = sorted([row for row in rows if _has_waiting(row) or not row.complete], key=current_action_sort_key)
    if candidates:
        return candidates[0]
    if fallback_title:
        return ContentActionRow("Milestone", "fallback", None, "General", fallback_date, fallback_title, "Upcoming", source_order=99)
    completed = sorted(rows, key=current_action_sort_key)
    if completed:
        return completed[0]
    return None


def content_action_sort_key(row: ContentActionRow) -> tuple[bool, date, int, str]:
    return (row.display_date is None, row.display_date or date.max, row.source_order, row.action.lower())


def current_action_sort_key(row: ContentActionRow) -> tuple[int, bool, date, int, str]:
    waiting = _has_waiting(row)
    active = not row.complete
    if waiting:
        rank = 0
    elif active:
        rank = 1
    else:
        rank = 2
    return (rank, row.display_date is None, row.display_date or date.max, row.source_order, row.action.lower())


def deliverable_status(deliverable: Any) -> str:
    status = safe_text(getattr(deliverable, "status", "")).lower()
    approval = safe_text(getattr(deliverable, "approval_status", "")).lower()
    if approval == "approved" or status == "approved" or getattr(deliverable, "approved_date", None):
        return "Approved"
    if status == "delivered" or getattr(deliverable, "delivered_date", None):
        return "Delivered"
    if "waiting" in status or safe_text(getattr(deliverable, "waiting_on", "")):
        return "Waiting"
    if status in {"in_progress", "drafting", "review"}:
        return "In Progress"
    if status in {"complete", "completed"}:
        return "Complete"
    return title_label(status) or "Not Started"


def deliverable_note(deliverable: Any) -> str | None:
    raw_notes = getattr(deliverable, "notes", None)
    explicit = str(raw_notes).strip() if raw_notes is not None else ""
    if explicit:
        return explicit
    if getattr(deliverable, "approved_date", None):
        return f"Approved {compact_date(getattr(deliverable, 'approved_date', None))}"
    if getattr(deliverable, "delivered_date", None):
        return f"Delivered {compact_date(getattr(deliverable, 'delivered_date', None))}"
    return None


def submission_status(submission: Any) -> str:
    status = safe_text(getattr(submission, "status", "")).lower()
    if status in {"live", "published"} or getattr(submission, "published_date", None):
        return "Published"
    if status == "approved" or getattr(submission, "approved_date", None):
        return "Approved"
    if status == "submitted" or getattr(submission, "submitted_date", None):
        return "Submitted"
    if "waiting" in status or safe_text(getattr(submission, "waiting_on", "")):
        return "Waiting"
    if status in {"issue_found", "rejected", "resubmission_required"}:
        return title_label(status)
    return title_label(status) or "Not Started"


def submission_note(submission: Any) -> str | None:
    raw_issue = getattr(submission, "issue_text", None)
    issue = str(raw_issue).strip() if raw_issue is not None else ""
    if issue:
        return issue
    if getattr(submission, "live_url", None):
        return "Live URL available"
    return None


def milestone_status(milestone: Any) -> str:
    status = safe_text(getattr(milestone, "status", "")).lower()
    if status == TaskStatus.COMPLETED.value or getattr(milestone, "completed_at", None):
        return "Complete"
    if "waiting" in status:
        return "Waiting"
    if status == TaskStatus.IN_PROGRESS.value:
        return "In Progress"
    return title_label(status) or "Upcoming"


def action_display_text(row: ContentActionRow) -> str:
    prefix = f"{compact_date(row.display_date)} | " if row.display_date else ""
    return f"{prefix}{row.action}"


def _has_waiting(row: ContentActionRow) -> bool:
    waiting_text = str(row.waiting_on).strip() if row.waiting_on is not None else ""
    return bool(waiting_text) or row.status == "Waiting"


def _clean_id(value: Any) -> str | None:
    cleaned = str(value).strip() if value is not None else ""
    return cleaned or None


def _group_name(group_id: Any, group_names: dict[str, str]) -> str:
    cleaned = _clean_id(group_id)
    return group_names.get(cleaned or "", "General") if cleaned else "General"
