from __future__ import annotations

from app.campaign_ops.ui.navigation import clear_all_specialized_state
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import can_access_admin

VIEWER_OPTIONS = ["Bailey", "T", "L"]

BAILEY_SECTIONS = [
    "Cross-Team",
    "All Programs",
    "My Work",
    "Influencer",
    "Retail Media",
    "eCommerce / Content",
    "Requests",
    "Insights",
    "Administration",
]

TEAM_MEMBER_SECTIONS = [
    "My Work",
    "My Programs",
    "Influencer",
    "Retail Media",
    "eCommerce / Content",
    "Requests",
    "Insights",
]

SESSION_KEYS = {
    "campaign_ops_viewer",
    "campaign_ops_viewer_id",
    "campaign_ops_previous_viewer",
    "campaign_ops_section",
    "campaign_ops_selected_program_id",
    "campaign_ops_program_filters",
    "campaign_ops_my_program_filters",
    "campaign_ops_program_view_mode",
    "campaign_ops_create_program_open",
    "campaign_ops_last_refresh",
    "campaign_ops_initialization_message",
    "campaign_ops_initialization_error",
    "campaign_ops_initialization_result",
    "campaign_ops_styles_applied",
    "campaign_ops_workspace_tab",
    "campaign_ops_milestone_create_open",
    "campaign_ops_milestone_edit_id",
    "campaign_ops_milestone_filters",
    "campaign_ops_milestone_show_inactive",
    "campaign_ops_milestone_complete_id",
    "campaign_ops_milestone_reopen_id",
    "campaign_ops_resource_create_open",
    "campaign_ops_resource_edit_id",
    "campaign_ops_resource_filters",
    "campaign_ops_resource_show_inactive",
    "campaign_ops_note_create_open",
    "campaign_ops_note_filters",
    "campaign_ops_note_sort_order",
    "campaign_ops_requests_view",
    "campaign_ops_selected_request_id",
    "campaign_ops_request_filters",
    "campaign_ops_request_create_open",
    "campaign_ops_request_edit_id",
    "campaign_ops_request_show_inactive",
    "campaign_ops_insights_view",
    "campaign_ops_selected_insights_project_id",
    "campaign_ops_insights_filters",
    "campaign_ops_insights_create_open",
    "campaign_ops_insights_edit_open",
    "campaign_ops_insights_timeline_edit_id",
    "campaign_ops_insights_objective_edit_id",
    "campaign_ops_insights_show_inactive",
    "campaign_ops_retail_media_view",
    "campaign_ops_selected_retail_media_campaign_id",
    "campaign_ops_retail_media_filters",
    "campaign_ops_retail_media_create_open",
    "campaign_ops_retail_media_edit_open",
    "campaign_ops_retail_media_channel_edit_id",
    "campaign_ops_retail_media_activation_edit_id",
    "campaign_ops_retail_media_creative_edit_id",
    "campaign_ops_retail_media_optimization_edit_id",
    "campaign_ops_retail_media_show_inactive",
    "campaign_ops_content_view",
    "campaign_ops_selected_content_program_id",
    "campaign_ops_content_filters",
    "campaign_ops_content_create_open",
    "campaign_ops_content_edit_open",
    "campaign_ops_content_sku_group_edit_id",
    "campaign_ops_content_sku_edit_id",
    "campaign_ops_content_deliverable_edit_id",
    "campaign_ops_content_submission_edit_id",
    "campaign_ops_content_monitoring_edit_id",
    "campaign_ops_content_invoice_edit_id",
    "campaign_ops_content_show_inactive",
    "campaign_ops_influencer_view",
    "campaign_ops_influencer_planning_view",
    "campaign_ops_influencer_planning_manager_filter",
    "campaign_ops_selected_influencer_campaign_id",
    "campaign_ops_influencer_filters",
    "campaign_ops_influencer_create_open",
    "campaign_ops_influencer_edit_open",
    "campaign_ops_influencer_step_edit_id",
    "campaign_ops_influencer_approval_edit_id",
    "campaign_ops_influencer_content_round_edit_id",
    "campaign_ops_influencer_show_inactive",
    "campaign_ops_influencer_live_view",
    "campaign_ops_influencer_live_manager_filter",
    "campaign_ops_selected_influencer_live_campaign_id",
    "campaign_ops_influencer_live_filters",
    "campaign_ops_influencer_live_checkpoint_edit_id",
    "campaign_ops_influencer_wave_edit_id",
    "campaign_ops_influencer_live_creator_edit_id",
    "campaign_ops_influencer_exception_edit_id",
    "campaign_ops_influencer_live_show_inactive",
    "campaign_ops_influencer_recap_view",
    "campaign_ops_influencer_recap_manager_filter",
    "campaign_ops_selected_influencer_recap_campaign_id",
    "campaign_ops_influencer_recap_filters",
    "campaign_ops_influencer_recap_checkpoint_edit_id",
    "campaign_ops_influencer_recap_requirement_edit_id",
    "campaign_ops_influencer_recap_launch_item_edit_id",
    "campaign_ops_influencer_recap_show_inactive",
    "campaign_ops_cross_team_filters",
    "campaign_ops_cross_team_person_view",
    "campaign_ops_cross_team_include_test_records",
    "campaign_ops_cross_team_upcoming_days",
    "campaign_ops_cross_team_attention_filter",
    "campaign_ops_cross_team_waiting_filter",
    "campaign_ops_cross_team_workflow_filter",
    "campaign_ops_cross_team_selected_program_id",
    "campaign_ops_cross_team_last_refresh",
    "campaign_ops_cross_team_program_view_mode",
    "campaign_ops_cross_team_owner",
    "campaign_ops_cross_team_assigned",
    "campaign_ops_cross_team_client",
    "campaign_ops_cross_team_program",
    "campaign_ops_cross_team_primary_workflow",
    "campaign_ops_cross_team_connected_workstream",
    "campaign_ops_cross_team_influencer_stage",
    "campaign_ops_cross_team_cross_stage",
    "campaign_ops_cross_team_status",
    "campaign_ops_cross_team_risk",
    "campaign_ops_cross_team_waiting_on",
    "campaign_ops_cross_team_active_state",
    "campaign_ops_cross_team_search",
    "campaign_ops_cross_team_needs_only",
    "campaign_ops_cross_team_start_from",
    "campaign_ops_cross_team_target_to",
    "campaign_ops_cross_team_refresh",
    "campaign_ops_cross_team_clear",
    "campaign_ops_cross_team_open_my_work",
    "campaign_ops_cross_team_open_my_programs",
    "campaign_ops_cross_team_open_program_select",
    "campaign_ops_cross_team_open_program",
    "campaign_ops_cross_team_export_csv",
}


