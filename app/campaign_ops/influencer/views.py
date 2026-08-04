from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.formatting import RISK_LABELS, format_date, format_datetime, safe_text, title_label
from app.campaign_ops.influencer.formatting import PORTFOLIO_COLUMNS, planning_portfolio_rows, status_label
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.resource_views import render_resource_actions, resource_table_rows
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer import (
    APPROVAL_TYPES,
    CONTENT_ROUND_TYPES,
    INFLUENCER_RESOURCE_TYPES,
    INFLUENCER_STAGES,
    PLANNING_STATUSES,
    RESPONSIBLE_PARTIES,
)
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.service import CampaignOpsService

SORT_OPTIONS = {
    "Recently updated": "updated_at",
    "Campaign name": "campaign_title",
    "Client": "client_name",
    "Manager": "manager_display_name",
    "Planning status": "planning_status",
    "Next planning step": "next_planning_step",
    "Next due date": "next_planning_step_due_date",
    "Launch date": "launch_date",
    "Hold state": "is_on_hold",
    "Risk": "program_risk",
}


def render_influencer(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    render_css()
    st.subheader("Influencer")
    section = st.radio("Influencer workspace", ["Planning", "Live", "Recapping"], horizontal=True, key="campaign_ops_influencer_view")
    if section == "Live":
        st.info("Influencer Live will use the shared Influencer campaign records in a later pass.")
        return
    if section == "Recapping":
        st.info("Influencer Recapping will extend the same Influencer campaign records in a later pass.")
        return
    selected_id = st.session_state.get("campaign_ops_selected_influencer_campaign_id")
    if selected_id:
        render_workspace(actor, service, users, str(selected_id))
        return
    render_planning(actor, service, users)


def render_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-influencer-title { background:#2fa6a3; color:#082525; text-align:center; font-weight:700; padding:.35rem; border:1px solid #64bfbd; }
        .campaign-ops-influencer-block { border:1px solid #c9d4d4; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-influencer-bar { background:#06314a; color:white; padding:.35rem .55rem; font-weight:700; }
        .campaign-ops-influencer-row { border-top:1px solid #dbe4e4; padding:.32rem .55rem; font-size:.9rem; }
        .campaign-ops-influencer-hold { color:#a00000; font-weight:700; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_planning(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    tabs = st.radio("Planning view", ["All Planning", "T - In Planning", "L - In Planning", "New Influencer Campaign"], horizontal=True, key="campaign_ops_influencer_planning_view")
    if tabs == "New Influencer Campaign" or st.session_state.get("campaign_ops_influencer_create_open"):
        render_new_campaign(actor, service, users)
        return
    manager_id = None
    if tabs.startswith("T"):
        manager_id = next((u.id for u in users if u.display_name == "T"), None)
    if tabs.startswith("L"):
        manager_id = next((u.id for u in users if u.display_name == "L"), None)
    render_portfolio(actor, service, manager_id)


def render_portfolio(actor: CampaignOpsUser, service: CampaignOpsService, manager_user_id: str | None) -> None:
    cols = st.columns(4)
    if cols[0].button("New Influencer Campaign", type="primary", key="campaign_ops_influencer_new"):
        st.session_state["campaign_ops_influencer_create_open"] = True
        st.rerun()
    include_inactive = cols[1].checkbox("Show inactive", key="campaign_ops_influencer_show_inactive")
    if cols[2].button("Refresh", key="campaign_ops_influencer_refresh"):
        st.rerun()
    if cols[3].button("Clear filters", key="campaign_ops_influencer_clear_filters"):
        st.session_state["campaign_ops_influencer_filters"] = {}
        st.rerun()
    try:
        campaigns = service.list_influencer_campaigns(actor, include_inactive=include_inactive, manager_user_id=manager_user_id)
    except CampaignOpsError as exc:
        st.error(f"Unable to load Influencer Planning: {exc}")
        return
    filters = render_filters(campaigns)
    campaigns = sort_campaigns(filter_campaigns(campaigns, filters), str(filters.get("sort_by") or "updated_at"))
    st.markdown("<div class='campaign-ops-influencer-title'>Influencer Planning Portfolio</div>", unsafe_allow_html=True)
    st.dataframe(planning_portfolio_rows(campaigns), column_order=PORTFOLIO_COLUMNS, hide_index=True, use_container_width=True)
    for campaign in campaigns:
        render_campaign_block(campaign)
    if campaigns:
        labels = {f"{item.campaign_title} | {safe_text(item.client_name)}": item.id for item in campaigns}
        cols = st.columns(2)
        chosen = cols[0].selectbox("Open Influencer Campaign", list(labels), key="campaign_ops_influencer_campaign_select")
        if cols[1].button("Open Campaign", key="campaign_ops_influencer_campaign_open"):
            st.session_state["campaign_ops_selected_influencer_campaign_id"] = labels[chosen]
            st.rerun()


def render_filters(campaigns: list[Any]) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_influencer_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Planning filters", expanded=True):
        cols = st.columns(5)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_influencer_filter_search")
        clients = {"Any": "", **{safe_text(c.client_name): c.client_name for c in campaigns if c.client_name}}
        current["client_name"] = clients[cols[1].selectbox("Client", list(clients), key="campaign_ops_influencer_filter_client")]
        programs = {"Any": "", **{c.program_name: c.program_id for c in campaigns}}
        current["program_id"] = programs[cols[2].selectbox("Program", list(programs), key="campaign_ops_influencer_filter_program")]
        managers = {"Any": "", **{safe_text(c.manager_display_name): c.manager_user_id for c in campaigns if c.manager_user_id}}
        current["manager_user_id"] = managers[cols[3].selectbox("Manager", list(managers), key="campaign_ops_influencer_filter_manager")]
        current["sort_by"] = SORT_OPTIONS[cols[4].selectbox("Sort", list(SORT_OPTIONS), key="campaign_ops_influencer_filter_sort")]
        cols = st.columns(5)
        current["planning_status"] = cols[0].selectbox("Planning status", ["Any", *PLANNING_STATUSES], key="campaign_ops_influencer_filter_status", format_func=status_label)
        current["waiting_on"] = cols[1].text_input("Waiting on", value=str(current.get("waiting_on", "")), key="campaign_ops_influencer_filter_waiting")
        current["hold"] = cols[2].selectbox("On Hold", ["Any", "On Hold", "Not on hold"], key="campaign_ops_influencer_filter_hold")
        current["launch_from"] = cols[3].date_input("Launch from", value=current.get("launch_from"), key="campaign_ops_influencer_filter_launch_from")
        current["launch_to"] = cols[4].date_input("Launch to", value=current.get("launch_to"), key="campaign_ops_influencer_filter_launch_to")
    st.session_state["campaign_ops_influencer_filters"] = current
    return current


def filter_campaigns(campaigns: list[Any], filters: dict[str, object]) -> list[Any]:
    rows = campaigns
    search = str(filters.get("search") or "").lower()
    if search:
        rows = [c for c in rows if search in " ".join([c.campaign_title, c.program_name, safe_text(c.client_name), safe_text(c.latest_update)]).lower()]
    for field in ("client_name", "program_id", "manager_user_id", "planning_status"):
        value = filters.get(field)
        if value and value != "Any":
            rows = [c for c in rows if getattr(c, field) == value]
    waiting = str(filters.get("waiting_on") or "").lower()
    if waiting:
        rows = [c for c in rows if waiting in safe_text(c.waiting_on).lower()]
    if filters.get("hold") == "On Hold":
        rows = [c for c in rows if c.is_on_hold]
    if filters.get("hold") == "Not on hold":
        rows = [c for c in rows if not c.is_on_hold]
    launch_from = filters.get("launch_from")
    launch_to = filters.get("launch_to")
    if launch_from:
        rows = [c for c in rows if c.launch_date and c.launch_date >= launch_from]
    if launch_to:
        rows = [c for c in rows if c.launch_date and c.launch_date <= launch_to]
    return rows


def sort_campaigns(campaigns: list[Any], sort_by: str) -> list[Any]:
    return sorted(campaigns, key=lambda c: (getattr(c, sort_by, None) is None, getattr(c, sort_by, None) or "", c.campaign_title))


def render_campaign_block(campaign: Any) -> None:
    hold = f" <span class='campaign-ops-influencer-hold'>ON HOLD: {escape(safe_text(campaign.hold_reason))}</span>" if campaign.is_on_hold else ""
    html = f"<div class='campaign-ops-influencer-block'><div class='campaign-ops-influencer-bar'>{escape(campaign.campaign_title)}{hold}</div>"
    rows = [
        f"Manager: {escape(safe_text(campaign.manager_display_name))} | Status: {escape(status_label(campaign.planning_status))} | Waiting on: {escape(safe_text(campaign.waiting_on))}",
        f"Next: {escape(safe_text(campaign.next_planning_step))} | Due: {format_date(campaign.next_planning_step_due_date)} | Launch: {format_date(campaign.launch_date)} | Wrap: {format_date(campaign.wrap_date)}",
        f"Creators: target {safe_text(campaign.target_creator_count)} | approved {safe_text(campaign.approved_creator_count)} | contracted {safe_text(campaign.contracted_creator_count)}",
        f"Invoice: {format_date(campaign.invoice_date)} | {escape(safe_text(campaign.invoice_status))} | {safe_text(campaign.invoice_amount)}",
    ]
    html += "".join(f"<div class='campaign-ops-influencer-row'>{row}</div>" for row in rows)
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_new_campaign(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    if st.button("Back to Influencer Planning", key="campaign_ops_influencer_create_back"):
        st.session_state["campaign_ops_influencer_create_open"] = False
        st.rerun()
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    program_options = {f"{p.program_name} | {safe_text(p.client_name)}": p.id for p in programs}
    user_options = {"": None, **{u.display_name: u.id for u in users if u.is_active}}
    with st.form("campaign_ops_influencer_create_form"):
        cols = st.columns(3)
        program_label = cols[0].selectbox("Existing Program", list(program_options))
        title = cols[1].text_input("Influencer Campaign Title")
        manager_label = cols[2].selectbox("Manager", list(user_options))
        cols = st.columns(4)
        stage = cols[0].selectbox("Stage", INFLUENCER_STAGES, format_func=status_label)
        planning_status = cols[1].selectbox("Planning Status", PLANNING_STATUSES, format_func=status_label)
        waiting_on = cols[2].text_input("Waiting On")
        on_hold = cols[3].checkbox("On Hold")
        hold_reason = st.text_input("Hold Reason")
        latest = st.text_area("Latest Update")
        cols = st.columns(4)
        app_open = cols[0].date_input("Application Open Date", value=None)
        app_close = cols[1].date_input("Application Close Date", value=None)
        influencer_due = cols[2].date_input("Influencer Approval Due Date", value=None)
        scripts_due = cols[3].date_input("Scripts Due Date", value=None)
        cols = st.columns(4)
        first_content = cols[0].date_input("First Content Due Date", value=None)
        launch = cols[1].date_input("Launch Date", value=None)
        wrap = cols[2].date_input("Wrap Date", value=None)
        invoice_date = cols[3].date_input("Invoice Date", value=None)
        cols = st.columns(4)
        invoice_status = cols[0].text_input("Invoice Status")
        invoice_amount = cols[1].number_input("Invoice Amount", min_value=0.0, value=0.0)
        target = cols[2].number_input("Target Creator Count", min_value=0, value=0)
        approved = cols[3].number_input("Approved Creator Count", min_value=0, value=0)
        contracted = st.number_input("Contracted Creator Count", min_value=0, value=0)
        use_template = st.checkbox("Create standard planning template")
        st.caption("Optional initial resources")
        resource_values = {resource_type: st.text_input(resource_type) for resource_type in INFLUENCER_RESOURCE_TYPES if resource_type != "Custom"}
        submitted = st.form_submit_button("Create Influencer Campaign", type="primary")
    if submitted:
        try:
            campaign = service.create_influencer_campaign(
                actor,
                program_id=program_options[program_label],
                campaign_title=title,
                manager_user_id=user_options[manager_label],
                influencer_stage=stage,
                planning_status=planning_status,
                latest_update=trim_or_none(latest),
                waiting_on=trim_or_none(waiting_on),
                is_on_hold=on_hold,
                hold_reason=trim_or_none(hold_reason),
                application_open_date=app_open,
                application_close_date=app_close,
                influencer_approval_due_date=influencer_due,
                scripts_due_date=scripts_due,
                first_content_due_date=first_content,
                launch_date=launch,
                wrap_date=wrap,
                invoice_date=invoice_date,
                invoice_status=trim_or_none(invoice_status),
                invoice_amount=invoice_amount,
                target_creator_count=target,
                approved_creator_count=approved,
                contracted_creator_count=contracted,
                initial_resources={key: trim_or_none(value) for key, value in resource_values.items()},
                use_standard_template=use_template,
            )
        except CampaignOpsError as exc:
            st.error(f"Influencer campaign was not created: {exc}")
            return
        st.session_state["campaign_ops_influencer_create_open"] = False
        st.session_state["campaign_ops_selected_influencer_campaign_id"] = campaign.id
        st.rerun()


def render_workspace(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign_id: str) -> None:
    try:
        campaign = service.get_influencer_campaign_detail(actor, campaign_id)
    except CampaignOpsError as exc:
        st.session_state.pop("campaign_ops_selected_influencer_campaign_id", None)
        st.warning(f"Influencer campaign is no longer available: {exc}")
        return
    if st.button("Back to Influencer Planning", key="campaign_ops_influencer_workspace_back"):
        st.session_state.pop("campaign_ops_selected_influencer_campaign_id", None)
        st.rerun()
    if st.button("Open Program Workspace", key=f"campaign_ops_influencer_open_program_{campaign.id}"):
        set_selected_program(st.session_state, campaign.program_id)
        st.rerun()
    hold = "ON HOLD" if campaign.is_on_hold else "Active"
    st.markdown(f"### {campaign.campaign_title}")
    st.caption(f"{safe_text(campaign.client_name)} | {campaign.program_name} | Manager: {safe_text(campaign.manager_display_name)} | {status_label(campaign.planning_status)} | {hold}")
    st.info(f"Next: {safe_text(campaign.next_planning_step)} | Due: {format_date(campaign.next_planning_step_due_date)} | Launch: {format_date(campaign.launch_date)} | Wrap: {format_date(campaign.wrap_date)} | Invoice: {format_date(campaign.invoice_date)} {safe_text(campaign.invoice_status)}")
    tabs = st.tabs(["Overview", "Planning Sequence", "Approvals", "Content Rounds", "Creator Summary", "Timeline", "Resources", "Program Notes", "Activity"])
    with tabs[0]:
        render_overview(actor, service, users, campaign)
    with tabs[1]:
        render_steps(actor, service, users, campaign)
    with tabs[2]:
        render_approvals(actor, service, campaign)
    with tabs[3]:
        render_content_rounds(actor, service, campaign)
    with tabs[4]:
        render_creator_summary(actor, service, campaign)
    with tabs[5]:
        render_timeline(actor, service, campaign)
    with tabs[6]:
        render_resources(actor, service, campaign)
    with tabs[7]:
        render_notes(actor, service, campaign.program_id, campaign.workstream_id)
    with tabs[8]:
        render_activity(actor, service, campaign)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any) -> None:
    user_options = {"": None, **{u.display_name: u.id for u in users if u.is_active}}
    reverse_users = {v: k for k, v in user_options.items()}
    with st.form(f"campaign_ops_influencer_overview_{campaign.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Campaign Title", value=campaign.campaign_title)
        manager = cols[1].selectbox("Manager", list(user_options), index=list(user_options).index(reverse_users.get(campaign.manager_user_id, "")))
        status = cols[2].selectbox("Planning Status", PLANNING_STATUSES, index=PLANNING_STATUSES.index(campaign.planning_status), format_func=status_label)
        cols = st.columns(4)
        stage = cols[0].selectbox("Stage", INFLUENCER_STAGES, index=INFLUENCER_STAGES.index(campaign.influencer_stage), format_func=status_label)
        waiting = cols[1].text_input("Waiting On", value=safe_text(campaign.waiting_on, ""))
        on_hold = cols[2].checkbox("On Hold", value=campaign.is_on_hold)
        hold_reason = cols[3].text_input("Hold Reason", value=safe_text(campaign.hold_reason, ""))
        latest = st.text_area("Latest Update", value=safe_text(campaign.latest_update, ""))
        cols = st.columns(4)
        launch = cols[0].date_input("Launch Date", value=campaign.launch_date)
        wrap = cols[1].date_input("Wrap Date", value=campaign.wrap_date)
        invoice_date = cols[2].date_input("Invoice Date", value=campaign.invoice_date)
        invoice_status = cols[3].text_input("Invoice Status", value=safe_text(campaign.invoice_status, ""))
        cols = st.columns(4)
        invoice_amount = cols[0].number_input("Invoice Amount", min_value=0.0, value=float(campaign.invoice_amount or 0))
        target = cols[1].number_input("Target Creators", min_value=0, value=int(campaign.target_creator_count or 0))
        approved = cols[2].number_input("Approved Creators", min_value=0, value=int(campaign.approved_creator_count or 0))
        contracted = cols[3].number_input("Contracted Creators", min_value=0, value=int(campaign.contracted_creator_count or 0))
        submitted = st.form_submit_button("Save Overview", type="primary")
    if submitted:
        service.update_influencer_campaign(actor, campaign.id, campaign_title=title, manager_user_id=user_options[manager], influencer_stage=stage, planning_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), is_on_hold=on_hold, hold_reason=trim_or_none(hold_reason), launch_date=launch, wrap_date=wrap, invoice_date=invoice_date, invoice_status=trim_or_none(invoice_status), invoice_amount=invoice_amount, target_creator_count=target, approved_creator_count=approved, contracted_creator_count=contracted)
        st.rerun()
    cols = st.columns(2)
    if campaign.is_active and cols[0].button("Deactivate Campaign", key=f"campaign_ops_influencer_deactivate_{campaign.id}"):
        service.deactivate_influencer_campaign(actor, campaign.id); st.rerun()
    if not campaign.is_active and cols[1].button("Reactivate Campaign", key=f"campaign_ops_influencer_reactivate_{campaign.id}"):
        service.reactivate_influencer_campaign(actor, campaign.id); st.rerun()


def render_steps(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any) -> None:
    if st.button("Create Standard Planning Template", key=f"campaign_ops_influencer_template_{campaign.id}"):
        service.create_standard_influencer_planning_template(actor, campaign.id); st.rerun()
    user_options = {"": None, **{u.display_name: u.id for u in users if u.is_active}}
    with st.form(f"campaign_ops_influencer_step_add_{campaign.id}"):
        cols = st.columns(5)
        title = cols[0].text_input("Planning Action")
        responsible = cols[1].selectbox("Responsible Party", ["", *RESPONSIBLE_PARTIES])
        assigned = cols[2].selectbox("Assigned User", list(user_options))
        due = cols[3].date_input("Due Date", value=None)
        order = cols[4].number_input("Sequence Order", min_value=0, value=0)
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Step", type="primary")
    if submitted:
        service.create_influencer_planning_step(actor, campaign.id, title, responsible_party=trim_or_none(responsible), assigned_user_id=user_options[assigned], due_date=due, sequence_order=order, notes=trim_or_none(notes), status="not_started")
        st.rerun()
    steps = service.list_influencer_planning_steps(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Date": format_date(s.due_date or s.start_date), "Planning Action": s.step_title, "Responsible Party": safe_text(s.responsible_party), "Status": status_label(s.status), "Completed": format_date(s.completed_date), "Waiting On": safe_text(s.waiting_on), "Notes": safe_text(s.notes), "Active State": "Active" if s.is_active else "Inactive"} for s in steps], hide_index=True, use_container_width=True)
    for step in steps:
        cols = st.columns(4)
        if not step.completed_date and cols[0].button("Complete", key=f"campaign_ops_influencer_step_complete_{step.id}"):
            service.complete_influencer_planning_step(actor, campaign.id, step.id); st.rerun()
        if step.completed_date and cols[1].button("Reopen", key=f"campaign_ops_influencer_step_reopen_{step.id}"):
            service.reopen_influencer_planning_step(actor, campaign.id, step.id); st.rerun()
        if step.is_active and cols[2].button("Deactivate", key=f"campaign_ops_influencer_step_deactivate_{step.id}"):
            service.deactivate_influencer_planning_step(actor, campaign.id, step.id); st.rerun()
        if not step.is_active and cols[3].button("Reactivate", key=f"campaign_ops_influencer_step_reactivate_{step.id}"):
            service.reactivate_influencer_planning_step(actor, campaign.id, step.id); st.rerun()


def render_approvals(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_approval_add_{campaign.id}"):
        cols = st.columns(4)
        approval_type = cols[0].selectbox("Approval Type", APPROVAL_TYPES)
        round_number = cols[1].number_input("Round Number", min_value=1, value=1)
        scope = cols[2].text_input("Approval Scope")
        due = cols[3].date_input("Feedback Due Date", value=None)
        submitted = st.form_submit_button("Add Approval", type="primary")
    if submitted:
        service.create_influencer_approval_round(actor, campaign.id, approval_type, round_number=round_number, approval_scope=trim_or_none(scope), feedback_due_date=due, status="not_sent")
        st.rerun()
    approvals = service.list_influencer_approval_rounds(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Type": a.approval_type, "Round": a.round_number, "Scope": safe_text(a.approval_scope), "Requested": format_date(a.requested_date), "Feedback Due": format_date(a.feedback_due_date), "Feedback Received": format_date(a.feedback_received_date), "Approved": format_date(a.approved_date), "Status": status_label(a.status), "Active State": "Active" if a.is_active else "Inactive"} for a in approvals], hide_index=True, use_container_width=True)
    for approval in approvals:
        cols = st.columns(6)
        if cols[0].button("Sent", key=f"campaign_ops_influencer_approval_sent_{approval.id}"):
            service.mark_influencer_approval_sent(actor, campaign.id, approval.id); st.rerun()
        if cols[1].button("Feedback", key=f"campaign_ops_influencer_approval_feedback_{approval.id}"):
            service.mark_influencer_approval_feedback_received(actor, campaign.id, approval.id); st.rerun()
        if cols[2].button("Approved", key=f"campaign_ops_influencer_approval_approved_{approval.id}"):
            service.mark_influencer_approval_approved(actor, campaign.id, approval.id); st.rerun()
        if cols[3].button("Reopen", key=f"campaign_ops_influencer_approval_reopen_{approval.id}"):
            service.reopen_influencer_approval_round(actor, campaign.id, approval.id); st.rerun()
        if approval.is_active and cols[4].button("Deactivate", key=f"campaign_ops_influencer_approval_deactivate_{approval.id}"):
            service.deactivate_influencer_approval_round(actor, campaign.id, approval.id); st.rerun()
        if not approval.is_active and cols[5].button("Reactivate", key=f"campaign_ops_influencer_approval_reactivate_{approval.id}"):
            service.reactivate_influencer_approval_round(actor, campaign.id, approval.id); st.rerun()


def render_content_rounds(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_content_round_add_{campaign.id}"):
        cols = st.columns(4)
        round_number = cols[0].number_input("Round Number", min_value=1, value=1)
        content_type = cols[1].selectbox("Content Type", ["", *CONTENT_ROUND_TYPES])
        internal_due = cols[2].date_input("Internal Review Due Date", value=None)
        feedback_due = cols[3].date_input("Client Feedback Due Date", value=None)
        submitted = st.form_submit_button("Add Content Round", type="primary")
    if submitted:
        service.create_influencer_content_round(actor, campaign.id, round_number, content_type=trim_or_none(content_type), internal_review_due_date=internal_due, client_feedback_due_date=feedback_due, status="not_started")
        st.rerun()
    rounds = service.list_influencer_content_rounds(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Round": r.round_number, "Type": safe_text(r.content_type), "Internal Due": format_date(r.internal_review_due_date), "Client Sent": format_date(r.client_review_sent_date), "Feedback Due": format_date(r.client_feedback_due_date), "Feedback Received": format_date(r.feedback_received_date), "Resubmission Due": format_date(r.resubmission_due_date), "Approved": format_date(r.approved_date), "Status": status_label(r.status), "Active State": "Active" if r.is_active else "Inactive"} for r in rounds], hide_index=True, use_container_width=True)
    for item in rounds:
        cols = st.columns(6)
        if cols[0].button("Sent", key=f"campaign_ops_influencer_round_sent_{item.id}"):
            service.mark_influencer_content_round_sent_for_review(actor, campaign.id, item.id); st.rerun()
        if cols[1].button("Feedback", key=f"campaign_ops_influencer_round_feedback_{item.id}"):
            service.mark_influencer_content_round_feedback_received(actor, campaign.id, item.id); st.rerun()
        if cols[2].button("Approved", key=f"campaign_ops_influencer_round_approved_{item.id}"):
            service.mark_influencer_content_round_approved(actor, campaign.id, item.id); st.rerun()
        if cols[3].button("Reopen", key=f"campaign_ops_influencer_round_reopen_{item.id}"):
            service.reopen_influencer_content_round(actor, campaign.id, item.id); st.rerun()
        if item.is_active and cols[4].button("Deactivate", key=f"campaign_ops_influencer_round_deactivate_{item.id}"):
            service.deactivate_influencer_content_round(actor, campaign.id, item.id); st.rerun()
        if not item.is_active and cols[5].button("Reactivate", key=f"campaign_ops_influencer_round_reactivate_{item.id}"):
            service.reactivate_influencer_content_round(actor, campaign.id, item.id); st.rerun()


def render_creator_summary(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_influencer_creator_summary(actor, campaign.id)
    with st.form(f"campaign_ops_influencer_creator_summary_{campaign.id}"):
        cols = st.columns(4)
        target = cols[0].number_input("Target Creators", min_value=0, value=int((summary.target_creator_count if summary else campaign.target_creator_count) or 0))
        applicants = cols[1].number_input("Applicants", min_value=0, value=int((summary.applicants_count if summary else 0) or 0))
        vetted = cols[2].number_input("Vetted", min_value=0, value=int((summary.vetted_count if summary else 0) or 0))
        submitted_count = cols[3].number_input("Submitted for Approval", min_value=0, value=int((summary.submitted_for_approval_count if summary else 0) or 0))
        cols = st.columns(4)
        approved = cols[0].number_input("Approved", min_value=0, value=int((summary.approved_count if summary else campaign.approved_creator_count) or 0))
        contracted = cols[1].number_input("Contracted", min_value=0, value=int((summary.contracted_count if summary else campaign.contracted_creator_count) or 0))
        content_submitted = cols[2].number_input("Content Submitted", min_value=0, value=int((summary.content_submitted_count if summary else 0) or 0))
        content_approved = cols[3].number_input("Content Approved", min_value=0, value=int((summary.content_approved_count if summary else 0) or 0))
        notes = st.text_area("Notes", value=safe_text(summary.notes if summary else "", ""))
        submitted = st.form_submit_button("Save Creator Summary", type="primary")
    if submitted:
        service.create_or_update_influencer_creator_summary(actor, campaign.id, target_creator_count=target, applicants_count=applicants, vetted_count=vetted, submitted_for_approval_count=submitted_count, approved_count=approved, contracted_count=contracted, content_submitted_count=content_submitted, content_approved_count=content_approved, notes=trim_or_none(notes), is_active=True)
        st.rerun()


def render_timeline(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_timeline_add_{campaign.id}"):
        cols = st.columns(4)
        title = cols[0].text_input("Timeline Item")
        target = cols[1].date_input("Exact Date", value=None)
        start = cols[2].date_input("Start Date", value=None)
        end = cols[3].date_input("End Date", value=None)
        submitted = st.form_submit_button("Add Timeline Item", type="primary")
    if submitted:
        service.create_milestone(actor, campaign.program_id, title, workstream_id=campaign.workstream_id, milestone_type="Influencer Planning", target_date=target, start_date=start, end_date=end)
        st.rerun()
    milestones = [m for m in service.list_program_milestones(actor, campaign.program_id, include_inactive=True) if m.workstream_id == campaign.workstream_id or m.milestone_type == "Influencer Planning"]
    st.dataframe([{"Date": format_date(m.target_date or m.start_date), "End": format_date(m.end_date), "Item": m.title, "Status": title_label(m.status), "Active State": "Active" if m.is_active else "Inactive"} for m in milestones], hide_index=True, use_container_width=True)
    for m in milestones:
        cols = st.columns(4)
        if m.status != TaskStatus.COMPLETED.value and cols[0].button("Complete", key=f"campaign_ops_influencer_milestone_complete_{m.id}"):
            service.complete_milestone(actor, m.id); st.rerun()
        if m.status == TaskStatus.COMPLETED.value and cols[1].button("Reopen", key=f"campaign_ops_influencer_milestone_reopen_{m.id}"):
            service.reopen_milestone(actor, m.id); st.rerun()
        if m.is_active and cols[2].button("Deactivate", key=f"campaign_ops_influencer_milestone_deactivate_{m.id}"):
            service.deactivate_milestone(actor, m.id); st.rerun()
        if not m.is_active and cols[3].button("Reactivate", key=f"campaign_ops_influencer_milestone_reactivate_{m.id}"):
            service.reactivate_milestone(actor, m.id); st.rerun()


def render_resources(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    quick = [("Track Sheet", campaign.track_sheet_url), ("Influencer Brief", campaign.influencer_brief_url), ("Bitly Link", campaign.bitly_link_url), ("Invoice", campaign.invoice_url), ("EOP Survey", campaign.eop_survey_url), ("Campaign Brief", campaign.campaign_brief_url), ("Click2Cart Link", campaign.click2cart_link_url)]
    cols = st.columns(4)
    for index, (label, url) in enumerate(quick):
        target = cols[index % 4]
        if url:
            target.link_button(label, sanitize_link(url), key=f"campaign_ops_influencer_quick_{label}_{campaign.id}")
        else:
            target.metric(label, "Missing")
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    resources = [r for r in service.list_program_resources(actor, campaign.program_id, include_inactive=True) if r.resource_type in INFLUENCER_RESOURCE_TYPES or r.workstream_id == campaign.workstream_id]
    st.dataframe(resource_table_rows(resources), hide_index=True, use_container_width=True)
    with st.form(f"campaign_ops_influencer_resource_add_{campaign.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Title")
        resource_type = cols[1].selectbox("Resource type", INFLUENCER_RESOURCE_TYPES)
        url = cols[2].text_input("URL")
        submitted = st.form_submit_button("Add Resource", type="primary")
    if submitted:
        service.create_resource(actor, campaign.program_id, title=title, resource_type=resource_type, workstream_id=campaign.workstream_id, url=trim_or_none(url))
        st.rerun()
    for resource in resources:
        render_resource_actions(actor, service, summary, resource)


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    rows = [{"Timestamp": format_datetime(e.created_at), "Event": title_label(e.event_type), "Message": safe_text(e.message)} for e in summary.activity if e.event_type.startswith("influencer_") or e.entity_type.startswith("influencer_")]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
