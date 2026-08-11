from __future__ import annotations

from typing import Any

from app.campaign_ops.formatting import RISK_LABELS, format_date, format_datetime, safe_text, title_label

PORTFOLIO_COLUMNS = [
    "Influencer Campaign",
    "Client",
    "Shared Program",
    "Manager",
    "Planning Status",
    "Latest Update",
    "Waiting On",
    "Hold State",
    "Hold Reason",
    "Next Planning Step",
    "Next Due Date",
    "Launch Date",
    "Wrap Date",
    "Target Creators",
    "Approved Creators",
    "Contracted Creators",
    "Invoice Date",
    "Invoice Status",
    "Invoice Amount",
    "Track Sheet",
    "Influencer Brief",
    "Bitly Link",
    "Invoice",
    "EOP Survey",
    "Influencer Education",
    "Campaign Brief",
    "Risk",
    "Updated Date",
    "Active State",
]


def status_label(value: str | None) -> str:
    return title_label(value)


def link_state(url: str | None) -> str:
    return "Available" if url else "Missing"


def planning_portfolio_rows(campaigns: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "Influencer Campaign": campaign.campaign_title,
            "Client": safe_text(campaign.client_name),
            "Shared Program": campaign.program_name,
            "Manager": safe_text(campaign.manager_display_name),
            "Planning Status": status_label(campaign.planning_status),
            "Latest Update": safe_text(campaign.latest_update),
            "Waiting On": safe_text(campaign.waiting_on),
            "Hold State": "ON HOLD" if campaign.is_on_hold else "Active",
            "Hold Reason": safe_text(campaign.hold_reason),
            "Next Planning Step": safe_text(campaign.next_planning_step),
            "Next Due Date": format_date(campaign.next_planning_step_due_date),
            "Launch Date": format_date(campaign.launch_date),
            "Wrap Date": format_date(campaign.wrap_date),
            "Target Creators": safe_text(campaign.target_creator_count),
            "Approved Creators": safe_text(campaign.approved_creator_count),
            "Contracted Creators": safe_text(campaign.contracted_creator_count),
            "Invoice Date": format_date(campaign.invoice_date),
            "Invoice Status": safe_text(campaign.invoice_status),
            "Invoice Amount": safe_text(campaign.invoice_amount),
            "Track Sheet": link_state(campaign.track_sheet_url),
            "Influencer Brief": link_state(campaign.influencer_brief_url),
            "Bitly Link": link_state(campaign.bitly_link_url),
            "Invoice": link_state(campaign.invoice_url),
            "EOP Survey": link_state(campaign.eop_survey_url),
            "Influencer Education": link_state(campaign.influencer_education_url),
            "Campaign Brief": link_state(campaign.campaign_brief_url),
            "Risk": RISK_LABELS.get(campaign.program_risk, status_label(campaign.program_risk)),
            "Updated Date": format_datetime(campaign.updated_at),
            "Active State": "Active" if campaign.is_active else "Inactive",
        }
        for campaign in campaigns
    ]
