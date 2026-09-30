from __future__ import annotations

from app.campaign_ops.ui.navigation import clear_all_specialized_state
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import can_access_admin

VIEWER_OPTIONS = ["Bailey"]

PROGRAM_SECTIONS = ["All Programs", "My Programs"]
WORKFLOW_SECTIONS = ["Influencer", "Retail Media", "eCommerce / Content", "Insights", "Social Media Management"]
BAILEY_SECTIONS = [*PROGRAM_SECTIONS, *WORKFLOW_SECTIONS]
TEAM_MEMBER_SECTIONS = [*PROGRAM_SECTIONS, *WORKFLOW_SECTIONS]

SESSION_KEYS = {
    "campaign_ops_viewer",
    "campaign_ops_viewer_id",
    "campaign_ops_previous_viewer",
    "campaign_ops_section",
    "campaign_ops_selected_program_id",
    "campaign_ops_program_filters",
    "campaign_ops_my_program_filters",
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
    "campaign_ops_note_create_open",
    "campaign_ops_note_filters",
    "campaign_ops_note_sort_order",
    "campaign_ops_insights_view",
    "campaign_ops_selected_insights_project_id",
    "campaign_ops_insights_filters",
    "campaign_ops_insights_create_open",
    "campaign_ops_insights_edit_open",
    "campaign_ops_insights_timeline_edit_id",
    "campaign_ops_insights_show_inactive",
    "campaign_ops_retail_media_view",
    "campaign_ops_selected_retail_media_campaign_id",
    "campaign_ops_retail_media_filters",
    "campaign_ops_retail_media_create_open",
    "campaign_ops_retail_media_edit_open",
    "campaign_ops_retail_media_activation_edit_id",
    "campaign_ops_retail_media_creative_edit_id",
    "campaign_ops_retail_media_show_inactive",
    "campaign_ops_content_view",
    "campaign_ops_selected_content_program_id",
    "campaign_ops_content_filters",
    "campaign_ops_content_create_open",
    "campaign_ops_content_edit_open",
    "campaign_ops_content_deliverable_edit_id",
    "campaign_ops_content_submission_edit_id",
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
    "campaign_ops_influencer_show_inactive",
    "campaign_ops_influencer_live_view",
    "campaign_ops_influencer_live_manager_filter",
    "campaign_ops_selected_influencer_live_campaign_id",
    "campaign_ops_influencer_live_filters",
    "campaign_ops_influencer_live_checkpoint_edit_id",
    "campaign_ops_influencer_wave_edit_id",
    "campaign_ops_influencer_exception_edit_id",
    "campaign_ops_influencer_live_show_inactive",
    "campaign_ops_influencer_recap_view",
    "campaign_ops_influencer_recap_manager_filter",
    "campaign_ops_selected_influencer_recap_campaign_id",
    "campaign_ops_influencer_recap_filters",
    "campaign_ops_influencer_recap_checkpoint_edit_id",
    "campaign_ops_influencer_recap_show_inactive",
}


def get_sections_for_user(user: CampaignOpsUser | None, viewer: str) -> list[str]:
    return BAILEY_SECTIONS if can_access_admin(user) or viewer == "Bailey" else TEAM_MEMBER_SECTIONS


def get_default_section(user: CampaignOpsUser | None, viewer: str) -> str:
    return "All Programs" if can_access_admin(user) or viewer == "Bailey" else "My Programs"


def selected_program_key() -> str:
    return "campaign_ops_selected_program_id"


def clear_selected_program(session_state: dict[str, object]) -> None:
    session_state.pop(selected_program_key(), None)


def update_viewer_state(
    session_state: dict[str, object],
    viewer: str,
    user: CampaignOpsUser | None,
) -> None:
    # Discard retired page state carried by an already-open browser session.
    for key in list(session_state):
        if key.startswith(("campaign_ops_cross_team_", "campaign_ops_request", "campaign_ops_my_work_")) or key == "campaign_ops_selected_request_id":
            session_state.pop(key, None)
    previous_viewer = session_state.get("campaign_ops_previous_viewer")
    sections = get_sections_for_user(user, viewer)
    if previous_viewer != viewer:
        clear_new_program_draft(session_state)
        clear_selected_program(session_state)
        clear_all_specialized_state(session_state)
        session_state["campaign_ops_previous_viewer"] = viewer
    if session_state.get("campaign_ops_section") not in sections and not (
        session_state.get("campaign_ops_section") == "New Program" and (user is None or can_access_admin(user))
    ):
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


def clear_new_program_draft(session_state: dict[str, object]) -> None:
    for key in list(session_state):
        if key.startswith("campaign_ops_new_program_") or key == "campaign_ops_primary_workflow":
            session_state.pop(key, None)
    session_state["campaign_ops_create_program_open"] = False


def cancel_new_program(session_state: dict[str, object]) -> None:
    clear_new_program_draft(session_state)
    set_section(session_state, "All Programs")


def finish_new_program(session_state: dict[str, object], program_id: str) -> None:
    # Widget keys can only be removed safely on the next render, before instantiation.
    session_state["campaign_ops_new_program_cleanup"] = True
    session_state["campaign_ops_create_program_open"] = False
    session_state["campaign_ops_program_created_message"] = "Program created."
    set_section(session_state, "All Programs")
    set_selected_program(session_state, program_id)


def begin_new_program(session_state: dict[str, object]) -> None:
    clear_new_program_draft(session_state)
    session_state["campaign_ops_create_program_open"] = True
    set_section(session_state, "New Program")
