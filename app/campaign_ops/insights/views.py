from __future__ import annotations

from html import escape
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.formatting import RISK_LABELS, STATUS_LABELS, WORKFLOW_LABELS, format_date, format_datetime, safe_text
from app.campaign_ops.insights.formatting import (
    PORTFOLIO_COLUMNS,
    format_currency,
    insights_status_label,
    portfolio_rows,
    quick_link_label,
    timeline_date_label,
)
from app.campaign_ops.resource_views import render_resource_actions, resource_table_rows
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import RiskLevel, TaskStatus, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.insights import INSIGHTS_RESOURCE_TYPES, INSIGHTS_STATUSES, INSIGHTS_STATUS_NOT_STARTED
from core.campaign_ops.models import CampaignOpsUser, InsightsPortfolioRow, MilestoneListRow
from core.campaign_ops.service import CampaignOpsService

SORT_OPTIONS = {
    "Recently updated": "updated_at",
    "Project name": "project_title",
    "Client": "client_name",
    "Owner": "owner_display_name",
    "Status": "insights_status",
    "Next milestone": "next_milestone_date",
    "Risk": "program_risk",
}


def render_insights(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
) -> None:
    st.subheader("Insights")
    render_insights_css()
    selected_id = st.session_state.get("campaign_ops_selected_insights_project_id")
    if selected_id:
        render_insights_workspace(actor, service, users, str(selected_id))
        return
    view = st.radio("Insights view", ["Insights Portfolio", "New Insights Project"], horizontal=True, key="campaign_ops_insights_view")
    if view == "New Insights Project" or st.session_state.get("campaign_ops_insights_create_open"):
        render_new_project_form(actor, service, users)
        return
    render_portfolio(actor, service)


