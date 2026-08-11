from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.campaign_ops.formatting import safe_text, title_label
from app.campaign_ops.influencer.planning_baseline import QuickLink, compact_date

LIVE_QUICK_LINK_FIELDS = [
    ("Track Sheet", "track_sheet_url"),
    ("Influencer Brief", "influencer_brief_url"),
    ("Click2Cart Link", "click2cart_link_url"),
    ("Client-Facing Live Doc", "client_facing_live_doc_url"),
    ("Daily Impressions", "daily_impressions_url"),
    ("Invoice", "invoice_url"),
    ("EOP Survey", "eop_survey_url"),
]

LIVE_RESOURCE_ORDER = {
    "Walmart Link": 4,
    "Retailer Link": 4,
    "Influencer Education": 9,
    "Client Guidelines": 10,
    "Custom": 11,
}

TERMINAL_MARKERS = ("campaign wrap", "campaign wraps", "ready for recap", "wrap review")


@dataclass(frozen=True, slots=True)
class LiveOperationalRow:
    source: str
    source_id: str
    display_date: date | None
    source_order: int
    action: str
    status: str
    waiting_on: str | None = None
    terminal: bool = False


def live_quick_links(campaign: Any, resources: list[Any] | None = None) -> list[QuickLink]:
    links: list[tuple[int, QuickLink]] = []
    seen: set[tuple[str, str]] = set()

    def add(order: int, label: str, url: str | None) -> None:
        cleaned = str(url).strip() if url is not None else ""
        if not cleaned:
            return
        key = (label.strip().lower(), cleaned)
        if key in seen:
            return
        seen.add(key)
        links.append((order, QuickLink(label.strip(), cleaned)))

    for order, (label, attr) in enumerate(LIVE_QUICK_LINK_FIELDS, start=1):
        add(order, label, getattr(campaign, attr, None))

    for resource in resources or []:
        if not getattr(resource, "is_active", True):
            continue
        resource_type = safe_text(getattr(resource, "resource_type", "")).strip()
        title = safe_text(getattr(resource, "title", "")).strip()
        label = title if resource_type == "Custom" and title else resource_type or title
        order = LIVE_RESOURCE_ORDER.get(resource_type)
        if order is not None or resource_type in {"Click2Cart Link", "Walmart Link", "Retailer Link"}:
            add(order or 4, label, getattr(resource, "url", None))

    return [link for _, link in sorted(links, key=lambda item: (item[0], item[1].label.lower()))]


def compose_live_operational_sequence(planning_steps: list[Any], checkpoints: list[Any], waves: list[Any]) -> list[LiveOperationalRow]:
    rows: list[LiveOperationalRow] = []
    for step in planning_steps:
        if not getattr(step, "is_active", True):
            continue
        title = safe_text(getattr(step, "step_title", ""))
        rows.append(
            LiveOperationalRow(
                source="Planning",
                source_id=str(getattr(step, "id", "")),
                display_date=getattr(step, "due_date", None) or getattr(step, "start_date", None),
                source_order=int(getattr(step, "sequence_order", 0) or 0),
                action=title,
                status=completion_label(getattr(step, "status", None), getattr(step, "completed_date", None)),
                waiting_on=getattr(step, "waiting_on", None),
                terminal=_is_terminal(title),
            )
        )
    for checkpoint in checkpoints:
        if not getattr(checkpoint, "is_active", True):
            continue
        title = safe_text(getattr(checkpoint, "checkpoint_title", ""))
        rows.append(
            LiveOperationalRow(
                source="Checkpoint",
                source_id=str(getattr(checkpoint, "id", "")),
                display_date=getattr(checkpoint, "due_date", None) or getattr(checkpoint, "start_date", None),
                source_order=int(getattr(checkpoint, "sequence_order", 0) or 0),
                action=title,
                status=completion_label(getattr(checkpoint, "status", None), getattr(checkpoint, "completed_date", None)),
                waiting_on=getattr(checkpoint, "waiting_on", None),
                terminal=_is_terminal(title),
            )
        )
    for wave in waves:
        if not getattr(wave, "is_active", True):
            continue
        name = safe_text(getattr(wave, "wave_name", "")).strip()
        number = int(getattr(wave, "wave_number", 0) or 0)
        title = name or f"Wave {number} creators go live"
        rows.append(
            LiveOperationalRow(
                source="Wave",
                source_id=str(getattr(wave, "id", "")),
                display_date=getattr(wave, "planned_start_date", None) or getattr(wave, "actual_start_date", None),
                source_order=number,
                action=title,
                status=wave_status_label(wave),
                waiting_on=getattr(wave, "waiting_on", None),
                terminal=_is_terminal(title),
            )
        )
    return _dedupe_exact_rows(_sort_live_rows(rows))


