from __future__ import annotations

from datetime import UTC, datetime

import streamlit as st

from app.campaign_ops.formatting import (
    ASSIGNMENT_ROLE_LABELS,
    CROSS_STAGE_LABELS,
    RISK_LABELS,
    STATUS_LABELS,
    WORKFLOW_LABELS,
    format_date,
    format_datetime,
    format_list,
    safe_text,
)
from app.campaign_ops.state import set_section, set_selected_program
from core.campaign_ops.enums import CrossStage, ProgramStatus, RiskLevel, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, Client, ProgramPortfolioRow
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.program_routing import ProgramRoutingService

SORT_OPTIONS = {
    "Recently updated": "recently_updated",
    "Program name": "program_name",
    "Client": "client",
    "Risk": "risk",
    "Cross stage": "cross_stage",
    "Program status": "program_status",
    "Start date": "start_date",
    "Target end date": "target_end_date",
}

ACTIVE_OPTIONS = {
    "Active": "active",
    "Archived": "archived",
    "All": "all",
}


def blank_filter_state() -> dict[str, str | None]:
    return {
        "search": "",
        "program_name": "",
        "client_name": "",
        "client_id": "",
        "primary_workstream_type": "",
        "connected_workstream_type": "",
        "cross_stage": "",
        "status": "",
        "risk_level": "",
        "primary_owner_user_id": "",
        "assigned_user_id": "",
        "active_state": "active",
        "sort_by": "recently_updated",
    }


def clean_filters(filters: dict[str, str | None]) -> dict[str, str | None]:
    return {key: value for key, value in filters.items() if value not in ("", None)}


def user_options(users: list[CampaignOpsUser]) -> dict[str, str]:
    return {"Any": "", **{user.display_name: user.id for user in users}}


def client_options(clients: list[Client]) -> dict[str, str]:
    return {"Any": "", **{client.name: client.id for client in clients}}


def render_portfolio_filters(
    key: str,
    clients: list[Client],
    users: list[CampaignOpsUser],
    include_text_filters: bool,
    include_people_filters: bool,
) -> dict[str, str | None]:
    current = st.session_state.get(key)
    if not isinstance(current, dict):
        current = blank_filter_state()
        st.session_state[key] = current

    with st.expander("Filters", expanded=True):
        if include_text_filters:
            cols = st.columns(3)
            current["search"] = cols[0].text_input(
                "Search",
                value=str(current.get("search") or ""),
                key=f"{key}_search",
            )
            current["program_name"] = cols[1].text_input(
                "Program name",
                value=str(current.get("program_name") or ""),
                key=f"{key}_program_name",
            )
            current["client_name"] = cols[2].text_input(
                "Client name",
                value=str(current.get("client_name") or ""),
                key=f"{key}_client_name",
            )

        cols = st.columns(4)
        client_map = client_options(clients)
        client_labels = list(client_map)
        current_client = next(
            (label for label, value in client_map.items() if value == current.get("client_id")),
            "Any",
        )
        current["client_id"] = client_map[
            cols[0].selectbox(
                "Client",
                client_labels,
                index=client_labels.index(current_client),
                key=f"{key}_client_id",
            )
        ]
        workflow_labels = ["Any", *WORKFLOW_LABELS.values()]
        workflow_values = {"Any": "", **{label: value for value, label in WORKFLOW_LABELS.items()}}
        current["primary_workstream_type"] = workflow_values[
            cols[1].selectbox("Primary workflow", workflow_labels, key=f"{key}_primary_workflow")
        ]
        current["connected_workstream_type"] = workflow_values[
            cols[2].selectbox("Connected workstream", workflow_labels, key=f"{key}_connected_workflow")
        ]
        active_labels = list(ACTIVE_OPTIONS)
        current_active = next(
            (label for label, value in ACTIVE_OPTIONS.items() if value == current.get("active_state")),
            "Active",
        )
        current["active_state"] = ACTIVE_OPTIONS[
            cols[3].selectbox(
                "Active state",
                active_labels,
                index=active_labels.index(current_active),
                key=f"{key}_active",
            )
        ]

        cols = st.columns(4)
        current["cross_stage"] = _enum_select(
            cols[0],
            "Cross stage",
            CROSS_STAGE_LABELS,
            f"{key}_cross_stage",
        )
        current["status"] = _enum_select(cols[1], "Program status", STATUS_LABELS, f"{key}_status")
        current["risk_level"] = _enum_select(cols[2], "Risk", RISK_LABELS, f"{key}_risk")
        current["sort_by"] = SORT_OPTIONS[
            cols[3].selectbox("Sort", list(SORT_OPTIONS), key=f"{key}_sort")
        ]

        if include_people_filters:
            people_map = user_options(users)
            people_labels = list(people_map)
            cols = st.columns(2)
            current["primary_owner_user_id"] = people_map[
                cols[0].selectbox("Primary owner", people_labels, key=f"{key}_owner")
            ]
            current["assigned_user_id"] = people_map[
                cols[1].selectbox("Any assigned person", people_labels, key=f"{key}_assigned")
            ]

    st.session_state[key] = current
    return clean_filters(current)