def render_insights_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-insights-title {
            background: #3aa6a6;
            color: #102222;
            text-align: center;
            font-weight: 700;
            padding: 0.35rem;
            border: 1px solid #6fbfbf;
        }
        .campaign-ops-highlight {
            background: #fff3b0;
            border: 1px solid #e0c85a;
            padding: 0.3rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_portfolio(actor: CampaignOpsUser, service: CampaignOpsService) -> None:
    cols = st.columns(4)
    if cols[0].button("New Insights Project", type="primary", key="campaign_ops_insights_new_project"):
        st.session_state["campaign_ops_insights_create_open"] = True
        st.rerun()
    include_inactive = cols[1].checkbox("Show inactive", key="campaign_ops_insights_show_inactive")
    if cols[2].button("Refresh", key="campaign_ops_insights_refresh"):
        st.rerun()
    if cols[3].button("Clear filters", key="campaign_ops_insights_clear_filters"):
        st.session_state["campaign_ops_insights_filters"] = {}
        st.rerun()
    try:
        projects = service.list_insights_projects(actor, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load Insights projects: {exc}")
        return
    filters = render_portfolio_filters(projects)
    filtered = sort_projects(filter_projects(projects, filters), str(filters.get("sort_by") or "updated_at"))
    render_workbook_table("Insights Portfolio", portfolio_rows(filtered), PORTFOLIO_COLUMNS)
    if not filtered:
        return
    labels = {f"{project.project_title} | {safe_text(project.client_name)}": project.id for project in filtered}
    cols = st.columns(2)
    selected = cols[0].selectbox("Open Insights project", list(labels), key="campaign_ops_insights_project_select")
    if cols[1].button("Open Project", key="campaign_ops_insights_project_open"):
        st.session_state["campaign_ops_selected_insights_project_id"] = labels[selected]
        st.rerun()


def render_portfolio_filters(projects: list[InsightsPortfolioRow]) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_insights_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Insights filters", expanded=True):
        cols = st.columns(4)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_insights_filter_search")
        clients = {"Any": "", **{safe_text(project.client_name): project.client_name for project in projects if project.client_name}}
        current["client_name"] = clients[cols[1].selectbox("Client", list(clients), key="campaign_ops_insights_filter_client")]
        owners = {"Any": "", **{safe_text(project.owner_display_name): project.owner_user_id for project in projects if project.owner_user_id}}
        current["owner_user_id"] = owners[cols[2].selectbox("Owner", list(owners), key="campaign_ops_insights_filter_owner")]
        current["sort_by"] = SORT_OPTIONS[cols[3].selectbox("Sort", list(SORT_OPTIONS), key="campaign_ops_insights_filter_sort")]
        cols = st.columns(2)
        current["insights_status"] = cols[0].selectbox("Status", ["Any", *sorted(INSIGHTS_STATUSES)], key="campaign_ops_insights_filter_status")
        current["program_risk"] = cols[1].selectbox("Risk", ["Any", *RISK_LABELS], key="campaign_ops_insights_filter_risk")
    st.session_state["campaign_ops_insights_filters"] = current
    return current


def filter_projects(projects: list[InsightsPortfolioRow], filters: dict[str, object]) -> list[InsightsPortfolioRow]:
    result = projects
    search = str(filters.get("search") or "").strip().lower()
    if search:
        result = [project for project in result if search in project.project_title.lower() or search in project.program_name.lower() or search in (project.client_name or "").lower()]
    for field in ("client_name", "owner_user_id", "insights_status", "program_risk"):
        value = filters.get(field)
        if value and value != "Any":
            result = [project for project in result if getattr(project, field) == value]
    return result


def sort_projects(projects: list[InsightsPortfolioRow], sort_by: str) -> list[InsightsPortfolioRow]:
    return sorted(projects, key=lambda project: (getattr(project, sort_by, None) is None, str(getattr(project, sort_by, "") or ""), project.project_title.lower()), reverse=sort_by == "updated_at")


def render_workbook_table(title: str, rows: list[dict[str, str]], columns: list[str]) -> None:
    st.markdown(f"<div class='campaign-ops-insights-title'>{title}</div>", unsafe_allow_html=True)
    ordered = [{column: row.get(column, "") for column in columns} for row in rows]
    if ordered:
        st.dataframe(ordered, hide_index=True, use_container_width=True)
    else:
        st.info(f"No {title.lower()} records match this view.")


def render_new_project_form(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    if st.button("Back to Insights Portfolio", key="campaign_ops_insights_create_back"):
        st.session_state["campaign_ops_insights_create_open"] = False
        st.rerun()
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    program_options = {program.program_name: program.id for program in programs}
    user_options = {"Unassigned": None, **{user.display_name: user.id for user in users if user.is_active}}
    if not program_options:
        st.warning("No active programs are available.")
        return
    with st.form("campaign_ops_insights_create_form"):
        cols = st.columns(3)
        program_label = cols[0].selectbox("Existing Program", list(program_options))
        owner_label = cols[1].selectbox("Owner", list(user_options))
        status = cols[2].selectbox("Insights Status", sorted(INSIGHTS_STATUSES), index=sorted(INSIGHTS_STATUSES).index(INSIGHTS_STATUS_NOT_STARTED), format_func=insights_status_label)
        cols = st.columns(3)
        job_number = cols[0].text_input("Job Number")
        project_title = cols[1].text_input("Project Title")
        latest_update = cols[2].text_input("Latest Update")
        cols = st.columns(3)
        total_program_cost = cols[0].number_input("Total Program Cost", min_value=0.0, value=0.0)
        sample_size = cols[1].number_input("Sample Size", min_value=0, value=0)
        budget = cols[2].number_input("Budget", min_value=0.0, value=0.0)
        cols = st.columns(3)
        tracksheet = cols[0].text_input("Tracksheet URL")
        results_deck = cols[1].text_input("Results Deck URL")
        raw_data = cols[2].text_input("Raw Data URL")
        objectives = st.text_area("Initial research objectives", height=160)
        submitted = st.form_submit_button("Create Insights Project", type="primary")
    if not submitted:
        return
    initial_resources = {k: v for k, v in {"Tracksheet": trim_or_none(tracksheet), "Results Deck": trim_or_none(results_deck), "Raw Data": trim_or_none(raw_data)}.items() if v}
    initial_objectives = [line.strip() for line in objectives.splitlines() if line.strip()]
    try:
        project = service.create_insights_project(
            actor,
            program_id=program_options[program_label],
            project_title=project_title,
            owner_user_id=user_options[owner_label],
            insights_status=status,
            latest_update=trim_or_none(latest_update),
            job_number=trim_or_none(job_number),
            total_program_cost=total_program_cost,
            sample_size=sample_size,
            budget=budget,
            initial_resources=initial_resources,
            initial_objectives=initial_objectives,
        )
    except CampaignOpsError as exc:
        st.error(f"Insights project was not created: {exc}")
        return
    st.session_state["campaign_ops_selected_insights_project_id"] = project.id
    st.session_state["campaign_ops_insights_create_open"] = False
    st.success("Insights project created.")
    st.rerun()


def render_insights_workspace(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], project_id: str) -> None:
    try:
        project = service.get_insights_project_detail(actor, project_id)
    except CampaignOpsError as exc:
        st.session_state.pop("campaign_ops_selected_insights_project_id", None)
        st.error(f"Insights project unavailable: {exc}")
        return
    if st.button("Back to Insights Portfolio", key="campaign_ops_insights_workspace_back"):
        st.session_state.pop("campaign_ops_selected_insights_project_id", None)
        st.rerun()
    cols = st.columns(2)
    if cols[0].button("Open Program Workspace", key=f"campaign_ops_insights_open_program_{project.id}"):
        set_selected_program(st.session_state, project.program_id)
        st.rerun()
    st.markdown(f"### {project.project_title}")
    st.caption(
        f"Client: {safe_text(project.client_name)} | Job: {safe_text(project.job_number)} | "
        f"Owner: {safe_text(project.owner_display_name)} | Status: {insights_status_label(project.insights_status)} | "
        f"Latest: {safe_text(project.latest_update)} | Next: {safe_text(project.next_milestone)} | "
        f"Risk: {RISK_LABELS.get(project.program_risk, project.program_risk)} | Updated: {format_datetime(project.updated_at)} | "
        f"{'Active' if project.is_active else 'Inactive'}"
    )
    tabs = st.tabs(["Overview", "Timeline", "Research Objectives", "Resources", "Activity"])
    with tabs[0]:
        render_overview(actor, service, users, project)
    with tabs[1]:
        render_timeline(actor, service, project)
    with tabs[2]:
        render_objectives(actor, service, project)
    with tabs[3]:
        render_resources(actor, service, project)
    with tabs[4]:
        render_activity(actor, service, project)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], project: InsightsPortfolioRow) -> None:
    user_options = {"Unassigned": None, **{user.display_name: user.id for user in users if user.is_active}}
    current_owner = next((name for name, user_id in user_options.items() if user_id == project.owner_user_id), "Unassigned")
    with st.form(f"campaign_ops_insights_overview_form_{project.id}"):
        cols = st.columns(3)
        job_number = cols[0].text_input("Job Number", value=project.job_number or "")
        project_title = cols[1].text_input("Project", value=project.project_title)
        owner_label = cols[2].selectbox("Owner", list(user_options), index=list(user_options).index(current_owner))
        cols = st.columns(3)
        total_program_cost = cols[0].number_input("Total Program Cost", min_value=0.0, value=float(project.total_program_cost or 0))
        sample_size = cols[1].number_input("Sample Size", min_value=0, value=int(project.sample_size or 0))
        budget = cols[2].number_input("Budget", min_value=0.0, value=float(project.budget or 0))
        cols = st.columns(2)
        status = cols[0].selectbox("Insights Status", sorted(INSIGHTS_STATUSES), index=sorted(INSIGHTS_STATUSES).index(project.insights_status or INSIGHTS_STATUS_NOT_STARTED), format_func=insights_status_label)
        latest_update = cols[1].text_input("Latest Update", value=project.latest_update or "")
        submitted = st.form_submit_button("Save Overview", type="primary")
    st.caption(f"Program: {project.program_name} | Client: {safe_text(project.client_name)} | Workstream: {safe_text(project.workstream_id)} | Program status: {STATUS_LABELS.get(project.program_status, project.program_status)} | Program risk: {RISK_LABELS.get(project.program_risk, project.program_risk)}")
    st.caption(f"Total Program Cost: {format_currency(project.total_program_cost)} | Budget: {format_currency(project.budget)} | Sample Size: {safe_text(project.sample_size)}")
    if submitted:
        try:
            service.update_insights_project(actor, project.id, job_number=trim_or_none(job_number), project_title=project_title, owner_user_id=user_options[owner_label], total_program_cost=total_program_cost, sample_size=sample_size, budget=budget, insights_status=status, latest_update=trim_or_none(latest_update))
        except CampaignOpsError as exc:
            st.error(f"Overview was not saved: {exc}")
            return
        st.success("Overview saved.")
        st.rerun()
    render_project_state_actions(actor, service, project)


