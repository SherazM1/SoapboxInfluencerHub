from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.campaign_ops.formatting import safe_text, title_label
from app.campaign_ops.influencer.planning_baseline import QuickLink, compact_date
from core.campaign_ops.enums import TaskStatus


@dataclass(frozen=True, slots=True)
class InsightsDeliverable:
    id: str
    title: str
    display_date: date | None
    status: str
    source_order: int = 0


def insights_quick_links(project: Any) -> list[QuickLink]:
    links: list[QuickLink] = []
    seen: set[tuple[str, str]] = set()
    for label, attr in (
        ("Tracksheet", "tracksheet_url"),
        ("Results Deck", "results_deck_url"),
        ("Raw Data Key", "raw_data_url"),
    ):
        url = str(getattr(project, attr, "") or "").strip()
        if not url:
            continue
        key = (label.lower(), url)
        if key in seen:
            continue
        seen.add(key)
        links.append(QuickLink(label, url))
    return links


def current_status_text(project: Any) -> str:
    latest = safe_text(getattr(project, "latest_update", "")).strip()
    if latest and latest != "-":
        return latest
    return title_label(getattr(project, "insights_status", None))


def normalize_insights_deliverables(milestones: list[Any], project: Any | None = None) -> list[InsightsDeliverable]:
    rows: list[InsightsDeliverable] = []
    for milestone in milestones:
        if not scoped_insights_milestone(milestone, project):
            continue
        if milestone_complete(milestone):
            continue
        rows.append(InsightsDeliverable(
            id=str(getattr(milestone, "id", "")),
            title=safe_text(getattr(milestone, "title", "")),
            display_date=getattr(milestone, "target_date", None) or getattr(milestone, "start_date", None) or getattr(milestone, "end_date", None),
            status=milestone_status(milestone),
            source_order=0 if getattr(milestone, "target_date", None) or getattr(milestone, "start_date", None) or getattr(milestone, "end_date", None) else 1,
        ))
    return sorted([row for row in rows if row.title and row.title != "-"], key=deliverable_sort_key)


def next_insights_deliverable(milestones: list[Any], project: Any | None = None) -> InsightsDeliverable | None:
    rows = normalize_insights_deliverables(milestones, project)
    return rows[0] if rows else None


def deliverable_display_text(deliverable: InsightsDeliverable | None) -> str:
    if deliverable is None:
        return "No open deliverable."
    prefix = f"{compact_date(deliverable.display_date)} | " if deliverable.display_date else ""
    return f"{prefix}{deliverable.title}"


def scoped_insights_milestone(milestone: Any, project: Any | None = None) -> bool:
    if not getattr(milestone, "is_active", True):
        return False
    if safe_text(getattr(milestone, "milestone_type", "")).strip() == "Insights":
        return True
    if project is None:
        return False
    milestone_workstream = str(getattr(milestone, "workstream_id", "") or "")
    project_workstream = str(getattr(project, "workstream_id", "") or "")
    return bool(milestone_workstream and project_workstream and milestone_workstream == project_workstream)


def milestone_complete(milestone: Any) -> bool:
    status = safe_text(getattr(milestone, "status", "")).lower()
    return status == TaskStatus.COMPLETED.value or getattr(milestone, "completed_at", None) is not None


def milestone_status(milestone: Any) -> str:
    status = safe_text(getattr(milestone, "status", "")).lower()
    if status == TaskStatus.COMPLETED.value or getattr(milestone, "completed_at", None):
        return "Complete"
    if status == TaskStatus.IN_PROGRESS.value:
        return "In Progress"
    if "blocked" in status or "waiting" in status:
        return title_label(status)
    return title_label(status) or "Open"


def deliverable_sort_key(row: InsightsDeliverable) -> tuple[bool, date, int, str]:
    return (row.display_date is None, row.display_date or date.max, row.source_order, row.title.lower())
