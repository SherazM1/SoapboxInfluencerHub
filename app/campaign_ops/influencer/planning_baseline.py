from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.campaign_ops.formatting import safe_text

QUICK_LINK_ORDER = [
    ("Track Sheet", "track_sheet_url"),
    ("Influencer Brief", "influencer_brief_url"),
    ("Bitly Link", "bitly_link_url"),
    ("Click2Cart Link", "click2cart_link_url"),
    ("Invoice", "invoice_url"),
    ("EOP Survey", "eop_survey_url"),
    ("Influencer Education", "influencer_education_url"),
    ("Campaign Brief", "campaign_brief_url"),
]

TERMINAL_STEP_MARKERS = ("campaign wraps", "campaign wrap", "wraps")


@dataclass(frozen=True, slots=True)
class QuickLink:
    label: str
    url: str


def compact_date(value: date | None, *, reference_year: int | None = None) -> str:
    if value is None:
        return ""
    if reference_year is not None and value.year != reference_year:
        return f"{value.month}/{value.day}/{value.year}"
    return f"{value.month}/{value.day}"


def campaign_quick_links(campaign: Any) -> list[QuickLink]:
    links: list[QuickLink] = []
    for label, attr in QUICK_LINK_ORDER:
        raw_url = getattr(campaign, attr, None)
        url = str(raw_url).strip() if raw_url is not None else ""
        if url:
            links.append(QuickLink(label, url))
    return links


def active_planning_steps(steps: list[Any]) -> list[Any]:
    return [step for step in steps if getattr(step, "is_active", True)]


def incomplete_step(step: Any) -> bool:
    return getattr(step, "completed_date", None) is None and safe_text(getattr(step, "status", "")).lower() != "complete"


def next_sequence_step(steps: list[Any]) -> Any | None:
    return next((step for step in active_planning_steps(steps) if incomplete_step(step)), None)


def planning_sequence_preview(steps: list[Any], *, today: date | None = None, upcoming_limit: int = 4, compact: bool = False) -> list[Any]:
    active = active_planning_steps(steps)
    if not active:
        return []
    threshold = 6 if compact else 8
    if len(active) <= threshold:
        return active

    today = today or date.today()
    selected: dict[str, Any] = {}

    def include(step: Any) -> None:
        selected[str(getattr(step, "id", len(selected)))] = step

    completed = [step for step in active if getattr(step, "completed_date", None) is not None]
    if completed:
        include(completed[-1])

    for step in active:
        due = getattr(step, "due_date", None)
        status = safe_text(getattr(step, "status", "")).lower()
        if incomplete_step(step) and due is not None and due < today:
            include(step)
        if incomplete_step(step) and "waiting" in status:
            include(step)

    upcoming = [step for step in active if incomplete_step(step)]
    for step in upcoming[:upcoming_limit]:
        include(step)

    terminal = next((step for step in reversed(active) if _is_terminal_step(step)), None)
    if terminal is not None:
        include(terminal)

    selected_steps = set(selected)
    if selected_steps:
        first_index = next((index for index, step in enumerate(active) if str(getattr(step, "id", index)) in selected_steps), None)
        last_index = next((index for index in range(len(active) - 1, -1, -1) if str(getattr(active[index], "id", index)) in selected_steps), None)
        if first_index is not None and last_index is not None:
            for step in active[first_index : last_index + 1]:
                if getattr(step, "due_date", None) is None:
                    include(step)

    return [step for index, step in enumerate(active) if str(getattr(step, "id", index)) in selected]


def select_campaign_for_open(session_state: dict[str, Any], campaign_id: str) -> None:
    session_state["campaign_ops_selected_influencer_campaign_id"] = campaign_id


def _is_terminal_step(step: Any) -> bool:
    title = safe_text(getattr(step, "step_title", "")).lower()
    return any(marker in title for marker in TERMINAL_STEP_MARKERS)
