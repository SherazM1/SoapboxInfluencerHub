from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


SPECIALIZED_SELECTION_KEYS = {
    "Influencer": {
        "campaign_ops_selected_influencer_campaign_id",
        "campaign_ops_selected_influencer_live_campaign_id",
        "campaign_ops_selected_influencer_recap_campaign_id",
    },
    "Retail Media": {"campaign_ops_selected_retail_media_campaign_id"},
    "eCommerce / Content": {"campaign_ops_selected_content_program_id"},
    "Insights": {"campaign_ops_selected_insights_project_id"},
    "Requests": {"campaign_ops_selected_request_id"},
}

EDITOR_KEYS = {
    "campaign_ops_request_edit_id",
    "campaign_ops_insights_timeline_edit_id",
    "campaign_ops_insights_objective_edit_id",
    "campaign_ops_retail_media_channel_edit_id",
    "campaign_ops_retail_media_activation_edit_id",
    "campaign_ops_retail_media_creative_edit_id",
    "campaign_ops_retail_media_optimization_edit_id",
    "campaign_ops_content_sku_group_edit_id",
    "campaign_ops_content_sku_edit_id",
    "campaign_ops_content_deliverable_edit_id",
    "campaign_ops_content_submission_edit_id",
    "campaign_ops_content_monitoring_edit_id",
    "campaign_ops_content_invoice_edit_id",
    "campaign_ops_influencer_step_edit_id",
    "campaign_ops_influencer_approval_edit_id",
    "campaign_ops_influencer_content_round_edit_id",
    "campaign_ops_influencer_live_checkpoint_edit_id",
    "campaign_ops_influencer_wave_edit_id",
    "campaign_ops_influencer_live_creator_edit_id",
    "campaign_ops_influencer_exception_edit_id",
    "campaign_ops_influencer_recap_checkpoint_edit_id",
    "campaign_ops_influencer_recap_requirement_edit_id",
    "campaign_ops_influencer_recap_launch_item_edit_id",
}


def clear_editor_state(session_state: MutableMapping[str, Any]) -> None:
    for key in EDITOR_KEYS:
        session_state.pop(key, None)


def clear_incompatible_specialized_state(
    session_state: MutableMapping[str, Any],
    active_module: str | None = None,
) -> None:
    keep = SPECIALIZED_SELECTION_KEYS.get(active_module or "", set())
    for module_keys in SPECIALIZED_SELECTION_KEYS.values():
        for key in module_keys:
            if key not in keep:
                session_state.pop(key, None)
    clear_editor_state(session_state)


def clear_all_specialized_state(session_state: MutableMapping[str, Any]) -> None:
    clear_incompatible_specialized_state(session_state, None)


def route_to_program_workspace(session_state: MutableMapping[str, Any], program_id: str) -> None:
    clear_all_specialized_state(session_state)
    session_state["campaign_ops_selected_program_id"] = program_id
    session_state["campaign_ops_section"] = "All Programs"


def route_to_specialized_workspace(
    session_state: MutableMapping[str, Any],
    section: str,
    program_id: str,
    record_id: str | None = None,
) -> None:
    clear_incompatible_specialized_state(session_state, section)
    session_state.pop("campaign_ops_selected_program_id", None)
    session_state["campaign_ops_section"] = section
    session_state["campaign_ops_cross_team_selected_program_id"] = program_id
    if not record_id:
        return
    if section == "Influencer":
        session_state["campaign_ops_selected_influencer_campaign_id"] = record_id
        session_state["campaign_ops_selected_influencer_live_campaign_id"] = record_id
        session_state["campaign_ops_selected_influencer_recap_campaign_id"] = record_id
    elif section == "Retail Media":
        session_state["campaign_ops_selected_retail_media_campaign_id"] = record_id
    elif section == "eCommerce / Content":
        session_state["campaign_ops_selected_content_program_id"] = record_id
    elif section == "Insights":
        session_state["campaign_ops_selected_insights_project_id"] = record_id
    elif section == "Requests":
        session_state["campaign_ops_selected_request_id"] = record_id


def return_to_portfolio(session_state: MutableMapping[str, Any], section: str) -> None:
    clear_incompatible_specialized_state(session_state, section)
    session_state.pop("campaign_ops_selected_program_id", None)
    session_state["campaign_ops_section"] = section

