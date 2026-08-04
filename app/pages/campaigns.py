from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.campaign_ops.components import (
    format_initialization_result,
    render_database_setup,
    render_initialization_message,
    render_placeholder,
    render_role_caption,
    render_section_navigation,
)
from app.campaign_ops.program_forms import render_new_program_form
from app.campaign_ops.program_list import render_all_programs, render_my_programs
from app.campaign_ops.program_workspace import render_program_workspace
from app.campaign_ops.content_management.views import render_content_management
from app.campaign_ops.insights.views import render_insights
from app.campaign_ops.retail_media.views import render_retail_media
from app.campaign_ops.reporting_requests.views import render_reporting_requests
from app.campaign_ops.personal_views import render_my_work
from app.campaign_ops.state import (
    VIEWER_OPTIONS,
    get_default_section,
    get_selected_program_id,
    get_sections_for_user,
    set_section,
    update_viewer_state,
)
from app.navigation import (
    clear_legacy_workflow_session_state,
    hide_default_streamlit_sidebar_nav,
)
from core.campaign_ops.db import CampaignOpsSetupStatus, get_campaign_ops_setup_status
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.migrations import initialize_campaign_ops_database
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService

ROLE_LABELS = {
    "administrator": "Administrator",
    "team_member": "Team Member",
    "viewer": "Viewer",
}


def render_header() -> None:
    st.title("Campaign Operations")
    st.markdown(
        "Manage persisted programs, workstreams, team assignments, requests, and "
        "cross-team progress from one workspace."
    )


def resolve_viewer_user(viewer: str) -> tuple[CampaignOpsUser | None, str | None]:
    try:
        return CampaignOpsRepository().get_user_by_display_name(viewer), None
    except CampaignOpsError as exc:
        return None, str(exc)


def get_viewer_role(viewer: str, user: CampaignOpsUser | None = None) -> str:
    if user is not None:
        return ROLE_LABELS.get(user.role, user.role)
    return "Administrator" if viewer == "Bailey" else "Team Member"


def resolve_initialized_viewer(viewer: str) -> CampaignOpsUser | None:
    user, setup_error = resolve_viewer_user(viewer)
    if setup_error:
        st.warning("Campaign Operations user lookup failed. Ask Bailey to verify database setup.")
        return None
    if user is not None:
        st.session_state["campaign_ops_viewer_id"] = user.id
    else:
        st.session_state.pop("campaign_ops_viewer_id", None)
    render_role_caption(user)
    if user is None:
        st.warning(f"{viewer} is not available in Campaign Operations users.")
    return user


def viewer_can_initialize_in_setup(viewer: str) -> bool:
    return viewer == "Bailey"


def render_initialization_control(
    viewer: str,
    user: CampaignOpsUser | None,
    setup_status: CampaignOpsSetupStatus,
) -> None:
    if user is None and viewer == "Bailey":
        user = CampaignOpsUser(
            id="00000000-0000-4000-8000-000000000000",
            display_name="Bailey",
            role="administrator",
        )
    if not can_access_admin(user):
        return
    with st.expander("Database Setup", expanded=False):
        if setup_status.is_initialized:
            st.success("Campaign Operations database is initialized.")
        else:
            st.warning(setup_status.message)
        st.caption(
            "DB config: "
            f"CAMPAIGN_OPS_DATABASE_URL detected={setup_status.database_url_detected}; "
            f"connection succeeded={setup_status.connection_succeeded}; "
            f"schema initialized={setup_status.schema_initialized}"
        )
        if st.button("Initialize Campaign Operations Database", type="secondary"):
            try:
                result = initialize_campaign_ops_database()
            except CampaignOpsError as exc:
                st.session_state.pop("campaign_ops_initialization_message", None)
                st.session_state.pop("campaign_ops_initialization_result", None)
                st.error(f"Campaign Operations database initialization failed: {exc}")
                return
            st.session_state.pop("campaign_ops_initialization_error", None)
            st.session_state.pop("campaign_ops_initialization_result", None)
            st.session_state["campaign_ops_initialization_message"] = format_initialization_result(
                result,
                setup_status,
            )
            st.session_state.pop("campaign_ops_viewer_id", None)
            st.rerun()


