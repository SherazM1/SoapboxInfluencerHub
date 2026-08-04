from __future__ import annotations

from typing import Any

from app.campaign_ops.formatting import RISK_LABELS, format_date, format_datetime, safe_text, title_label

PORTFOLIO_COLUMNS = [
    "Content Program",
    "Client",
    "Shared Program",
    "Owner",
    "Status",
    "Latest Update",
    "Total SKUs",
    "SKU Groups",
    "Graphics per SKU",
    "Delivered / Completed Counts",
    "Published / Live Counts",
    "Issues",
    "Waiting On",
    "Next Action / Milestone",
    "Maintenance End Date",
    "Tracksheet",
    "SKU List",
    "Creative Request Deck",
    "PDP Request Deck",
    "Keyword Insights",
    "Photography",
    "Risk",
    "Updated Date",
    "Active State",
]


def content_status_label(value: str | None) -> str:
    return title_label(value)


def link_state(url: str | None) -> str:
    return "Available" if url else "Missing"


def portfolio_rows(programs: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "Content Program": program.content_program_title,
            "Client": safe_text(program.client_name),
            "Shared Program": program.program_name,
            "Owner": safe_text(program.owner_display_name),
            "Status": content_status_label(program.content_status),
            "Latest Update": safe_text(program.latest_update),
            "Total SKUs": safe_text(program.total_sku_count or program.active_sku_count),
            "SKU Groups": ", ".join(program.group_names) if program.group_names else "-",
            "Graphics per SKU": safe_text(program.default_graphics_per_sku),
            "Delivered / Completed Counts": str(program.delivered_count),
            "Published / Live Counts": str(program.live_count),
            "Issues": str(program.issue_count),
            "Waiting On": safe_text(program.waiting_on),
            "Next Action / Milestone": f"{format_date(program.next_milestone_date)} | {program.next_milestone}" if program.next_milestone else "-",
            "Maintenance End Date": format_date(program.maintenance_end_date),
            "Tracksheet": link_state(program.tracksheet_url),
            "SKU List": link_state(program.sku_list_url),
            "Creative Request Deck": link_state(program.creative_request_deck_url),
            "PDP Request Deck": link_state(program.pdp_request_deck_url),
            "Keyword Insights": link_state(program.keyword_insights_url),
            "Photography": link_state(program.photography_url),
            "Risk": RISK_LABELS.get(program.program_risk, title_label(program.program_risk)),
            "Updated Date": format_datetime(program.updated_at),
            "Active State": "Active" if program.is_active else "Inactive",
        }
        for program in programs
    ]
