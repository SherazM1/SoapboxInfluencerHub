from __future__ import annotations

import streamlit as st

from app.campaign_ops.formatting import WORKFLOW_LABELS
from app.campaign_ops.state import cancel_new_program, finish_new_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import WorkflowRole, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, Client
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.program_routing import ProgramRoutingService


def render_new_program_form(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
    clients: list[Client],
) -> None:
    st.subheader("New Program")
    if not can_access_admin(actor):
        st.warning("You do not have permission to create programs.")
        return

    st.button("Cancel", key="campaign_ops_new_program_cancel",
              on_click=cancel_new_program, args=(st.session_state,))

    del users, clients
    workflow_labels = list(WORKFLOW_LABELS.values())
    workflow_by_label = {label: key for key, label in WORKFLOW_LABELS.items()}
    default_workflow = WORKFLOW_LABELS[WorkstreamType.INFLUENCER.value]
    client_name = st.text_input("Client", key="campaign_ops_new_program_client")
    program_name = st.text_input("Program Name", key="campaign_ops_new_program_name")
    workflow_label = st.selectbox(
        "Workflow",
        workflow_labels,
        index=workflow_labels.index(default_workflow),
        key="campaign_ops_new_program_workflow",
    )
    workflow_key = workflow_by_label[workflow_label]
    try:
        lead_users = service.list_workflow_role_users(
            workflow_key, WorkflowRole.LEAD_OWNER.value
        )
        manager_users = service.list_workflow_role_users(
            workflow_key, WorkflowRole.MANAGER.value
        )
    except CampaignOpsError as exc:
        st.error(f"Unable to load the workflow roster: {exc}")
        return
    if not lead_users or not manager_users:
        st.info("No active Lead Owner / Manager roster is configured for this workflow.")
        return

    lead_names = {user.id: user.display_name for user in lead_users}
    manager_names = {user.id: user.display_name for user in manager_users}
    lead_id = st.selectbox(
        "Lead Owner", list(lead_names), format_func=lead_names.get,
        index=None, placeholder="Choose a Lead Owner",
        key=f"campaign_ops_new_program_lead_{workflow_key}",
    )
    manager_id = st.selectbox(
        "Manager", list(manager_names), format_func=manager_names.get,
        index=None, placeholder="Choose a Manager",
        key=f"campaign_ops_new_program_manager_{workflow_key}",
    )

    if not st.button("Create Program", type="primary", key="campaign_ops_new_program_submit"):
        return
    if lead_id is None:
        st.error("Choose a Lead Owner.")
        return
    if manager_id is None:
        st.error("Choose a Manager.")
        return
    try:
        program_id = ProgramRoutingService(service.repository).create_registry_program(
            actor=actor,
            program_name=program_name,
            new_client_name=trim_or_none(client_name),
            primary_workstream_type=workflow_key,
            primary_owner_user_id=lead_id,
            manager_user_id=manager_id,
            workstream_types=[workflow_key],
        )
    except CampaignOpsError as exc:
        st.error(f"Program was not created: {exc}")
        return

    finish_new_program(st.session_state, program_id)
    st.rerun()