def render_timeline(actor: CampaignOpsUser, service: CampaignOpsService, project: InsightsPortfolioRow) -> None:
    st.markdown("<div class='campaign-ops-insights-title'>Timeline</div>", unsafe_allow_html=True)
    include_inactive = st.checkbox("Show inactive milestones", key="campaign_ops_insights_timeline_show_inactive")
    with st.expander("Add Timeline Milestone", expanded=False):
        with st.form(f"campaign_ops_insights_timeline_add_{project.id}"):
            title = st.text_input("Milestone Description")
            cols = st.columns(4)
            target_date = cols[0].date_input("Exact date", value=None)
            start_date = cols[1].date_input("Start date", value=None)
            end_date = cols[2].date_input("End date", value=None)
            is_highlighted = cols[3].checkbox("Highlighted/key milestone")
            submitted = st.form_submit_button("Add Milestone", type="primary")
        if submitted:
            try:
                service.create_milestone(actor, project.program_id, title, workstream_id=project.workstream_id, milestone_type="Insights", target_date=target_date, start_date=start_date, end_date=end_date, is_highlighted=is_highlighted)
            except CampaignOpsError as exc:
                st.error(f"Milestone was not added: {exc}")
                return
            st.success("Milestone added.")
            st.rerun()
    milestones = [m for m in service.list_program_milestones(actor, project.program_id, include_inactive=include_inactive) if m.milestone_type == "Insights" or m.workstream_id == project.workstream_id]
    milestones = sorted(milestones, key=lambda m: ((m.target_date or m.start_date or m.end_date) is None, m.target_date or m.start_date or m.end_date or "", m.title))
    for milestone in milestones:
        style = "campaign-ops-highlight" if milestone.is_highlighted else ""
        st.markdown(f"<div class='{style}'><b>{escape(timeline_date_label(milestone))}</b> &nbsp; {escape(milestone.title)}</div>", unsafe_allow_html=True)
        cols = st.columns(5)
        cols[0].caption(f"Owner: {safe_text(milestone.owner_user_name)}")
        cols[1].caption(f"Status: {milestone.status.replace('_', ' ').title()}")
        if cols[2].button("Highlight" if not milestone.is_highlighted else "Unhighlight", key=f"campaign_ops_insights_highlight_{milestone.id}"):
            service.update_milestone_details(actor, milestone.id, is_highlighted=not milestone.is_highlighted)
            st.rerun()
        if milestone.status != TaskStatus.COMPLETED.value and cols[3].button("Complete", key=f"campaign_ops_insights_complete_{milestone.id}"):
            service.complete_milestone(actor, milestone.id)
            st.rerun()
        if milestone.status == TaskStatus.COMPLETED.value and cols[3].button("Reopen", key=f"campaign_ops_insights_reopen_{milestone.id}"):
            service.reopen_milestone(actor, milestone.id)
            st.rerun()
        if milestone.is_active and cols[4].button("Deactivate", key=f"campaign_ops_insights_milestone_deactivate_{milestone.id}"):
            service.deactivate_milestone(actor, milestone.id)
            st.rerun()
        if not milestone.is_active and cols[4].button("Reactivate", key=f"campaign_ops_insights_milestone_reactivate_{milestone.id}"):
            service.reactivate_milestone(actor, milestone.id)
            st.rerun()