def _enum_select(column: object, label: str, label_map: dict[str, str], key: str) -> str:
    labels = ["Any", *label_map.values()]
    values = {"Any": "", **{display: value for value, display in label_map.items()}}
    return values[column.selectbox(label, labels, key=key)]


def render_program_rows(rows: list[ProgramPortfolioRow], my_programs: bool = False) -> None:
    if not rows:
        st.info("No programs match this view.")
        return
    table_rows = []
    for row in rows:
        base = {
            "Program name": row.program_name,
            "Client": safe_text(row.client_name),
            "Primary workflow": WORKFLOW_LABELS.get(row.primary_workstream_type or "", "-"),
            "Connected workstreams": format_list(row.workstream_types),
            "Program status": STATUS_LABELS.get(row.status, row.status),
            "Cross stage": CROSS_STAGE_LABELS.get(row.cross_stage, row.cross_stage),
            "Risk": RISK_LABELS.get(row.risk_level, row.risk_level),
            "Priority": safe_text(row.priority),
            "Primary owner": safe_text(row.primary_owner_name),
            "Start date": format_date(row.start_date),
            "Target end date": format_date(row.target_end_date),
            "Last updated": format_datetime(row.updated_at),
            "State": "Active" if row.is_active else "Archived",
        }
        if my_programs:
            base["Assignment role"] = ASSIGNMENT_ROLE_LABELS.get(row.assignment_role or "", "-")
            base["Assigned workstream"] = WORKFLOW_LABELS.get(row.assigned_workstream_type or "", "-")
            base["Open assigned tasks"] = str(row.open_task_count)
            base["Overdue assigned tasks"] = str(row.overdue_task_count)
            base["Nearest task due"] = format_date(row.nearest_task_due_date)
        table_rows.append(base)
    st.dataframe(table_rows, use_container_width=True, hide_index=True)


def render_open_program_control(rows: list[ProgramPortfolioRow], key: str) -> None:
    if not rows:
        return
    labels = {f"{row.program_name} ({safe_text(row.client_name)})": row.id for row in rows}
    selected = st.selectbox("Open Program", list(labels), key=key)
    if st.button("Open Selected Program", type="primary", key=f"{key}_open"):
        set_selected_program(st.session_state, labels[selected])
        st.rerun()


def render_all_programs(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
    clients: list[Client],
) -> None:
    st.subheader("All Programs")
    if can_access_admin(actor) and st.button("New Program", type="primary"):
        st.session_state["campaign_ops_create_program_open"] = True
        set_section(st.session_state, "New Program")
        st.rerun()
    try:
        rows = ProgramRoutingService(service.repository).list_registry(actor)
    except CampaignOpsError as exc:
        st.error(f"Unable to load programs: {exc}")
        return
    columns = st.columns([2, 3, 2, 2, 2, 1])
    for column, label in zip(columns, ("Client", "Program", "Workflow", "Lead Owner", "Manager", "Open")):
        column.markdown(f"**{label}**")
    if not rows:
        st.info("No active programs are available.")
    for row in rows:
        columns = st.columns([2, 3, 2, 2, 2, 1])
        for column, value in zip(columns, (
            row.client_name, row.program_name, WORKFLOW_LABELS.get(row.primary_workstream_type, "-"),
            row.primary_owner_name, row.manager_name,
        )):
            column.write(safe_text(value))
        columns[5].button("Open", key=f"campaign_ops_registry_open_{row.id}",
                          on_click=set_selected_program, args=(st.session_state, row.id))


def render_my_programs(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
    clients: list[Client],
) -> None:
    st.subheader("My Programs")
    if can_access_admin(actor):
        show_all = st.checkbox("Show all programs", key="campaign_ops_my_show_all")
        if show_all:
            render_all_programs(actor, service, users, clients)
            return
    cols = st.columns(2)
    if cols[0].button("Refresh", key="campaign_ops_my_refresh"):
        st.session_state["campaign_ops_last_refresh"] = datetime.now(UTC).isoformat()
        st.rerun()
    if cols[1].button("Clear filters", key="campaign_ops_my_clear_filters"):
        st.session_state["campaign_ops_my_program_filters"] = blank_filter_state()
        st.rerun()
    filters = render_portfolio_filters(
        "campaign_ops_my_program_filters",
        clients,
        users,
        include_text_filters=False,
        include_people_filters=False,
    )
    try:
        rows = service.list_user_programs(actor, actor.id, filters)
    except CampaignOpsError as exc:
        st.error(f"Unable to load assigned programs: {exc}")
        return
    render_program_rows(rows, my_programs=True)
    render_open_program_control(rows, "campaign_ops_my_open_program")
