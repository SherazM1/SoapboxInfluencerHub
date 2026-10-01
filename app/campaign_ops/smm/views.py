from __future__ import annotations

from copy import deepcopy
import streamlit as st

from app.campaign_ops.operational_editor import collect_rows, editor_styles, render_rows
from app.campaign_ops.program_router import open_program
from core.campaign_ops.enums import WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsPermissionError
from core.campaign_ops.permissions import can_access_admin, require_program_access
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.smm import SMMTimelineService, sort_smm_timeline_rows

SELECTED = "campaign_ops_selected_smm_program_id"


def _back():
    st.session_state.pop(SELECTED, None)
    for key in list(st.session_state):
        if key.startswith("campaign_ops_smm_draft_"):
            st.session_state.pop(key, None)


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



def render_smm(actor, service, program_id=None):
    if st.session_state.pop("campaign_ops_smm_denied", False):
        st.warning("You do not have access to this program.")
    program_id = program_id or st.session_state.get(SELECTED)
    if program_id is None:
        _render_smm_program_list(actor, service)
        return
    render_editor(actor, SMMTimelineService(service.repository), str(program_id))
    st.button("Back to programs", key=f"smm_back_to_programs_{program_id}", on_click=_back)


@st.fragment
def render_editor(actor, service, program_id):
    draft_key = f"campaign_ops_smm_draft_{actor.id}_{program_id}"
    version_key = f"smm_timeline_editor_version_{actor.id}_{program_id}"
    repo = service.repository or CampaignOpsRepository()
    try:
        program = require_program_access(repo, actor, program_id, active_only=True)
        if program.primary_workstream_type != WorkstreamType.SMM.value:
            raise CampaignOpsError("The selected Program is not an SMM Program.")
        snapshot = st.session_state.get(draft_key)
        if snapshot is None:
            _, rows = service.initialize_program(actor, program_id)
            ownership = service.assignment_state(actor, program_id)
            snapshot = {
                "rows": deepcopy(rows), "ownership": ownership,
                "editor_owner": ownership["lead_id"], "editor_manager": ownership["manager_id"],
                "lead_names": {u.id: u.display_name for u in service.list_workflow_role_users("smm", "lead_owner")},
                "manager_names": {u.id: u.display_name for u in service.list_workflow_role_users("smm", "manager")},
                "editor_records": [{"_row_id": r.id, "_draft_id": r.id, "Date": r.due_date,
                    "Action": r.action, "Done": bool(r.done), "Program Notes": r.program_notes or ""}
                    for r in sort_smm_timeline_rows(rows)],
            }
            st.session_state[draft_key] = snapshot
    except CampaignOpsPermissionError:
        _back()
        st.session_state["campaign_ops_smm_denied"] = True
        st.rerun()  # Exceptional denial returns to full-page navigation.
    except CampaignOpsError as exc:
        st.error(str(exc))
        return
    editor_styles()
    with st.container(key="ops_editor"):
        st.markdown(f"### {program.program_name}")
        message = st.session_state.pop(draft_key + "_message", None)
        if message:
            (st.error if message[0] else st.success)(message[1])
        version = st.session_state.get(version_key, 0)
        prefix = f"smm_rows_{actor.id}_{program_id}_{version}"
        for label, options, field, key in (
            ("Lead Owner", snapshot["lead_names"], "editor_owner", f"{prefix}_lead"),
            ("Manager", snapshot["manager_names"], "editor_manager", f"{prefix}_manager"),
        ):
            snapshot[field] = st.selectbox(label, list(options), format_func=options.get,
                index=list(options).index(snapshot[field]) if snapshot[field] in options else None,
                placeholder=f"Choose a {label}", key=key, disabled=not can_access_admin(actor))
        st.markdown("#### Timeline")
        render_rows(snapshot, prefix)
        st.button("Save Changes", type="primary", key=f"smm_save_{program_id}", on_click=_save,
            args=(actor, service, program_id, draft_key, version_key, prefix))
        st.caption("Edits stay unsaved until Save Changes. Save before leaving.")


def _save(actor, service, program_id, draft_key, version_key, prefix):
    snapshot = st.session_state[draft_key]
    records = deepcopy(collect_rows(snapshot, prefix))
    lead, manager = st.session_state.get(f"{prefix}_lead"), st.session_state.get(f"{prefix}_manager")
    try:
        changes = service.save_changes(actor, program_id, records, snapshot["rows"],
            snapshot["ownership"], lead, manager)
    except (CampaignOpsError, ValueError) as exc:
        st.session_state[draft_key + "_message"] = (True, f"{exc} Nothing saved.")
    else:
        st.session_state.pop(draft_key, None)
        st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
        st.session_state[draft_key + "_message"] = (False, "Changes saved." if any(changes.values()) else "No changes to save.")
