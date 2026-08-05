from __future__ import annotations

from datetime import date
from typing import Any

import streamlit as st

from app.campaign_ops.cross_team.formatting import csv_rows
from app.campaign_ops.state import set_section
from app.campaign_ops.ui.badges import status_label
from app.campaign_ops.ui.components import render_empty_state, render_page_header, render_section_header, render_status_badges
from app.campaign_ops.ui.formatting import display_record_title, format_display_date, readable_label
from app.campaign_ops.ui.navigation import route_to_program_workspace, route_to_specialized_workspace
from core.campaign_ops.enums import CrossStage, ProgramStatus, RiskLevel, WaitingOn, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, CrossTeamDashboardSummary
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService


PERSON_OPTIONS = ["Cross-Team", "Bailey", "T", "L"]


def _user_options(users: list[CampaignOpsUser]) -> dict[str, str]:
    return {user.display_name: user.id for user in users if user.display_name in {"Bailey", "T", "L"}}


def _enum_options(enum_type: Any) -> list[str]:
    return [""] + [item.value for item in enum_type]


def _clear_filters() -> None:
    for key in (
        "campaign_ops_cross_team_filters",
        "campaign_ops_cross_team_owner",
        "campaign_ops_cross_team_assigned",
        "campaign_ops_cross_team_client",
        "campaign_ops_cross_team_program",
        "campaign_ops_cross_team_primary_workflow",
        "campaign_ops_cross_team_connected_workstream",
        "campaign_ops_cross_team_influencer_stage",
        "campaign_ops_cross_team_cross_stage",
        "campaign_ops_cross_team_status",
        "campaign_ops_cross_team_risk",
        "campaign_ops_cross_team_waiting_on",
        "campaign_ops_cross_team_active_state",
        "campaign_ops_cross_team_search",
        "campaign_ops_cross_team_needs_only",
    ):
        st.session_state.pop(key, None)


def _drill_to(program_id: str, section: str, record_id: str | None = None) -> None:
    if section == "Program Workspace":
        route_to_program_workspace(st.session_state, program_id)
    else:
        route_to_specialized_workspace(st.session_state, section, program_id, record_id)
    st.rerun()