def render_objectives(actor: CampaignOpsUser, service: CampaignOpsService, project: InsightsPortfolioRow) -> None:
    st.markdown("<div class='campaign-ops-insights-title'>Research Objectives</div>", unsafe_allow_html=True)
    include_inactive = st.checkbox("Show inactive objectives", key="campaign_ops_insights_objectives_show_inactive")
    with st.form(f"campaign_ops_insights_objective_add_{project.id}"):
        objective_text = st.text_area("Add objective", height=100)
        sort_order = st.number_input("Sort order", min_value=0, value=0)
        submitted = st.form_submit_button("Add Objective", type="primary")
    if submitted:
        try:
            service.add_insights_objective(actor, project.id, objective_text, int(sort_order))
        except CampaignOpsError as exc:
            st.error(f"Objective was not added: {exc}")
            return
        st.rerun()
    objectives = service.list_insights_objectives(actor, project.id, include_inactive=include_inactive)
    for objective in objectives:
        with st.expander(f"{objective.sort_order}. {objective.objective_text}", expanded=False):
            text = st.text_area("Objective", value=objective.objective_text, key=f"campaign_ops_insights_objective_text_{objective.id}")
            order = st.number_input("Sort order", min_value=0, value=objective.sort_order, key=f"campaign_ops_insights_objective_order_{objective.id}")
            cols = st.columns(3)
            if cols[0].button("Save Objective", key=f"campaign_ops_insights_objective_save_{objective.id}"):
                service.update_insights_objective(actor, project.id, objective.id, text, int(order))
                st.rerun()
            if objective.is_active and cols[1].button("Deactivate", key=f"campaign_ops_insights_objective_deactivate_{objective.id}"):
                service.deactivate_insights_objective(actor, project.id, objective.id)
                st.rerun()
            if not objective.is_active and cols[2].button("Reactivate", key=f"campaign_ops_insights_objective_reactivate_{objective.id}"):
                service.reactivate_insights_objective(actor, project.id, objective.id)
                st.rerun()


