from __future__ import annotations

from typing import Any

from app.campaign_ops.formatting import format_date, format_datetime, safe_text, title_label

RECAP_COLUMNS = [
    "Campaign",
    "Client",
    "Shared Program",
    "Manager",
    "Recap Status",
    "Latest Update",
    "Waiting On",
    "All Creators Live",
    "Creator Closeout",
    "EOP Survey",
    "Final Performance Data",
    "Sales Lift Analysis",
    "Recap Deck",
    "Client Recap Date",
    "Invoice State",
    "Financial Close",
    "Open Requirements",
    "Product / Retailer Launch Items",
    "Track Sheet",
    "Influencer Brief",
    "Click2Cart / Bitly",
    "Invoice",
    "EOP Survey Link",
    "Live Content Tracker",
    "Risk",
    "Updated Date",
    "Active State",
]


def link_state(url: str | None) -> str:
    return "Available" if url else "No Link"


def recap_rows(campaigns: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "Campaign": c.campaign_title,
            "Client": safe_text(c.client_name),
            "Shared Program": c.program_name,
            "Manager": safe_text(c.manager_display_name),
            "Recap Status": title_label(c.recap_status),
            "Latest Update": safe_text(c.latest_update),
            "Waiting On": safe_text(c.waiting_on),
            "All Creators Live": "TRUE" if c.all_creators_live else "FALSE",
            "Creator Closeout": safe_text(c.creator_closeout_status),
            "EOP Survey": safe_text(c.eop_survey_status),
            "Final Performance Data": safe_text(c.final_performance_data_status),
            "Sales Lift Analysis": safe_text(c.sales_lift_analysis_status),
            "Recap Deck": safe_text(c.recap_deck_status),
            "Client Recap Date": format_date(c.client_recap_date),
            "Invoice State": safe_text(c.invoice_status),
            "Financial Close": safe_text(c.financial_close_status),
            "Open Requirements": str(c.open_requirement_count),
            "Product / Retailer Launch Items": str(c.launch_item_count),
            "Track Sheet": link_state(c.track_sheet_url),
            "Influencer Brief": link_state(c.influencer_brief_url),
            "Click2Cart / Bitly": "Available" if c.click2cart_link_url or c.bitly_link_url else "No Link",
            "Invoice": link_state(c.invoice_url),
            "EOP Survey Link": link_state(c.eop_survey_url),
            "Live Content Tracker": link_state(c.live_content_tracker_url),
            "Risk": title_label(c.program_risk),
            "Updated Date": format_datetime(c.updated_at),
            "Active State": "Active" if c.is_active else "Inactive",
        }
        for c in campaigns
    ]
