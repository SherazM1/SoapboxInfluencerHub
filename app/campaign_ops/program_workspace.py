from __future__ import annotations

import streamlit as st

from app.campaign_ops.formatting import (
    ASSIGNMENT_ROLE_LABELS,
    CROSS_STAGE_LABELS,
    RISK_LABELS,
    STATUS_LABELS,
    WORKFLOW_LABELS,
    format_date,
    format_datetime,
    safe_text,
)
from app.campaign_ops.state import clear_selected_program
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, ProgramAssignment, ProgramWorkspaceSummary
from core.campaign_ops.service import CampaignOpsService


def render_program_workspace(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    program_id: str,
) -> None:
    try:
        summary = service.get_program_workspace_summary(actor, program_id)
    except CampaignOpsError as exc:
        clear_selected_program(st.session_state)
        st.warning(f"Selected program is not available: {exc}")
        if st.button("Back to Programs", key="campaign_ops_workspace_back_after_error"):
            st.rerun()
        return

    if st.button("Back to Programs", key="campaign_ops_workspace_back"):
        clear_selected_program(st.session_state)
        st.rerun()

    render_workspace_header(summary)
    tabs = st.tabs(["Overview", "Workstreams", "Tasks", "Timeline", "Resources", "Notes", "Team", "Activity"])
    with tabs[0]:
        render_overview(summary)
    with tabs[1]:
        render_workstreams(summary)
    with tabs[2]:
        st.info("Task CRUD is planned for a later implementation pass.")
    with tabs[3]:
        st.info("Timeline and milestone management are planned for a later implementation pass.")
    with tabs[4]:
        st.info("Resource management is planned for a later implementation pass.")
    with tabs[5]:
        st.info("Notes are planned for a later implementation pass.")
    with tabs[6]:
        render_team(summary)
    with tabs[7]:
        render_activity(summary)


def render_workspace_header(summary: ProgramWorkspaceSummary) -> None:
    program = summary.program
    owner = primary_owner(summary.assignments, summary.users)
    st.subheader(program.program_name)
    st.caption(
        f"{safe_text(summary.client.name if summary.client else None)} | "
        f"{WORKFLOW_LABELS.get(program.primary_workstream_type or '', '-')} | "
        f"{'Active' if program.is_active else 'Archived'}"
    )
    cols = st.columns(4)
    cols[0].metric("Status", STATUS_LABELS.get(program.status, program.status))
    cols[1].metric("Cross stage", CROSS_STAGE_LABELS.get(program.cross_stage, program.cross_stage))
    cols[2].metric("Risk", RISK_LABELS.get(program.risk_level, program.risk_level))
    cols[3].metric("Primary owner", safe_text(owner))
    st.caption(
        f"Priority: {safe_text(program.priority)} | "
        f"Start: {format_date(program.start_date)} | "
        f"Target: {format_date(program.target_end_date)} | "
        f"Last updated: {format_datetime(program.updated_at)}"
    )
    st.caption(
        "Active workstreams: "
        + (
            ", ".join(
                WORKFLOW_LABELS.get(workstream.workstream_type, workstream.workstream_type)
                for workstream in summary.workstreams
                if workstream.is_active
            )
            or "-"
        )
    )


def primary_owner(assignments: list[ProgramAssignment], users: list[CampaignOpsUser]) -> str | None:
    users_by_id = {user.id: user.display_name for user in users}
    for assignment in assignments:
        if assignment.is_active and assignment.is_primary and assignment.assignment_role == "program_owner":
            return users_by_id.get(assignment.user_id)
    return None


def render_overview(summary: ProgramWorkspaceSummary) -> None:
    program = summary.program
    rows = [
        {"Field": "Program name", "Value": program.program_name},
        {"Field": "Client", "Value": safe_text(summary.client.name if summary.client else None)},
        {"Field": "Description", "Value": safe_text(program.description)},
        {
            "Field": "Primary workflow",
            "Value": WORKFLOW_LABELS.get(program.primary_workstream_type or "", "-"),
        },
        {"Field": "Program status", "Value": STATUS_LABELS.get(program.status, program.status)},
        {"Field": "Cross stage", "Value": CROSS_STAGE_LABELS.get(program.cross_stage, program.cross_stage)},
        {"Field": "Risk", "Value": RISK_LABELS.get(program.risk_level, program.risk_level)},
        {"Field": "Priority", "Value": safe_text(program.priority)},
        {"Field": "Start date", "Value": format_date(program.start_date)},
        {"Field": "Target end date", "Value": format_date(program.target_end_date)},
        {"Field": "Last updated", "Value": format_datetime(program.updated_at)},
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def render_workstreams(summary: ProgramWorkspaceSummary) -> None:
    users_by_id = {user.id: user.display_name for user in summary.users}
    rows = [
        {
            "Workstream type": WORKFLOW_LABELS.get(workstream.workstream_type, workstream.workstream_type),
            "Lead": safe_text(users_by_id.get(workstream.owner_user_id or "")),
            "Cross stage": CROSS_STAGE_LABELS.get(workstream.cross_stage, workstream.cross_stage),
            "Risk": RISK_LABELS.get(workstream.risk_level, workstream.risk_level),
            "Status": STATUS_LABELS.get(workstream.status, workstream.status),
            "State": "Active" if workstream.is_active else "Inactive",
        }
        for workstream in summary.workstreams
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No active workstreams are connected to this program.")


def render_team(summary: ProgramWorkspaceSummary) -> None:
    users_by_id = {user.id: user.display_name for user in summary.users}
    workstreams_by_id = {
        workstream.id: WORKFLOW_LABELS.get(workstream.workstream_type, workstream.workstream_type)
        for workstream in summary.workstreams
    }
    rows = [
        {
            "User": safe_text(users_by_id.get(assignment.user_id)),
            "Assignment role": ASSIGNMENT_ROLE_LABELS.get(
                assignment.assignment_role,
                assignment.assignment_role,
            ),
            "Workstream": safe_text(workstreams_by_id.get(assignment.workstream_id or "")),
            "Primary": "Yes" if assignment.is_primary else "No",
            "State": "Active" if assignment.is_active else "Inactive",
        }
        for assignment in summary.assignments
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No active assignments are connected to this program.")


def render_activity(summary: ProgramWorkspaceSummary) -> None:
    users_by_id = {user.id: user.display_name for user in summary.users}
    rows = [
        {
            "Timestamp": format_datetime(event.created_at),
            "Actor": safe_text(users_by_id.get(event.actor_user_id or "")),
            "Event": event.event_type.replace("_", " ").title(),
            "Entity": event.entity_type.replace("_", " ").title(),
            "Message": safe_text(event.message),
        }
        for event in summary.activity
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No activity has been recorded for this program yet.")