def render_resources(actor: CampaignOpsUser, service: CampaignOpsService, project: InsightsPortfolioRow) -> None:
    st.markdown("<div class='campaign-ops-insights-title'>Resources</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for idx, (label, url) in enumerate((("Tracksheet", project.tracksheet_url), ("Results Deck", project.results_deck_url), ("Raw Data", project.raw_data_url))):
        if url:
            cols[idx].link_button(label, sanitize_link(url), key=f"campaign_ops_insights_quick_link_{label}_{project.id}")
        else:
            cols[idx].metric(label, quick_link_label(url))
    summary = service.get_program_workspace_summary(actor, project.program_id)
    resources = [r for r in service.list_program_resources(actor, project.program_id, include_inactive=True) if r.resource_type in INSIGHTS_RESOURCE_TYPES or r.workstream_id == project.workstream_id]
    if resources:
        st.dataframe(resource_table_rows(resources), hide_index=True, use_container_width=True)
    with st.expander("Add Resource", expanded=False):
        render_insights_resource_form(actor, service, project)
    for resource in resources:
        render_resource_actions(actor, service, summary, resource)


def render_insights_resource_form(actor: CampaignOpsUser, service: CampaignOpsService, project: InsightsPortfolioRow) -> None:
    with st.form(f"campaign_ops_insights_resource_form_{project.id}"):
        title = st.text_input("Title")
        resource_type = st.selectbox("Resource type", INSIGHTS_RESOURCE_TYPES)
        url = st.text_input("URL")
        is_required = st.checkbox("Required")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Create Resource", type="primary")
    if not submitted:
        return
    try:
        service.create_resource(
            actor,
            project.program_id,
            title=title,
            resource_type=resource_type,
            workstream_id=project.workstream_id,
            url=trim_or_none(url),
            is_required=is_required,
            notes=trim_or_none(notes),
        )
    except CampaignOpsError as exc:
        st.error(f"Resource was not created: {exc}")
        return
    st.success("Resource created.")
    st.rerun()


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, project: InsightsPortfolioRow) -> None:
    summary = service.get_program_workspace_summary(actor, project.program_id)
    rows = [
        {"Timestamp": format_datetime(event.created_at), "Event": event.event_type.replace("_", " ").title(), "Message": safe_text(event.message)}
        for event in summary.activity
        if event.event_type.startswith("insights_") or event.entity_type in {"insights_project", "insights_objective"}
    ]
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No Insights activity recorded yet.")


def render_project_state_actions(actor: CampaignOpsUser, service: CampaignOpsService, project: InsightsPortfolioRow) -> None:
    cols = st.columns(2)
    if project.is_active and cols[0].button("Deactivate Insights Project", key=f"campaign_ops_insights_deactivate_{project.id}"):
        service.deactivate_insights_project(actor, project.id)
        st.rerun()
    if not project.is_active and cols[1].button("Reactivate Insights Project", key=f"campaign_ops_insights_reactivate_{project.id}"):
        service.reactivate_insights_project(actor, project.id)
        st.rerun()


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
