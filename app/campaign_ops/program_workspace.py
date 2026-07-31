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
from app.campaign_ops.timeline_views import render_timeline
from app.campaign_ops.resource_views import render_resources
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.task_views import render_program_tasks
from app.campaign_ops.validation import trim_or_none, validate_date_order
from core.campaign_ops.enums import AssignmentRole, WaitingOn, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, ProgramAssignment, ProgramWorkspaceSummary, Workstream
from core.campaign_ops.permissions import can_access_admin, can_edit_program, can_edit_workstream, can_manage_assignments
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
    render_admin_archive_controls(actor, service, summary)
    tabs = st.tabs(["Overview", "Workstreams", "Tasks", "Timeline", "Resources", "Notes", "Team", "Activity"])
    with tabs[0]:
        render_overview(summary, actor)
    with tabs[1]:
        render_workstreams(summary, actor, service)
    with tabs[2]:
        render_program_tasks(actor, service, summary)
    with tabs[3]:
        render_timeline(actor, service, summary)
    with tabs[4]:
        render_resources(actor, service, summary)
    with tabs[5]:
        render_notes(actor, service, summary)
    with tabs[6]:
        render_team(summary, actor, service)
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


def render_admin_archive_controls(
    actor: CampaignOpsUser | None,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    if not can_access_admin(actor):
        return
    with st.expander("Program Archive / Reactivation", expanded=False):
        program = summary.program
        confirm_text = st.text_input(
            "Type the program name to confirm",
            key=f"campaign_ops_archive_confirm_{program.id}",
        )
        if program.is_active:
            if st.button("Archive Program", key=f"campaign_ops_archive_{program.id}"):
                if confirm_text != program.program_name:
                    st.error("Confirmation must match the program name.")
                    return
                try:
                    service.archive_program(actor, program.id)
                except CampaignOpsError as exc:
                    st.error(f"Program was not archived: {exc}")
                    return
                st.success("Program archived.")
                st.rerun()
        else:
            if st.button("Reactivate Program", key=f"campaign_ops_reactivate_{program.id}"):
                if confirm_text != program.program_name:
                    st.error("Confirmation must match the program name.")
                    return
                try:
                    service.reactivate_program(actor, program.id)
                except CampaignOpsError as exc:
                    st.error(f"Program was not reactivated: {exc}")
                    return
                st.success("Program reactivated.")
                st.rerun()


def render_overview(summary: ProgramWorkspaceSummary, actor: CampaignOpsUser | None = None) -> None:
    st.markdown("### Overview")
    st.caption("Persisted shared program details.")
    program = summary.program
    editable = can_edit_program(actor, program, [a for a in summary.assignments if a.is_active])
    if editable:
        render_overview_form(actor, summary)
        st.divider()
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
def render_overview_form(actor: CampaignOpsUser | None, summary: ProgramWorkspaceSummary) -> None:
    program = summary.program
    clients = CampaignOpsService().list_active_clients()
    client_options = {client.name: client.id for client in clients}
    current_client_label = next(
        (label for label, value in client_options.items() if value == program.client_id),
        next(iter(client_options), ""),
    )
    with st.form(f"campaign_ops_program_edit_{program.id}"):
        cols = st.columns(2)
        program_name = cols[0].text_input("Program name", value=program.program_name)
        client_label = cols[1].selectbox(
            "Client",
            list(client_options) or ["No active clients"],
            index=(list(client_options).index(current_client_label) if current_client_label in client_options else 0),
        )
        description = st.text_area("Description", value=program.description or "")
        cols = st.columns(3)
        primary_workflow = _enum_select(cols[0], "Primary workflow", WORKFLOW_LABELS, program.primary_workstream_type)
        status = _enum_select(cols[1], "Program status", STATUS_LABELS, program.status)
        cross_stage = _enum_select(cols[2], "Cross stage", CROSS_STAGE_LABELS, program.cross_stage)
        cols = st.columns(3)
        risk = _enum_select(cols[0], "Risk", RISK_LABELS, program.risk_level)
        priority = cols[1].text_input("Priority", value=program.priority or "")
        latest_update = cols[2].text_input("Latest operational update", value=program.latest_update or "")
        cols = st.columns(2)
        start_date = cols[0].date_input("Start date", value=program.start_date)
        target_end_date = cols[1].date_input("Target end date", value=program.target_end_date)
        submitted = st.form_submit_button("Save Overview", type="primary")
    if not submitted:
        return
    error = validate_date_order(start_date, target_end_date)
    if error:
        st.error(error)
        return
    try:
        service = CampaignOpsService()
        updated = service.update_program_details(
            actor,
            program.id,
            program_name=program_name,
            client_id=client_options.get(client_label),
            description=trim_or_none(description),
            primary_workstream_type=primary_workflow,
            status=status,
            cross_stage=cross_stage,
            risk_level=risk,
            priority=trim_or_none(priority),
            latest_update=trim_or_none(latest_update),
            start_date=start_date,
            target_end_date=target_end_date,
        )
    except CampaignOpsError as exc:
        st.error(f"Program was not updated: {exc}")
        return
    st.success("Program updated." if updated.updated_at != program.updated_at else "No changes to save.")
    st.rerun()


def render_workstreams(summary: ProgramWorkspaceSummary, actor: CampaignOpsUser | None = None, service: CampaignOpsService | None = None) -> None:
    service = service or CampaignOpsService()
    active_assignments = [assignment for assignment in summary.assignments if assignment.is_active]
    show_inactive = st.checkbox("Show inactive workstreams", key="campaign_ops_show_inactive_workstreams")
    if can_access_admin(actor):
        render_add_workstream_form(actor, service, summary)
        st.divider()
    users_by_id = {user.id: user.display_name for user in summary.users}
    visible_workstreams = [
        workstream for workstream in summary.workstreams if show_inactive or workstream.is_active
    ]
    rows = [
        {
            "Workstream type": WORKFLOW_LABELS.get(workstream.workstream_type, workstream.workstream_type),
            "Lead": safe_text(users_by_id.get(workstream.owner_user_id or "")),
            "Cross stage": CROSS_STAGE_LABELS.get(workstream.cross_stage, workstream.cross_stage),
            "Risk": RISK_LABELS.get(workstream.risk_level, workstream.risk_level),
            "Status": STATUS_LABELS.get(workstream.status, workstream.status),
            "State": "Active" if workstream.is_active else "Inactive",
        }
        for workstream in visible_workstreams
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No active workstreams are connected to this program.")
    for workstream in visible_workstreams:
        editable = can_access_admin(actor) or can_edit_workstream(actor, workstream, active_assignments)
        if editable:
            render_workstream_editor(actor, service, summary, workstream)


def render_add_workstream_form(actor: CampaignOpsUser | None, service: CampaignOpsService, summary: ProgramWorkspaceSummary) -> None:
    with st.expander("Add Workstream", expanded=False):
        user_options = {"Unassigned": None, **{user.display_name: user.id for user in summary.users if user.is_active}}
        workflow = _enum_select(st, "Workstream type", WORKFLOW_LABELS, WorkstreamType.INFLUENCER.value, key="campaign_ops_add_workstream_type")
        lead_label = st.selectbox("Lead", list(user_options), key="campaign_ops_add_workstream_lead")
        if st.button("Add Workstream", key="campaign_ops_add_workstream_submit"):
            try:
                service.add_workstream_to_program(
                    actor,
                    summary.program.id,
                    workflow,
                    owner_user_id=user_options[lead_label],
                )
            except CampaignOpsError as exc:
                st.error(f"Workstream was not added: {exc}")
                return
            st.success("Workstream added.")
            st.rerun()


def render_workstream_editor(
    actor: CampaignOpsUser | None,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    workstream: Workstream,
) -> None:
    label = WORKFLOW_LABELS.get(workstream.workstream_type, workstream.workstream_type)
    with st.expander(f"Edit Workstream: {label}", expanded=False):
        user_options = {"Unassigned": None, **{user.display_name: user.id for user in summary.users if user.is_active}}
        current_lead = next((name for name, user_id in user_options.items() if user_id == workstream.owner_user_id), "Unassigned")
        cols = st.columns(3)
        status = _enum_select(cols[0], "Status", STATUS_LABELS, workstream.status, key=f"campaign_ops_ws_status_{workstream.id}")
        cross_stage = _enum_select(cols[1], "Cross stage", CROSS_STAGE_LABELS, workstream.cross_stage, key=f"campaign_ops_ws_stage_{workstream.id}")
        risk = _enum_select(cols[2], "Risk", RISK_LABELS, workstream.risk_level, key=f"campaign_ops_ws_risk_{workstream.id}")
        cols = st.columns(3)
        waiting_on = _enum_select(
            cols[0],
            "Waiting on",
            {item.value: item.value.replace("_", " ").title() for item in WaitingOn},
            workstream.waiting_on,
            key=f"campaign_ops_ws_waiting_{workstream.id}",
        )
        next_due = cols[1].date_input("Next due date", value=workstream.next_due_date, key=f"campaign_ops_ws_due_{workstream.id}")
        lead_label = cols[2].selectbox(
            "Lead",
            list(user_options),
            index=list(user_options).index(current_lead),
            key=f"campaign_ops_ws_lead_{workstream.id}",
        )
        next_action = st.text_input("Next action", value=workstream.next_action or "", key=f"campaign_ops_ws_action_{workstream.id}")
        latest_update = st.text_input("Latest update", value=workstream.latest_update or "", key=f"campaign_ops_ws_update_{workstream.id}")
        cols = st.columns(3)
        if cols[0].button("Save Workstream", key=f"campaign_ops_ws_save_{workstream.id}"):
            try:
                service.update_workstream_details(
                    actor,
                    summary.program.id,
                    workstream.id,
                    status=status,
                    cross_stage=cross_stage,
                    risk_level=risk,
                    waiting_on=waiting_on,
                    next_due_date=next_due,
                    owner_user_id=user_options[lead_label],
                    next_action=trim_or_none(next_action),
                    latest_update=trim_or_none(latest_update),
                )
            except CampaignOpsError as exc:
                st.error(f"Workstream was not updated: {exc}")
                return
            st.success("Workstream updated.")
            st.rerun()
        if can_access_admin(actor) and workstream.is_active and cols[1].button("Deactivate", key=f"campaign_ops_ws_deactivate_{workstream.id}"):
            try:
                service.deactivate_workstream(actor, summary.program.id, workstream.id)
            except CampaignOpsError as exc:
                st.error(f"Workstream was not deactivated: {exc}")
                return
            st.success("Workstream deactivated.")
            st.rerun()
        if can_access_admin(actor) and not workstream.is_active and cols[2].button("Reactivate", key=f"campaign_ops_ws_reactivate_{workstream.id}"):
            try:
                service.reactivate_workstream(actor, summary.program.id, workstream.id)
            except CampaignOpsError as exc:
                st.error(f"Workstream was not reactivated: {exc}")
                return
            st.success("Workstream reactivated.")
            st.rerun()


def render_team(summary: ProgramWorkspaceSummary, actor: CampaignOpsUser | None = None, service: CampaignOpsService | None = None) -> None:
    service = service or CampaignOpsService()
    show_inactive = st.checkbox("Show inactive assignments", key="campaign_ops_show_inactive_assignments")
    if can_manage_assignments(actor):
        render_primary_owner_reassignment(actor, service, summary)
        render_add_assignment_form(actor, service, summary)
        st.divider()
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
        if show_inactive or assignment.is_active
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No active assignments are connected to this program.")
    if can_manage_assignments(actor):
        for assignment in summary.assignments:
            if show_inactive or assignment.is_active:
                render_assignment_editor(actor, service, summary, assignment)


def render_primary_owner_reassignment(
    actor: CampaignOpsUser | None,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    with st.expander("Reassign Primary Owner", expanded=False):
        current_owner = primary_owner(summary.assignments, summary.users)
        st.caption(f"Current primary owner: {safe_text(current_owner)}")
        user_options = {user.display_name: user.id for user in summary.users if user.is_active}
        selected = st.selectbox(
            "New primary owner",
            list(user_options),
            key=f"campaign_ops_primary_owner_select_{summary.program.id}",
        )
        confirm = st.checkbox(
            "I understand My Programs access may change.",
            key=f"campaign_ops_primary_owner_confirm_{summary.program.id}",
        )
        if st.button("Reassign Primary Owner", key=f"campaign_ops_primary_owner_submit_{summary.program.id}"):
            if not confirm:
                st.error("Confirm the reassignment before saving.")
                return
            try:
                service.reassign_primary_program_owner(actor, summary.program.id, user_options[selected])
            except CampaignOpsError as exc:
                st.error(f"Primary owner was not reassigned: {exc}")
                return
            st.success("Primary owner reassigned.")
            st.rerun()


def render_add_assignment_form(
    actor: CampaignOpsUser | None,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    with st.expander("Add Assignment", expanded=False):
        user_options = {user.display_name: user.id for user in summary.users if user.is_active}
        role = _enum_select(
            st,
            "Assignment role",
            ASSIGNMENT_ROLE_LABELS,
            AssignmentRole.CONTRIBUTOR.value,
            key=f"campaign_ops_assignment_add_role_{summary.program.id}",
        )
        user_label = st.selectbox("User", list(user_options), key=f"campaign_ops_assignment_add_user_{summary.program.id}")
        scope = st.radio(
            "Scope",
            ["Program", "Workstream"],
            horizontal=True,
            key=f"campaign_ops_assignment_add_scope_{summary.program.id}",
        )
        workstream_id = None
        if scope == "Workstream":
            workstream_options = {
                WORKFLOW_LABELS.get(workstream.workstream_type, workstream.workstream_type): workstream.id
                for workstream in summary.workstreams
                if workstream.is_active
            }
            if workstream_options:
                workstream_label = st.selectbox(
                    "Workstream",
                    list(workstream_options),
                    key=f"campaign_ops_assignment_add_workstream_{summary.program.id}",
                )
                workstream_id = workstream_options[workstream_label]
        is_primary = st.checkbox("Primary", key=f"campaign_ops_assignment_add_primary_{summary.program.id}")
        if st.button("Add Assignment", key=f"campaign_ops_assignment_add_submit_{summary.program.id}"):
            try:
                service.add_assignment(
                    actor,
                    summary.program.id,
                    user_options[user_label],
                    role,
                    workstream_id=workstream_id,
                    is_primary=is_primary,
                )
            except CampaignOpsError as exc:
                st.error(f"Assignment was not added: {exc}")
                return
            st.success("Assignment added.")
            st.rerun()


def render_assignment_editor(
    actor: CampaignOpsUser | None,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    assignment: ProgramAssignment,
) -> None:
    users_by_id = {user.id: user.display_name for user in summary.users}
    title = f"Edit Assignment: {safe_text(users_by_id.get(assignment.user_id))}"
    with st.expander(title, expanded=False):
        user_options = {user.display_name: user.id for user in summary.users if user.is_active}
        current_user = users_by_id.get(assignment.user_id, next(iter(user_options), ""))
        role = _enum_select(
            st,
            "Assignment role",
            ASSIGNMENT_ROLE_LABELS,
            assignment.assignment_role,
            key=f"campaign_ops_assignment_role_{assignment.id}",
        )
        user_label = st.selectbox(
            "User",
            list(user_options),
            index=list(user_options).index(current_user) if current_user in user_options else 0,
            key=f"campaign_ops_assignment_user_{assignment.id}",
        )
        scope = st.radio(
            "Scope",
            ["Program", "Workstream"],
            index=1 if assignment.workstream_id else 0,
            horizontal=True,
            key=f"campaign_ops_assignment_scope_{assignment.id}",
        )
        workstream_id = None
        if scope == "Workstream":
            workstream_options = {
                WORKFLOW_LABELS.get(workstream.workstream_type, workstream.workstream_type): workstream.id
                for workstream in summary.workstreams
            }
            current_ws = next((label for label, value in workstream_options.items() if value == assignment.workstream_id), next(iter(workstream_options), ""))
            if workstream_options:
                workstream_label = st.selectbox(
                    "Workstream",
                    list(workstream_options),
                    index=list(workstream_options).index(current_ws),
                    key=f"campaign_ops_assignment_workstream_{assignment.id}",
                )
                workstream_id = workstream_options[workstream_label]
        is_primary = st.checkbox("Primary", value=assignment.is_primary, key=f"campaign_ops_assignment_primary_{assignment.id}")
        cols = st.columns(3)
        if assignment.is_active and cols[0].button("Save Assignment", key=f"campaign_ops_assignment_save_{assignment.id}"):
            try:
                service.update_assignment(
                    actor,
                    summary.program.id,
                    assignment.id,
                    user_options[user_label],
                    role,
                    workstream_id,
                    is_primary=is_primary,
                )
            except CampaignOpsError as exc:
                st.error(f"Assignment was not updated: {exc}")
                return
            st.success("Assignment updated.")
            st.rerun()
        if assignment.is_active and cols[1].button("Deactivate", key=f"campaign_ops_assignment_deactivate_{assignment.id}"):
            try:
                service.deactivate_assignment(actor, summary.program.id, assignment.id)
            except CampaignOpsError as exc:
                st.error(f"Assignment was not deactivated: {exc}")
                return
            st.success("Assignment deactivated.")
            st.rerun()
        if not assignment.is_active and cols[2].button("Reactivate", key=f"campaign_ops_assignment_reactivate_{assignment.id}"):
            try:
                service.reactivate_assignment(actor, summary.program.id, assignment.id)
            except CampaignOpsError as exc:
                st.error(f"Assignment was not reactivated: {exc}")
                return
            st.success("Assignment reactivated.")
            st.rerun()


def render_activity(summary: ProgramWorkspaceSummary) -> None:
    users_by_id = {user.id: user.display_name for user in summary.users}
    filter_label = st.selectbox(
        "Activity filter",
        [
            "All activity",
            "Program changes",
            "Workstream changes",
            "Task changes",
            "Milestone changes",
            "Resource changes",
            "Notes",
            "Assignment changes",
            "Ownership changes",
            "Archive activity",
        ],
        key="campaign_ops_activity_filter",
    )
    rows = [
        {
            "Timestamp": format_datetime(event.created_at),
            "Actor": safe_text(users_by_id.get(event.actor_user_id or "")),
            "Event": event.event_type.replace("_", " ").title(),
            "Entity": event.entity_type.replace("_", " ").title(),
            "Message": safe_text(event.message),
            "Old value": format_activity_details(event.old_value_json),
            "New value": format_activity_details(event.new_value_json),
            "Entity ID": safe_text(event.entity_id),
            "Workstream": safe_text(event.workstream_id),
        }
        for event in summary.activity
        if activity_matches_filter(event.event_type, filter_label)
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No activity has been recorded for this program yet.")


def activity_matches_filter(event_type: str, filter_label: str) -> bool:
    if filter_label == "All activity":
        return True
    if filter_label == "Program changes":
        return event_type.startswith("program_")
    if filter_label == "Workstream changes":
        return event_type.startswith("workstream_")
    if filter_label == "Assignment changes":
        return event_type.startswith("assignment_")
    if filter_label == "Task changes":
        return event_type.startswith("task_")
    if filter_label == "Milestone changes":
        return event_type.startswith("milestone_")
    if filter_label == "Resource changes":
        return event_type.startswith("resource_")
    if filter_label == "Notes":
        return "note" in event_type
    if filter_label == "Ownership changes":
        return "owner" in event_type or "lead" in event_type
    if filter_label == "Archive activity":
        return "archiv" in event_type or "reactivat" in event_type
    return True


def format_activity_details(value: object) -> str:
    if not value:
        return "-"
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(f"{str(key).replace('_', ' ').title()}: {safe_text(item)}")
        return "; ".join(parts) if parts else "-"
    return safe_text(value)


def _enum_select(container: object, label: str, label_map: dict[str, str], current: str | None, key: str | None = None) -> str:
    labels = list(label_map.values())
    values = {display: value for value, display in label_map.items()}
    current_label = label_map.get(current or "", labels[0])
    return values[container.selectbox(label, labels, index=labels.index(current_label), key=key)]
