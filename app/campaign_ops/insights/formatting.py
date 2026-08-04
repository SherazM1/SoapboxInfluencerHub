from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.campaign_ops.formatting import RISK_LABELS, format_date, format_datetime, safe_text, title_label

if TYPE_CHECKING:
    from core.campaign_ops.models import InsightsPortfolioRow, MilestoneListRow

PORTFOLIO_COLUMNS = [
    "Project",
    "Client",
    "Owner",
    "Status",
    "Latest Update",
    "Next Milestone",
    "Tracksheet",
    "Results Deck",
    "Raw Data",
    "Risk",
    "Updated",
    "Active State",
]


def insights_status_label(value: str | None) -> str:
    return title_label(value)


def format_currency(value: float | Decimal | None) -> str:
    if value is None:
        return "-"
    return f"${float(value):,.0f}"


def quick_link_label(url: str | None) -> str:
    return "Available" if url else "Missing"


def portfolio_rows(projects: list[InsightsPortfolioRow]) -> list[dict[str, str]]:
    return [
        {
            "Project": project.project_title,
            "Client": safe_text(project.client_name),
            "Owner": safe_text(project.owner_display_name),
            "Status": insights_status_label(project.insights_status),
            "Latest Update": safe_text(project.latest_update),
            "Next Milestone": milestone_summary(project.next_milestone, project.next_milestone_date),
            "Tracksheet": quick_link_label(project.tracksheet_url),
            "Results Deck": quick_link_label(project.results_deck_url),
            "Raw Data": quick_link_label(project.raw_data_url),
            "Risk": RISK_LABELS.get(project.program_risk, title_label(project.program_risk)),
            "Updated": format_datetime(project.updated_at),
            "Active State": "Active" if project.is_active else "Inactive",
        }
        for project in projects
    ]


def milestone_summary(title: str | None, milestone_date: object | None) -> str:
    if not title:
        return "-"
    return f"{format_date(milestone_date)} | {title}" if milestone_date else title


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
