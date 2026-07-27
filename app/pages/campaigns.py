from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.navigation import (
    clear_legacy_workflow_session_state,
    hide_default_streamlit_sidebar_nav,
)
from core.campaign_ops.enums import UserRole
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.db import get_campaign_ops_database_status
from core.campaign_ops.migrations import initialize_campaign_ops_database
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.repository import CampaignOpsRepository

VIEWER_OPTIONS = ["Bailey", "T", "L"]
BAILEY_SECTIONS = [
    "Cross-Team Dashboard",
    "All Programs",
    "Influencer",
    "Retail Media",
    "eCommerce / Content",
    "Requests",
    "Administration",
]
TEAM_MEMBER_SECTIONS = [
    "My Work",
    "My Programs",
    "Influencer",
    "Retail Media",
    "eCommerce / Content",
    "Requests",
]
PROGRAM_WORKSPACES = [
    "Influencer Programs",
    "Retail Media Programs",
    "eCommerce / Content Programs",
]
ROLE_LABELS = {
    UserRole.ADMINISTRATOR.value: "Administrator",
    UserRole.TEAM_MEMBER.value: "Team Member",
    UserRole.VIEWER.value: "Viewer",
}


def render_header() -> None:
    """Render module workspace header and orientation."""
    st.title("Campaign Operations")
    st.markdown(
        "Manage programs, workstreams, team assignments, deadlines, resources, and "
        "cross-team progress from one workspace."
    )


def get_viewer_role(viewer: str, user: CampaignOpsUser | None = None) -> str:
    """Return temporary role label for the selected viewer."""
    if user is not None:
        return ROLE_LABELS.get(user.role, user.role)
    return "Administrator" if viewer == "Bailey" else "Team Member"


def get_sections_for_viewer(viewer: str) -> list[str]:
    """Return shell sections available to a temporary viewer."""
    return BAILEY_SECTIONS if viewer == "Bailey" else TEAM_MEMBER_SECTIONS


def get_default_section(viewer: str) -> str:
    """Return the default landing section for a temporary viewer."""
    return "Cross-Team Dashboard" if viewer == "Bailey" else "My Work"


def resolve_viewer_user(viewer: str) -> tuple[CampaignOpsUser | None, str | None]:
    """Resolve a temporary viewer against seeded Campaign Operations users."""
    try:
        return CampaignOpsRepository().get_user_by_display_name(viewer), None
    except CampaignOpsError as exc:
        return None, str(exc)


def render_viewer_selector() -> tuple[str, str, CampaignOpsUser | None]:
    """Render temporary viewer scaffolding until authentication exists."""
    previous_viewer = st.session_state.get("campaign_ops_previous_viewer")
    viewer = st.selectbox("Viewing as", VIEWER_OPTIONS, key="campaign_ops_viewer")
    user, setup_error = resolve_viewer_user(viewer)
    sections = get_sections_for_viewer(viewer)
    default_section = get_default_section(viewer)

    if (
        previous_viewer != viewer
        or st.session_state.get("campaign_ops_section") not in sections
    ):
        st.session_state["campaign_ops_section"] = default_section
        st.session_state["campaign_ops_previous_viewer"] = viewer

    if user is not None:
        st.session_state["campaign_ops_viewer_id"] = user.id
    else:
        st.session_state.pop("campaign_ops_viewer_id", None)

    st.caption(f"Role: {get_viewer_role(viewer, user)}")
    if setup_error:
        st.warning(
            "Campaign Operations database is not initialized or is unavailable. "
            "Use the Bailey setup control to initialize it when CAMPAIGN_OPS_DATABASE_URL "
            "is configured."
        )
    elif user is None:
        st.warning(
            f"{viewer} is not available in Campaign Operations users yet. "
            "Initialize the Campaign Operations database to seed internal users."
        )
    return viewer, st.session_state["campaign_ops_section"], user


def render_initialization_control(viewer: str, user: CampaignOpsUser | None) -> None:
    """Render Bailey-only database initialization control."""
    fallback_admin = viewer == "Bailey" and user is None
    if not (can_access_admin(user) or fallback_admin):
        return

    with st.expander("Database Setup", expanded=False):
        database_status = get_campaign_ops_database_status()
        st.caption(
            "Runs pending Campaign Operations migrations and idempotently seeds Bailey, T, and L."
        )
        st.caption(
            "DB config: "
            f"CAMPAIGN_OPS_DATABASE_URL detected={database_status['database_url_detected']}; "
            f"connection succeeded={database_status['connection_succeeded']}; "
            f"status={database_status['message']}"
        )
        if st.button("Initialize Campaign Operations Database", type="primary"):
            try:
                result = initialize_campaign_ops_database()
            except CampaignOpsError as exc:
                st.error(f"Campaign Operations database initialization failed: {exc}")
                return

            applied = result.migrations.applied_migrations or ["None"]
            skipped = result.migrations.skipped_migrations or ["None"]
            st.success("Campaign Operations database initialization completed.")
            st.markdown(f"- Applied migrations: {', '.join(applied)}")
            st.markdown(f"- Already applied migrations: {', '.join(skipped)}")
            st.markdown(f"- Seeded users: {', '.join(result.seed.seeded_users)}")


def set_active_section(section: str) -> None:
    """Persist selected Campaign Operations shell section."""
    st.session_state["campaign_ops_section"] = section


def render_section_navigation(viewer: str) -> str:
    """Render internal Campaign Operations section navigation."""
    sections = get_sections_for_viewer(viewer)
    active_section = st.session_state.get("campaign_ops_section", get_default_section(viewer))

    st.subheader("Workspace Areas")
    columns = st.columns(3)
    for index, section in enumerate(sections):
        with columns[index % 3]:
            button_type = "primary" if section == active_section else "secondary"
            if st.button(section, type=button_type, use_container_width=True):
                set_active_section(section)
                active_section = section

    return active_section


def render_summary_cards() -> None:
    """Render placeholder admin summary cards."""
    st.subheader("Overview")
    labels = ["Active Programs", "At Risk", "Overdue Tasks", "Waiting on Client"]
    columns = st.columns(4)
    for column, label in zip(columns, labels):
        column.metric(label, "Not configured")


def render_program_workspace_cards() -> None:
    """Render future program workspace cards."""
    st.subheader("Program Workspaces")
    columns = st.columns(3)
    for column, title in zip(columns, PROGRAM_WORKSPACES):
        with column:
            st.markdown(f"### {title}")
            st.caption(
                "Workspace foundation ready. Program data will be added in the next "
                "implementation pass."
            )


def render_personal_notice(viewer: str) -> None:
    """Render placeholder personal workload messaging."""
    st.info(f"This view will show programs, tasks, and deadlines assigned to {viewer}.")


def render_active_section(viewer: str, section: str) -> None:
    """Render the currently selected Campaign Operations shell section."""
    st.subheader(section)
    if viewer == "Bailey" and section == "Cross-Team Dashboard":
        render_summary_cards()
        st.divider()
        render_program_workspace_cards()
        return

    if viewer in {"T", "L"} and section == "My Work":
        render_personal_notice(viewer)
        return

    st.info(
        "Workspace foundation ready. Program data will be added in the next "
        "implementation pass."
    )


def main() -> None:
    """Render Campaign Operations module shell."""
    st.set_page_config(page_title="Campaign Operations", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()
    clear_legacy_workflow_session_state()

    render_header()
    st.divider()
    viewer, _, user = render_viewer_selector()
    render_initialization_control(viewer, user)
    st.divider()
    active_section = render_section_navigation(viewer)
    st.divider()
    render_active_section(viewer, active_section)


if __name__ == "__main__":
    main()