def smart_live_sequence_preview(rows: list[LiveOperationalRow], *, today: date | None = None, upcoming_limit: int = 4, compact: bool = False) -> list[LiveOperationalRow]:
    if not rows:
        return []
    threshold = 6 if compact else 8
    if len(rows) <= threshold:
        return rows
    today = today or date.today()
    selected: dict[tuple[str, str], LiveOperationalRow] = {}

    def include(row: LiveOperationalRow) -> None:
        selected[(row.source, row.source_id)] = row

    completed = [row for row in rows if row.status == "Complete"]
    if completed:
        include(completed[-1])
    for row in rows:
        if row.status == "Waiting":
            include(row)
        if row.display_date and row.display_date < today and row.status != "Complete":
            include(row)
    upcoming = [row for row in rows if row.status != "Complete"]
    for row in upcoming[:upcoming_limit]:
        include(row)
    terminal = next((row for row in reversed(rows) if row.terminal), None)
    if terminal:
        include(terminal)
    return [row for row in rows if (row.source, row.source_id) in selected]


def select_live_campaign_for_open(session_state: dict[str, Any], campaign_id: str) -> None:
    session_state["campaign_ops_selected_influencer_live_campaign_id"] = campaign_id


def next_go_live_text(value: date | None, *, all_live: bool) -> str:
    if value:
        return compact_date(value, reference_year=date.today().year)
    return "All scheduled creators are live" if all_live else ""


def completion_label(status: str | None, completed_date: date | None = None) -> str:
    if completed_date is not None or safe_text(status).lower() == "complete":
        return "Complete"
    cleaned = safe_text(status).lower()
    if "waiting" in cleaned:
        return "Waiting"
    if cleaned in {"in_progress", "reopened", "resubmission"}:
        return "In Progress"
    if cleaned in {"cancelled"}:
        return "Cancelled"
    return "Not Started"


def wave_status_label(wave: Any) -> str:
    status = safe_text(getattr(wave, "status", "")).lower()
    if status == "complete" or getattr(wave, "actual_end_date", None) is not None:
        return "Complete"
    if status in {"in_progress", "live", "reopened"} or getattr(wave, "actual_start_date", None) is not None:
        return "In Progress"
    if "waiting" in status:
        return "Waiting"
    if status == "cancelled":
        return "Cancelled"
    return "Upcoming" if getattr(wave, "planned_start_date", None) else "Not Started"


def _sort_live_rows(rows: list[LiveOperationalRow]) -> list[LiveOperationalRow]:
    source_rank = {"Planning": 0, "Checkpoint": 1, "Wave": 2}
    return sorted(
        rows,
        key=lambda row: (
            row.display_date is None,
            row.display_date or date.max,
            source_rank.get(row.source, 9),
            row.source_order,
            row.action.lower(),
        ),
    )


def _dedupe_exact_rows(rows: list[LiveOperationalRow]) -> list[LiveOperationalRow]:
    seen: set[tuple[str, date | None]] = set()
    result: list[LiveOperationalRow] = []
    for row in rows:
        key = (row.action.strip().lower(), row.display_date)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _is_terminal(title: str) -> bool:
    cleaned = title.lower()
    return any(marker in cleaned for marker in TERMINAL_MARKERS)
