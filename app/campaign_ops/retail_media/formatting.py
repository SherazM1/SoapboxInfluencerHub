from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.campaign_ops.formatting import RISK_LABELS, format_date, format_datetime, safe_text, title_label

PORTFOLIO_COLUMNS = [
    "Campaign",
    "Client",
    "Program",
    "Owner",
    "Channel Mix",
    "Status",
    "Latest Update",
    "Next Action / Milestone",
    "Launch Date",
    "Wrap Date",
    "Budget",
    "Spend to Date",
    "Tracksheet",
    "Budget Tracker",
    "Optimization Log",
    "Risk",
    "Paused State",
    "Updated Date",
    "Active State",
]


def retail_status_label(value: str | None) -> str:
    return title_label(value)


def currency(value: float | Decimal | None) -> str:
    if value is None:
        return "-"
    return f"${float(value):,.0f}"


def percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}%"


def link_state(url: str | None) -> str:
    return "Available" if url else "Missing"


def channel_mix_label(values: list[str] | tuple[str, ...] | None) -> str:
    return ", ".join(values) if values else "-"


def milestone_label(title: str | None, milestone_date: Any | None) -> str:
    if not title:
        return "-"
    return f"{format_date(milestone_date)} | {title}" if milestone_date else title


def portfolio_rows(campaigns: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "Campaign": campaign.campaign_title,
            "Client": safe_text(campaign.client_name),
            "Program": campaign.program_name,
            "Owner": safe_text(campaign.owner_display_name),
            "Channel Mix": channel_mix_label(campaign.channel_mix),
            "Status": retail_status_label(campaign.retail_media_status),
            "Latest Update": safe_text(campaign.latest_update),
            "Next Action / Milestone": milestone_label(campaign.next_milestone, campaign.next_milestone_date),
            "Launch Date": format_date(campaign.launch_date),
            "Wrap Date": format_date(campaign.wrap_date),
            "Budget": currency(campaign.overall_budget if campaign.overall_budget is not None else campaign.channel_budget_total),
            "Spend to Date": currency(campaign.total_spend if campaign.total_spend is not None else campaign.channel_spend_total),
            "Tracksheet": link_state(campaign.tracksheet_url),
            "Budget Tracker": link_state(campaign.budget_tracker_url),
            "Optimization Log": link_state(campaign.optimization_log_url),
            "Risk": RISK_LABELS.get(campaign.program_risk, title_label(campaign.program_risk)),
            "Paused State": f"Paused: {campaign.pause_reason}" if campaign.is_paused else "Active",
            "Updated Date": format_datetime(campaign.updated_at),
            "Active State": "Active" if campaign.is_active else "Inactive",
        }
        for campaign in campaigns
    ]
