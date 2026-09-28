from __future__ import annotations

from typing import Any


def select_recap_campaign_for_open(session_state: dict[str, Any], campaign_id: str) -> None:
    session_state["campaign_ops_selected_influencer_recap_campaign_id"] = campaign_id


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