def _render_filters(service: CampaignOpsService, actor: CampaignOpsUser, users: list[CampaignOpsUser]) -> dict[str, Any]:
    user_ids = _user_options(users)
    clients = service.list_active_clients()
    client_options = {"": None, **{client.name: client.id for client in clients}}
    allowed_person = PERSON_OPTIONS if can_access_admin(actor) else [actor.display_name]
    default_person = "Cross-Team" if can_access_admin(actor) else actor.display_name
    person_view = st.selectbox(
        "Dashboard view",
        allowed_person,
        index=allowed_person.index(st.session_state.get("campaign_ops_cross_team_person_view", default_person)) if st.session_state.get("campaign_ops_cross_team_person_view", default_person) in allowed_person else 0,
        key="campaign_ops_cross_team_person_view",
    )
    include_test = st.checkbox("Include test records", value=bool(st.session_state.get("campaign_ops_cross_team_include_test_records", False)), key="campaign_ops_cross_team_include_test_records", help="Validation records prefixed with TEST - are excluded from dashboard metrics by default.")
    if not include_test:
        st.markdown("<div class='campaign-ops-filter-note'>TEST - validation records are excluded from metrics and sections.</div>", unsafe_allow_html=True)
    upcoming_days = st.number_input("Upcoming milestone window", min_value=1, max_value=90, value=int(st.session_state.get("campaign_ops_cross_team_upcoming_days", 14)), step=1, key="campaign_ops_cross_team_upcoming_days")
    with st.expander("Global Filters", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        owner_label = c1.selectbox("Owner", [""] + list(user_ids), key="campaign_ops_cross_team_owner")
        assigned_label = c2.selectbox("Assigned Person", [""] + list(user_ids), key="campaign_ops_cross_team_assigned")
        client_label = c3.selectbox("Client", list(client_options), key="campaign_ops_cross_team_client")
        program_name = c4.text_input("Program", key="campaign_ops_cross_team_program")
        c5, c6, c7, c8 = st.columns(4)
        primary = c5.selectbox("Primary Workflow", _enum_options(WorkstreamType), key="campaign_ops_cross_team_primary_workflow")
        connected = c6.selectbox("Connected Workstream", _enum_options(WorkstreamType), key="campaign_ops_cross_team_connected_workstream")
        influencer_stage = c7.selectbox("Influencer Stage", ["", "planning", "live", "recapping", "complete"], key="campaign_ops_cross_team_influencer_stage")
        cross_stage = c8.selectbox("Cross Stage", _enum_options(CrossStage), key="campaign_ops_cross_team_cross_stage")
        c9, c10, c11, c12 = st.columns(4)
        status = c9.selectbox("Program Status", _enum_options(ProgramStatus), key="campaign_ops_cross_team_status")
        risk = c10.selectbox("Risk", _enum_options(RiskLevel), key="campaign_ops_cross_team_risk")
        waiting_on = c11.selectbox("Waiting On", _enum_options(WaitingOn), key="campaign_ops_cross_team_waiting_on")
        active_state = c12.selectbox("Active State", ["active", "inactive", "all"], key="campaign_ops_cross_team_active_state")
        c13, c14, c15, c16 = st.columns(4)
        start_from = c13.date_input("Start Date From", value=None, key="campaign_ops_cross_team_start_from")
        target_to = c14.date_input("Target End Date To", value=None, key="campaign_ops_cross_team_target_to")
        needs_only = c15.checkbox("Needs Attention only", key="campaign_ops_cross_team_needs_only")
        search = c16.text_input("Search", key="campaign_ops_cross_team_search")
    buttons = st.columns([1, 1, 5])
    if buttons[0].button("Refresh", key="campaign_ops_cross_team_refresh"):
        st.session_state["campaign_ops_cross_team_last_refresh"] = date.today().isoformat()
        st.rerun()
    if buttons[1].button("Clear filters", key="campaign_ops_cross_team_clear"):
        _clear_filters()
        st.rerun()
    filters = {
        "person_view": person_view,
        "include_test_records": include_test,
        "upcoming_days": upcoming_days,
        "owner_user_id": user_ids.get(owner_label),
        "assigned_user_id": user_ids.get(assigned_label),
        "client_id": client_options.get(client_label),
        "program_name": program_name.strip() or None,
        "primary_workflow": primary or None,
        "connected_workstream": connected or None,
        "influencer_stage": influencer_stage or None,
        "cross_stage": cross_stage or None,
        "program_status": status or None,
        "risk": risk or None,
        "waiting_on": waiting_on or None,
        "active_state": active_state,
        "start_date_from": start_from if isinstance(start_from, date) else None,
        "target_end_date_to": target_to if isinstance(target_to, date) else None,
        "needs_attention_only": needs_only,
        "search": search.strip() or None,
    }
    st.session_state["campaign_ops_cross_team_filters"] = filters
    return filters


def _render_metrics(summary: CrossTeamDashboardSummary) -> None:
    metrics = summary.metrics
    values = [
        ("Active Programs", metrics.active_programs),
        ("Needs Attention", metrics.needs_attention),
        ("High Risk", metrics.high_risk),
        ("Overdue Tasks", metrics.overdue_tasks),
        ("Due This Week", metrics.due_this_week),
        ("Upcoming Milestones", metrics.upcoming_milestones),
        ("Waiting on Client", metrics.waiting_on_client),
        ("Waiting on Internal Team", metrics.waiting_on_internal_team),
        ("Paused / On Hold", metrics.paused_on_hold),
        ("Ready for Recap", metrics.ready_for_recap),
        ("Ready to Close", metrics.ready_to_close),
        ("Completed Recently", metrics.completed_recently),
    ]
    for row in range(0, len(values), 4):
        cols = st.columns(4)
        for col, (name, value) in zip(cols, values[row:row + 4]):
            col.metric(name, value)


def _table(rows: list[dict[str, Any]], empty: str) -> None:
    if not rows:
        render_empty_state("no filter matches", empty)
        return
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_attention(summary: CrossTeamDashboardSummary) -> None:
    render_section_header("Needs Attention", "Cross-workflow queue sorted by severity and due date.", len(summary.needs_attention))
    rows = [
        {
            "Program": display_record_title(row.program_name),
            "Client": row.client_name or "-",
            "Workflow": readable_label(row.workflow),
            "Stage": status_label(row.stage),
            "Owner": row.owner_name or "-",
            "Assigned": row.assigned_name or "-",
            "Attention Reason": row.attention_reason,
            "Severity": row.severity,
            "Risk": status_label(row.risk),
            "Waiting On": readable_label(row.waiting_on),
            "Due / Target": format_display_date(row.due_date),
            "Days Overdue": row.days_overdue or 0,
            "Latest Update": row.latest_update or "-",
        }
        for row in summary.needs_attention
    ]
    _table(rows[:50], "No matching Needs Attention items.")


def _render_waiting(summary: CrossTeamDashboardSummary) -> None:
    render_section_header("Waiting On", "Source waiting text is preserved and grouped into dashboard categories.", len(summary.waiting_on))
    rows = [
        {
            "Waiting On": row.waiting_category,
            "Source Text": readable_label(row.waiting_on),
            "Program": display_record_title(row.program_name),
            "Client": row.client_name or "-",
            "Workflow": readable_label(row.workflow),
            "Record Type": row.record_type,
            "Item": row.item,
            "Owner": row.owner_name or "-",
            "Due Date": format_display_date(row.due_date),
            "Age": row.age or 0,
            "Latest Update": row.latest_update or "-",
        }
        for row in summary.waiting_on
    ]
    _table(rows[:50], "No matching Waiting On items.")


def _render_operational_tables(summary: CrossTeamDashboardSummary) -> None:
    render_section_header("Overdue Tasks", "Active incomplete tasks past due.", len(summary.overdue_tasks))
    _table([
        {
            "Task": row.task,
            "Program": display_record_title(row.program_name),
            "Client": row.client_name or "-",
            "Workstream": readable_label(row.workstream),
            "Assigned User": row.assigned_user_name or "-",
            "Responsible Party": readable_label(row.responsible_party),
            "Status": status_label(row.status),
            "Risk": status_label(row.risk),
            "Due Date": format_display_date(row.due_date),
            "Days Overdue": row.days_overdue,
            "Waiting On": readable_label(row.waiting_on),
            "Hard Deadline": row.hard_deadline,
        }
        for row in summary.overdue_tasks[:50]
    ], "No overdue tasks.")
    render_section_header("Upcoming Milestones", "Incomplete milestones in the selected upcoming window.", len(summary.upcoming_milestones))
    _table([
        {
            "Milestone": row.milestone,
            "Program": display_record_title(row.program_name),
            "Client": row.client_name or "-",
            "Workstream": readable_label(row.workstream),
            "Owner": row.owner_name or "-",
            "Status": status_label(row.status),
            "Best Available Date": format_display_date(row.best_available_date),
            "Days Until": row.days_until,
            "Hard Deadline": row.hard_deadline,
            "Highlighted": row.highlighted,
        }
        for row in summary.upcoming_milestones[:50]
    ], "No upcoming milestones in the selected window.")


def _render_workload(summary: CrossTeamDashboardSummary) -> None:
    render_section_header("Workload by Person", "Transparent counts by owner, assignment, task owner, and workflow owner.", len(summary.workload))
    _table([
        {
            "Person": row.display_name,
            "Owned Active Programs": row.owned_active_programs,
            "Assigned Active Programs": row.assigned_active_programs,
            "Open Tasks": row.open_tasks,
            "Overdue Tasks": row.overdue_tasks,
            "Due This Week": row.due_this_week,
            "Active Milestones Owned": row.active_milestones_owned,
            "Needs Attention Programs": row.needs_attention_programs,
            "Waiting Items": row.waiting_items,
            "Influencer Planning": row.influencer_planning,
            "Influencer Live": row.influencer_live,
            "Influencer Recapping": row.influencer_recapping,
            "Reporting Requests": row.reporting_requests,
            "Insights Projects": row.insights_projects,
            "Retail Media Campaigns": row.retail_media_campaigns,
            "Content Programs": row.content_programs,
        }
        for row in summary.workload
    ], "No workload rows.")
    c1, c2 = st.columns(2)
    if c1.button("Open My Work", key="campaign_ops_cross_team_open_my_work"):
        set_section(st.session_state, "My Work")
        st.rerun()
    if c2.button("Open My Programs", key="campaign_ops_cross_team_open_my_programs"):
        set_section(st.session_state, "My Programs")
        st.rerun()


def _render_cards(title: str, cards: list[Any]) -> None:
    if not cards:
        return
    render_section_header(title, "Showing up to two priority records by default.", len(cards))
    cols = st.columns(min(2, len(cards)))
    for idx, card in enumerate(cards[:2]):
        with cols[idx % len(cols)]:
            st.markdown("<div class='campaign-ops-card'>", unsafe_allow_html=True)
            st.markdown(f"**{display_record_title(card.title)}**")
            st.caption(f"{card.client_name or 'Not set'} | {status_label(card.stage)} | {status_label(card.status)}")
            render_status_badges(card.risk, "needs_attention" if card.needs_attention else None)
            st.write(card.latest_update or "No latest update.")
            st.write(f"Waiting: {readable_label(card.waiting_on)}")
            st.write(f"Next: {card.next_item or 'Not set'} ({format_display_date(card.next_date)})")
            st.write(card.details or "")
            if st.button(f"Open {title} Workspace", key=f"campaign_ops_cross_team_open_card_{card.workflow}_{card.id}", use_container_width=True):
                _drill_to(card.program_id, card.target_section, card.id)
            st.markdown("</div>", unsafe_allow_html=True)
    if len(cards) > 2:
        st.caption(f"{len(cards) - 2} more matching records. Use the workflow section for the full list.")


def _render_program_table(summary: CrossTeamDashboardSummary) -> None:
    render_section_header("All Programs", "Dense operational table for matching programs.", len(summary.programs))
    rows = [
        {
            "Program": display_record_title(row.program_name),
            "Client": row.client_name or "-",
            "Primary Workflow": readable_label(row.primary_workflow),
            "Connected Workstreams": ", ".join(readable_label(item) for item in row.connected_workstreams),
            "Program Status": status_label(row.program_status),
            "Cross Stage": status_label(row.cross_stage),
            "Specialized Stage": row.specialized_stage or "-",
            "Risk": status_label(row.risk),
            "Priority": row.priority or "-",
            "Primary Owner": row.primary_owner_name or "-",
            "Assigned People": ", ".join(row.assigned_people),
            "Latest Update": row.latest_update or "-",
            "Waiting On": readable_label(row.waiting_on),
            "Open Tasks": row.open_tasks,
            "Overdue Tasks": row.overdue_tasks,
            "Next Task Due": format_display_date(row.next_task_due),
            "Next Milestone": row.next_milestone or "-",
            "Needs Attention Reasons": ", ".join(row.needs_attention_reasons),
            "Start Date": format_display_date(row.start_date),
            "Target End Date": format_display_date(row.target_end_date),
            "Updated Date": format_display_date(row.updated_at),
            "Active State": row.active_state,
        }
        for row in summary.programs
    ]
    _table(rows[:250], "No programs match the selected dashboard filters.")
    if rows:
        st.download_button("Export CSV", csv_rows(rows), file_name="campaign_ops_cross_team_programs.csv", mime="text/csv", key="campaign_ops_cross_team_export_csv")
        options = {row.program_name: row.id for row in summary.programs}
        selected = st.selectbox("Open Program", list(options), key="campaign_ops_cross_team_open_program_select")
        if st.button("Open Program Workspace", key="campaign_ops_cross_team_open_program"):
            _drill_to(options[selected], "Program Workspace")


def render_cross_team_dashboard(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    render_page_header(
        "Cross-Team Dashboard",
        "Operational view over Campaign Operations programs, workflows, tasks, milestones, requests, resources, and waiting states.",
        viewer_context=f"Viewing as {actor.display_name}",
        active_module="Cross-Team",
    )
    filters = _render_filters(service, actor, users)
    try:
        summary = service.get_cross_team_dashboard_summary(actor, filters)
    except CampaignOpsError as exc:
        st.error(f"Cross-Team Dashboard could not load: {exc}")
        return
    if not summary.programs:
        render_empty_state("no filter matches", "No programs match the selected dashboard filters.")
    _render_metrics(summary)
    _render_attention(summary)
    _render_waiting(summary)
    _render_operational_tables(summary)
    _render_workload(summary)
    _render_cards("Influencer", summary.influencer_cards)
    _render_cards("Retail Media", summary.retail_media_cards)
    _render_cards("eCommerce / Content Management", summary.content_cards)
    _render_cards("Insights", summary.insights_cards)
    _render_cards("Reporting & Survey Requests", summary.request_cards)
    _render_program_table(summary)
