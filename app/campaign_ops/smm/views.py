from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from app.campaign_ops.program_router import open_program
from core.campaign_ops.enums import AssignmentRole, WorkflowRole, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsPermissionError
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.smm import SMMTimelineService, sort_smm_timeline_rows


def _table_key(program_id: str, version: int = 0) -> str:
    return f"smm_timeline_table_{program_id}_{version}"


def _program_rows(service: CampaignOpsService, program_id: str):
    return SMMTimelineService(service.repository).initialize_program(None, program_id)[1]


def _frame_from_rows(rows):
    records = []
    for row in sort_smm_timeline_rows(rows):
        records.append(
            {
                "_row_id": getattr(row, "id", None),
                "Date": getattr(row, "due_date", None),
                "Action": getattr(row, "action", "") or "",
                "Done": bool(getattr(row, "done", False)),
                "Program Notes": getattr(row, "program_notes", None) or "",
            }
        )
    frame = pd.DataFrame(records, columns=["_row_id", "Date", "Action", "Done", "Program Notes"])
    if frame.empty:
        return pd.DataFrame(columns=["_row_id", "Date", "Action", "Done", "Program Notes"])
    return frame


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return pd.to_datetime(value).date()
    return value


def _save_smm_state(actor, service, program_id: str, draft_frame):
    if draft_frame is None:
        return
    rows = draft_frame.to_dict("records")
    repository = service.repository
    row_service = SMMTimelineService(repository)
    current_rows = row_service.fetch_rows(program_id)
    current_by_id = {row.id: row for row in current_rows}
    seen_ids = set()

    for row in rows:
        row_id = row.get("_row_id")
        action = str(row.get("Action") or "").strip()
        if not action:
            raise ValueError("Every row requires an action.")
        done = bool(row.get("Done", False))
        notes = row.get("Program Notes")
        parsed_date = _parse_date(row.get("Date"))
        if row_id and row_id in current_by_id:
            current = current_by_id[row_id]
            if (
                current.due_date != parsed_date
                or current.action != action
                or bool(current.done) != done
                or (current.program_notes or "") != (notes or "")
            ):
                row_service.update_row(
                    actor,
                    row_id,
                    due_date=parsed_date,
                    action=action,
                    program_notes=notes or "",
                    done=done,
                )
            seen_ids.add(row_id)
            continue
        row_service.create_row(
            actor,
            row_service.get_workspace(actor, program_id)[0].id,
            action,
            due_date=parsed_date,
            program_notes=notes or "",
            done=done,
        )

    for row_id in current_by_id:
        if row_id not in seen_ids:
            row_service.remove_row(actor, row_id)

    summary = service.get_program_workspace_summary(actor, program_id)
    smm_workstream = next((ws for ws in summary.workstreams if ws.workstream_type == WorkstreamType.SMM.value and ws.is_active), None)
    lead_owner = st.session_state.get(f"smm_lead_owner_{program_id}")
    manager = st.session_state.get(f"smm_manager_{program_id}")
    if lead_owner is not None and smm_workstream is not None:
        current_lead = next(
            (assignment.user_id for assignment in summary.assignments if assignment.is_active and assignment.is_primary and assignment.assignment_role == AssignmentRole.PROGRAM_OWNER.value),
            None,
        )
        if current_lead != lead_owner:
            service.reassign_primary_program_owner(actor, program_id, lead_owner)
    if manager is not None and smm_workstream is not None:
        current_manager = smm_workstream.owner_user_id
        if current_manager != manager:
            service.reassign_workstream_lead(actor, program_id, smm_workstream.id, manager)

    st.success("Changes saved.")


def _select_option(value, options):
    return value if value in options else next(iter(options), None)


def _render_smm_program_list(actor, service: CampaignOpsService) -> None:
    try:
        programs = [
            row for row in ProgramRoutingService(service.repository).list_registry(actor)
            if row.primary_workstream_type == WorkstreamType.SMM.value
        ]
    except CampaignOpsError as exc:
        st.error(f"Unable to load SMM programs: {exc}")
        return

    columns = st.columns([3, 2, 2, 1])
    for column, label in zip(columns, ("Program", "Lead Owner", "Manager", "Open")):
        column.markdown(f"**{label}**")
    if not programs:
        st.info("No active SMM programs are available.")
    for program in programs:
        columns = st.columns([3, 2, 2, 1])
        columns[0].write(program.program_name)
        columns[1].write(program.primary_owner_name or "-")
        columns[2].write(program.manager_name or "-")
        columns[3].button(
            "Open",
            key=f"campaign_ops_smm_open_{program.id}",
            on_click=open_program,
            args=(st.session_state, actor, service, program.id),
        )


