from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st

from app.campaign_ops.formatting import ROLE_LABELS
from app.campaign_ops.state import get_sections_for_user, set_section
from core.campaign_ops.db import CampaignOpsSetupStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.migrations import initialize_campaign_ops_database
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import can_access_admin


@dataclass(frozen=True, slots=True)
class InitializationDisplaySummary:
    initialized_status: str
    applied_migrations: list[str]
    skipped_migrations: list[str]
    seeded_users: list[str]
    verified_users: list[str]


def read_result_field(source: Any, field_name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(field_name)
    return getattr(source, field_name, None)


def normalize_summary_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def format_initialization_result(
    result: Any,
    setup_status: CampaignOpsSetupStatus | None = None,
) -> InitializationDisplaySummary:
    migrations = read_result_field(result, "migrations")
    seed = read_result_field(result, "seed")
    verified_source = (
        read_result_field(seed, "verified_users")
        or read_result_field(result, "verified_users")
        or read_result_field(result, "verified")
    )
    return InitializationDisplaySummary(
        initialized_status=str(
            read_result_field(result, "initialized_status")
            or read_result_field(result, "status")
            or read_result_field(result, "message")
            or (setup_status.message if setup_status is not None else None)
            or "Campaign Operations database is initialized."
        ),
        applied_migrations=normalize_summary_list(
            read_result_field(migrations, "applied_migrations")
            or read_result_field(result, "applied_migrations")
            or read_result_field(result, "applied")
        ),
        skipped_migrations=normalize_summary_list(
            read_result_field(migrations, "skipped_migrations")
            or read_result_field(result, "skipped_migrations")
            or read_result_field(result, "skipped")
            or read_result_field(result, "already_applied_migrations")
        ),
        seeded_users=normalize_summary_list(
            read_result_field(result, "seeded_users")
            or read_result_field(result, "seeded")
            or (read_result_field(seed, "seeded_users") if not verified_source else None)
        ),
        verified_users=normalize_summary_list(verified_source),
    )


def render_summary_list(label: str, values: list[str], empty_text: str) -> None:
    st.markdown(f"**{label}:**")
    if values:
        for value in values:
            st.markdown(f"- {value}")
    else:
        st.markdown(f"- {empty_text}")


def render_initialization_message() -> None:
    raw_message = st.session_state.pop("campaign_ops_initialization_message", None)
    if not raw_message:
        return
    summary = (
        raw_message
        if isinstance(raw_message, InitializationDisplaySummary)
        else format_initialization_result(raw_message)
    )
    st.success(summary.initialized_status)
    render_summary_list(
        "Applied migrations",
        summary.applied_migrations,
        "None; all migrations were already applied",
    )
    render_summary_list("Already applied migrations", summary.skipped_migrations, "None")
    if summary.seeded_users:
        render_summary_list("Seeded users", summary.seeded_users, "None")
    render_summary_list("Verified users", summary.verified_users, "None reported")


def render_database_setup(
    user: CampaignOpsUser | None,
    setup_status: CampaignOpsSetupStatus,
) -> None:
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
        show_details = st.checkbox(
            "Show migration details after maintenance run",
            key="campaign_ops_show_setup_details",
        )
        if st.button("Initialize Campaign Operations Database", type="secondary"):
            try:
                result = initialize_campaign_ops_database()
            except CampaignOpsError as exc:
                st.session_state.pop("campaign_ops_initialization_message", None)
                st.session_state["campaign_ops_initialization_error"] = str(exc)
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
        if show_details:
            st.caption(setup_status.message)


def render_role_caption(user: CampaignOpsUser | None) -> None:
    if user is None:
        return
    st.caption(f"Role: {ROLE_LABELS.get(user.role, user.role)}")


def render_section_navigation(user: CampaignOpsUser | None, viewer: str) -> str:
    sections = get_sections_for_user(user, viewer)
    active_section = st.session_state.get("campaign_ops_section", sections[0])
    st.subheader("Workspace Areas")
    columns = st.columns(4)
    for index, section in enumerate(sections):
        with columns[index % 4]:
            if st.button(
                section,
                type="primary" if section == active_section else "secondary",
                use_container_width=True,
            ):
                set_section(st.session_state, section)
                active_section = section
    return str(active_section)


def render_placeholder(section: str) -> None:
    st.subheader(section)
    st.info("This Campaign Operations area is reserved for a later implementation pass.")
