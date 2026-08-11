from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.campaign_ops.formatting import safe_text, title_label
from app.campaign_ops.influencer.planning_baseline import QuickLink, compact_date

RECAP_QUICK_LINK_FIELDS = [
    ("Track Sheet", "track_sheet_url"),
    ("Influencer Brief", "influencer_brief_url"),
    ("Click2Cart Link", "click2cart_link_url"),
    ("Bitly Link", "bitly_link_url"),
    ("Invoice", "invoice_url"),
    ("EOP Survey", "eop_survey_url"),
    ("Live Content Tracker", "live_content_tracker_url"),
    ("Recap Deck", "recap_deck_url"),
    ("Final Performance Data", "final_performance_data_url"),
    ("Sales Lift Analysis", "sales_lift_analysis_url"),
]

RECAP_RESOURCE_ORDER = {
    "Track Sheet": 1,
    "Influencer Brief": 2,
    "Click2Cart Link": 3,
    "Bitly Link": 4,
    "Invoice": 5,
    "EOP Survey": 6,
    "Client-Facing Influencer Review": 7,
    "Live Content Tracker": 8,
    "Recap Deck": 9,
    "Results Deck": 9,
    "Client Recap Deck": 9,
    "Final Performance Data": 10,
    "Sales Lift Analysis": 11,
    "Product Link": 12,
    "Retailer Link": 12,
    "Custom": 13,
}

RECAP_RESOURCE_TYPES = tuple(RECAP_RESOURCE_ORDER)


@dataclass(frozen=True, slots=True)
class RecapLaunchGroup:
    group_name: str | None
    items: list[Any]


def select_recap_campaign_for_open(session_state: dict[str, Any], campaign_id: str) -> None:
    session_state["campaign_ops_selected_influencer_recap_campaign_id"] = campaign_id


def recap_quick_links(campaign: Any, resources: list[Any] | None = None, launch_items: list[Any] | None = None) -> list[QuickLink]:
    links: list[tuple[int, QuickLink]] = []
    seen: set[tuple[str, str]] = set()

    def add(order: int, label: str, url: str | None) -> None:
        cleaned = str(url).strip() if url is not None else ""
        cleaned_label = label.strip()
        if not cleaned or not cleaned_label:
            return
        key = (cleaned_label.lower(), cleaned)
        if key in seen:
            return
        seen.add(key)
        links.append((order, QuickLink(cleaned_label, cleaned)))

    for order, (label, attr) in enumerate(RECAP_QUICK_LINK_FIELDS, start=1):
        add(order, label, getattr(campaign, attr, None))

    for resource in resources or []:
        if not getattr(resource, "is_active", True):
            continue
        resource_type = safe_text(getattr(resource, "resource_type", "")).strip()
        if resource_type not in RECAP_RESOURCE_ORDER:
            continue
        title = safe_text(getattr(resource, "title", "")).strip()
        label = title if resource_type == "Custom" and title else resource_type or title
        add(RECAP_RESOURCE_ORDER[resource_type], label, getattr(resource, "url", None))

    for item in launch_items or []:
        if not getattr(item, "is_active", True):
            continue
        product_name = safe_text(getattr(item, "product_name", "")).strip()
        retailer_name = safe_text(getattr(item, "retailer_name", "")).strip()
        add(RECAP_RESOURCE_ORDER["Product Link"], product_name or "Product Link", getattr(item, "product_url", None))
        add(RECAP_RESOURCE_ORDER["Retailer Link"], retailer_name or "Retailer Link", getattr(item, "retailer_url", None))

    return [link for _, link in sorted(links, key=lambda item: (item[0], item[1].label.lower()))]


def group_recap_launch_items(items: list[Any]) -> list[RecapLaunchGroup]:
    groups: dict[str | None, list[Any]] = {}
    for item in items:
        if not getattr(item, "is_active", True):
            continue
        raw_group = getattr(item, "group_name", None)
        key = str(raw_group).strip() if raw_group is not None else None
        key = key or None
        groups.setdefault(key, []).append(item)
    return [RecapLaunchGroup(group, grouped) for group, grouped in groups.items()]


def all_influencers_live_state(campaign: Any) -> tuple[str, str]:
    total = int(getattr(campaign, "total_creator_count", 0) or 0)
    live = int(getattr(campaign, "live_creator_count", 0) or 0)
    if total > 0 and live >= total:
        return "Complete", f"{live} / {total} live"
    return "In Progress", f"{live} / {total} live"


def closeout_status_items(campaign: Any) -> list[tuple[str, str, str]]:
    live_state, live_subtext = all_influencers_live_state(campaign)
    sales_value = "Not Required" if not getattr(campaign, "sales_lift_analysis_required", False) else title_label(getattr(campaign, "sales_lift_analysis_status", None))
    return [
        ("Open Requirements", f"{int(getattr(campaign, 'open_requirement_count', 0) or 0)} Open", "Primary Closeout"),
        ("Creator Closeout", safe_text(getattr(campaign, "creator_closeout_status", None)) or creator_closeout_fallback(campaign), "Primary Closeout"),
        ("Invoice", invoice_status_text(campaign), "Primary Closeout"),
        ("Financial Close", safe_text(getattr(campaign, "financial_close_status", None)), "Primary Closeout"),
        ("EOP Survey", safe_text(getattr(campaign, "eop_survey_status", None)), "Reporting"),
        ("Recap Deck", safe_text(getattr(campaign, "recap_deck_status", None)), "Reporting"),
        ("Sales Lift", sales_value, "Reporting"),
        ("All Influencers Live", f"{live_state} - {live_subtext}", "Lifecycle"),
    ]


def creator_closeout_fallback(campaign: Any) -> str:
    completed = int(getattr(campaign, "completed_creator_count", 0) or 0)
    total = int(getattr(campaign, "total_creator_count", 0) or 0)
    return f"{completed} / {total} complete"


def invoice_status_text(campaign: Any) -> str:
    status = safe_text(getattr(campaign, "invoice_status", None))
    invoice_date = compact_date(getattr(campaign, "invoice_date", None))
    return f"{status} {invoice_date}".strip()


def ready_to_close_blockers(campaign: Any) -> list[str]:
    blockers: list[str] = []
    if int(getattr(campaign, "open_exception_count", 0) or 0) > 0:
        blockers.append(f"{int(getattr(campaign, 'open_exception_count', 0) or 0)} unresolved exception(s)")
    if int(getattr(campaign, "open_checkpoint_count", 0) or 0) > 0:
        blockers.append(f"{int(getattr(campaign, 'open_checkpoint_count', 0) or 0)} open checkpoint(s)")
    if int(getattr(campaign, "open_requirement_count", 0) or 0) > 0:
        blockers.append(f"{int(getattr(campaign, 'open_requirement_count', 0) or 0)} open requirement(s)")
    if int(getattr(campaign, "paid_live_incomplete_count", 0) or 0) > 0:
        blockers.append("Paid-live incomplete")
    if int(getattr(campaign, "missing_final_links_count", 0) or 0) > 0:
        blockers.append("Missing final links")
    if int(getattr(campaign, "missing_final_impressions_count", 0) or 0) > 0:
        blockers.append("Missing final impressions")
    return blockers[:3]