def render_smm(actor, service, program_id: str | None = None) -> None:
    if program_id is None:
        program_id = st.session_state.get("campaign_ops_selected_smm_program_id")
    if program_id is None:
        _render_smm_program_list(actor, service)
        return

    try:
        destination = ProgramRoutingService(service.repository).resolve(actor, str(program_id))
        if destination.section != "Social Media Management":
            raise ValueError("The selected Program is not an SMM Program.")
        summary = service.get_program_workspace_summary(actor, program_id)
    except CampaignOpsPermissionError:
        st.session_state.pop("campaign_ops_selected_smm_program_id", None)
        st.warning("You do not have access to this program.")
        _render_smm_program_list(actor, service)
        return
    except (CampaignOpsError, ValueError) as exc:
        st.session_state.pop("campaign_ops_selected_smm_program_id", None)
        st.error(f"SMM program unavailable: {exc}")
        return

    if st.button("Back to programs", key=f"smm_back_to_programs_{program_id}"):
        st.session_state.pop("campaign_ops_selected_smm_program_id", None)
        st.rerun()

    st.markdown(f"### {summary.program.program_name}")
    lead_options = {user.id: user.display_name for user in service.list_workflow_role_users(WorkstreamType.SMM.value, WorkflowRole.LEAD_OWNER.value)}
    manager_options = {user.id: user.display_name for user in service.list_workflow_role_users(WorkstreamType.SMM.value, WorkflowRole.MANAGER.value)}

    current_lead = next(
        (assignment.user_id for assignment in summary.assignments if assignment.is_active and assignment.is_primary and assignment.assignment_role == AssignmentRole.PROGRAM_OWNER.value),
        None,
    )
    smm_workstream = next((ws for ws in summary.workstreams if ws.workstream_type == WorkstreamType.SMM.value and ws.is_active), None)
    current_manager = smm_workstream.owner_user_id if smm_workstream else None

    lead_key = f"smm_lead_owner_{program_id}"
    manager_key = f"smm_manager_{program_id}"
    if lead_key not in st.session_state:
        st.session_state[lead_key] = current_lead if current_lead in lead_options else next(iter(lead_options), None)
    if manager_key not in st.session_state:
        st.session_state[manager_key] = current_manager if current_manager in manager_options else next(iter(manager_options), None)

    st.selectbox(
        "Lead Owner",
        list(lead_options),
        format_func=lambda user_id: lead_options.get(user_id, "Unassigned"),
        index=list(lead_options).index(st.session_state[lead_key]) if st.session_state[lead_key] in lead_options else 0,
        key=lead_key,
        disabled=not can_access_admin(actor),
    )
    st.selectbox(
        "Manager",
        list(manager_options),
        format_func=lambda user_id: manager_options.get(user_id, "Unassigned"),
        index=list(manager_options).index(st.session_state[manager_key]) if st.session_state[manager_key] in manager_options else 0,
        key=manager_key,
        disabled=not can_access_admin(actor),
    )

    st.markdown("#### Timeline")
    base_rows = _program_rows(service, program_id)
    version_key = f"smm_timeline_editor_version_{program_id}"
    version = st.session_state.get(version_key, 0)
    table_key = _table_key(program_id, version)

    draft = st.data_editor(
        _frame_from_rows(base_rows),
        key=table_key,
        hide_index=True,
        num_rows="dynamic",
        column_order=["Date", "Action", "Done", "Program Notes"],
        disabled=["_row_id"],
        column_config={
            "_row_id": st.column_config.Column("", disabled=True),
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD", required=False),
            "Action": st.column_config.TextColumn("Action", width="large"),
            "Done": st.column_config.CheckboxColumn("Done"),
            "Program Notes": st.column_config.TextColumn("Program Notes", width="large"),
        },
    )
    if st.button("Save Changes", type="primary"):
        try:
            _save_smm_state(actor, service, program_id, draft)
            st.session_state[version_key] = version + 1
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
