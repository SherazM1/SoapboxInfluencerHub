from __future__ import annotations

from datetime import date

import streamlit as st

from app.campaign_ops.formatting import (
    CROSS_STAGE_LABELS,
    RISK_LABELS,
    STATUS_LABELS,
    WORKFLOW_LABELS,
)
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none, validate_date_order
from core.campaign_ops.enums import CrossStage, ProgramStatus, RiskLevel, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, Client
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService


def _reverse_label_map(label_map: dict[str, str]) -> dict[str, str]:
    return {label: value for value, label in label_map.items()}


def _user_label_map(users: list[CampaignOpsUser]) -> dict[str, str]:
    return {user.display_name: user.id for user in users if user.is_active}


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

    workflow_values = _reverse_label_map(WORKFLOW_LABELS)
    status_values = _reverse_label_map(STATUS_LABELS)
    stage_values = _reverse_label_map(CROSS_STAGE_LABELS)
    risk_values = _reverse_label_map(RISK_LABELS)
    user_values = _user_label_map(users)

    if not user_values:
        st.error("No active Campaign Operations users are available for assignment.")
        return

    with st.form("campaign_ops_new_program_form", clear_on_submit=False):
        program_name = st.text_input("Program name")
        client_mode = st.radio(
            "Client",
            ["Use existing client", "Create new client"],
            horizontal=True,
            key="campaign_ops_client_mode",
        )
        client_id: str | None = None
        new_client_name: str | None = None
        if client_mode == "Use existing client":
            client_labels = [client.name for client in clients]
            if client_labels:
                selected_client = st.selectbox("Existing client", client_labels)
                client_by_name = {client.name: client.id for client in clients}
                client_id = client_by_name[selected_client]
            else:
                st.info("No active clients exist yet. Create a new client for this program.")
        else:
            new_client_name = st.text_input("New client name")

        description = st.text_area("Description", height=100)
        cols = st.columns(3)
        primary_workflow_label = cols[0].selectbox(
            "Primary workflow",
            list(WORKFLOW_LABELS.values()),
            key="campaign_ops_primary_workflow",
        )
        primary_workflow = workflow_values[primary_workflow_label]
        status = status_values[
            cols[1].selectbox(
                "Program status",
                list(STATUS_LABELS.values()),
                index=list(STATUS_LABELS).index(ProgramStatus.DRAFT.value),
            )
        ]
        cross_stage = stage_values[
            cols[2].selectbox(
                "Cross stage",
                list(CROSS_STAGE_LABELS.values()),
                index=list(CROSS_STAGE_LABELS).index(CrossStage.DRAFT.value),
            )
        ]

        cols = st.columns(3)
        risk = risk_values[
            cols[0].selectbox(
                "Risk",
                list(RISK_LABELS.values()),
                index=list(RISK_LABELS).index(RiskLevel.UNRATED.value),
            )
        ]
        priority = cols[1].text_input("Priority")
        primary_owner_label = cols[2].selectbox("Primary owner", list(user_values))
        primary_owner_user_id = user_values[primary_owner_label]

        cols = st.columns(2)
        start_date = cols[0].date_input("Start date", value=None)
        target_end_date = cols[1].date_input("Target end date", value=None)

        selected_workflow_labels = st.multiselect(
            "Initial workstreams",
            list(WORKFLOW_LABELS.values()),
            default=[primary_workflow_label],
            key="campaign_ops_initial_workstreams",
        )
        selected_workstream_values = [
            workflow_values[label] for label in selected_workflow_labels
        ]
        if primary_workflow not in selected_workstream_values:
            selected_workstream_values.insert(0, primary_workflow)
            st.caption(f"{primary_workflow_label} will be included as the primary workflow.")

        lead_options = ["Unassigned", *user_values.keys()]
        workstream_leads: dict[str, str | None] = {}
        st.markdown("Workstream leads")
        for workstream_value in selected_workstream_values:
            label = WORKFLOW_LABELS.get(workstream_value, workstream_value)
            lead_label = st.selectbox(
                label,
                lead_options,
                key=f"campaign_ops_workstream_lead_{workstream_value}",
            )
            workstream_leads[workstream_value] = (
                None if lead_label == "Unassigned" else user_values[lead_label]
            )

        submitted = st.form_submit_button("Create Program", type="primary")

    if not submitted:
        return

    date_error = validate_date_order(start_date, target_end_date)
    if date_error:
        st.error(date_error)
        return
    try:
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=actor,
            program_name=program_name,
            client_id=client_id,
            new_client_name=trim_or_none(new_client_name),
            description=trim_or_none(description),
            primary_workstream_type=primary_workflow,
            status=status,
            cross_stage=cross_stage,
            risk_level=risk,
            priority=trim_or_none(priority),
            start_date=start_date if isinstance(start_date, date) else None,
            target_end_date=target_end_date if isinstance(target_end_date, date) else None,
            primary_owner_user_id=primary_owner_user_id,
            workstream_types=selected_workstream_values,
            workstream_lead_user_ids=workstream_leads,
        )
    except CampaignOpsError as exc:
        st.error(f"Program was not created: {exc}")
        return

    st.success("Program created.")
    set_selected_program(st.session_state, program_id)
    st.session_state["campaign_ops_create_program_open"] = False
    st.rerun()