def render_temporary_viewer_selector(user: CampaignOpsUser | None = None) -> str:
    viewer = st.selectbox("Viewing as", VIEWER_OPTIONS, key="campaign_ops_viewer")
    update_viewer_state(st.session_state, viewer, user)
    return viewer


def render_setup_state(viewer: str, setup_status: CampaignOpsSetupStatus) -> None:
    st.warning(setup_status.message)
    if not viewer_can_initialize_in_setup(viewer):
        st.info("Campaign Operations database setup has not been completed. Ask Bailey to initialize it.")
        st.stop()
    st.info("Bailey can initialize Campaign Operations database setup from this page.")
    render_initialization_control(viewer, None, setup_status)
    st.stop()


def render_cross_team_intro() -> None:
    st.subheader("Cross-Team")
    st.info("Cross-team dashboard metrics are planned for a later implementation pass.")
    if st.button("Open All Programs", type="primary", key="campaign_ops_open_all_programs"):
        set_section(st.session_state, "All Programs")
        st.rerun()


def render_active_section(
    section: str,
    viewer: str,
    user: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
) -> None:
    clients = service.list_active_clients()
    if section == "Cross-Team":
        render_cross_team_intro()
    elif section == "All Programs":
        render_all_programs(user, service, users, clients)
    elif section == "My Programs":
        render_my_programs(user, service, users, clients)
    elif section == "New Program":
        render_new_program_form(user, service, users, clients)
    elif section == "My Work":
        render_my_work(user, service, users)
    elif section == "Requests":
        render_reporting_requests(user, service, users)
    elif section == "Retail Media":
        render_retail_media(user, service, users)
    elif section == "eCommerce / Content":
        render_content_management(user, service, users)
    elif section == "Insights":
        render_insights(user, service, users)
    else:
        render_placeholder(section)


def main() -> None:
    st.set_page_config(page_title="Campaign Operations", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()
    clear_legacy_workflow_session_state()

    render_header()
    st.divider()
    render_initialization_message()

    setup_status = get_campaign_ops_setup_status()
    if not setup_status.is_initialized:
        viewer = render_temporary_viewer_selector(None)
        render_setup_state(viewer, setup_status)

    viewer = st.selectbox("Viewing as", VIEWER_OPTIONS, key="campaign_ops_viewer")
    user = resolve_initialized_viewer(viewer)
    if user is None:
        st.stop()
        return

    update_viewer_state(st.session_state, viewer, user)
    render_database_setup(user, setup_status)

    service = CampaignOpsService()
    try:
        users = service.list_active_users()
    except CampaignOpsError as exc:
        st.error(f"Unable to load Campaign Operations users: {exc}")
        users = [user]

    selected_program_id = get_selected_program_id(st.session_state)
    if selected_program_id:
        render_program_workspace(user, service, selected_program_id)
        return

    sections = get_sections_for_user(user, viewer)
    current_section = st.session_state.get(
        "campaign_ops_section",
        get_default_section(user, viewer),
    )
    if current_section not in sections and current_section != "New Program":
        current_section = get_default_section(user, viewer)
        set_section(st.session_state, current_section)
    if current_section == "New Program" and not can_access_admin(user):
        current_section = get_default_section(user, viewer)
        set_section(st.session_state, current_section)

    st.divider()
    if current_section != "New Program":
        current_section = render_section_navigation(user, viewer)
    else:
        if st.button("Back to All Programs", key="campaign_ops_back_from_new_program"):
            set_section(st.session_state, "All Programs")
            st.rerun()
    st.divider()
    render_active_section(current_section, viewer, user, service, users)


if __name__ == "__main__":
    main()