def get_sections_for_user(user: CampaignOpsUser | None, viewer: str) -> list[str]:
    return BAILEY_SECTIONS if can_access_admin(user) or viewer == "Bailey" else TEAM_MEMBER_SECTIONS


def get_default_section(user: CampaignOpsUser | None, viewer: str) -> str:
    return "Cross-Team" if can_access_admin(user) or viewer == "Bailey" else "My Programs"


def selected_program_key() -> str:
    return "campaign_ops_selected_program_id"


def clear_selected_program(session_state: dict[str, object]) -> None:
    session_state.pop(selected_program_key(), None)


def update_viewer_state(
    session_state: dict[str, object],
    viewer: str,
    user: CampaignOpsUser | None,
) -> None:
    previous_viewer = session_state.get("campaign_ops_previous_viewer")
    sections = get_sections_for_user(user, viewer)
    if previous_viewer != viewer:
        clear_selected_program(session_state)
        clear_all_specialized_state(session_state)
        session_state.pop("campaign_ops_cross_team_selected_program_id", None)
        session_state["campaign_ops_previous_viewer"] = viewer
    if session_state.get("campaign_ops_section") not in sections:
        session_state["campaign_ops_section"] = get_default_section(user, viewer)
    if user is not None:
        session_state["campaign_ops_viewer_id"] = user.id
    else:
        session_state.pop("campaign_ops_viewer_id", None)


def set_section(session_state: dict[str, object], section: str) -> None:
    session_state["campaign_ops_section"] = section


def set_selected_program(session_state: dict[str, object], program_id: str) -> None:
    session_state[selected_program_key()] = program_id


def get_selected_program_id(session_state: dict[str, object]) -> str | None:
    value = session_state.get(selected_program_key())
    return str(value) if value else None
