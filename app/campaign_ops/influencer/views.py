from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

import streamlit as st

from app.campaign_ops.formatting import format_date, format_datetime, safe_text, title_label
from app.campaign_ops.influencer.formatting import status_label
from app.campaign_ops.influencer.live_views import render_live
from app.campaign_ops.influencer.planning_baseline import compact_date, next_sequence_step, planning_sequence_preview, select_campaign_for_open
from app.campaign_ops.influencer.recap_views import render_recapping
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer import INFLUENCER_STAGES, PLANNING_STATUSES, RESPONSIBLE_PARTIES
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


def option_index(options: list[str], value: str | None, default: str | None = None) -> int:
    fallback = default if default in options else options[0]
    return options.index(value if value in options else fallback)


def render_influencer(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    render_css()
    st.subheader("Influencer")
    section = st.radio("Influencer workspace", ["Planning", "Live", "Recapping"], horizontal=True, key="campaign_ops_influencer_view")
    if section == "Live":
        render_live(actor, service, users)
        return
    if section == "Recapping":
        render_recapping(actor, service, users)
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
        .campaign-ops-influencer-controls [data-testid="stButton"] button[kind="secondary"] { border-color:#c8d0d2; color:#32444c; }
        .campaign-ops-influencer-block { border:1px solid #b7c7c7; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-influencer-header { background:#2fa6a3; color:#082525; padding:.42rem .55rem; border-bottom:1px solid #268f8c; }
        .campaign-ops-influencer-header-main { display:flex; justify-content:space-between; gap:.75rem; align-items:flex-start; font-weight:800; line-height:1.2; }
        .campaign-ops-influencer-header-meta { margin-top:.16rem; font-size:.82rem; font-weight:700; color:#123b42; }
        .campaign-ops-influencer-hold { background:#b00020; color:#fff; font-weight:800; padding:.12rem .42rem; border-radius:2px; white-space:nowrap; }
        .campaign-ops-influencer-hold-reason { margin-top:.2rem; color:#601015; font-weight:700; font-size:.82rem; }
        .campaign-ops-influencer-links { border-bottom:1px solid #d7e0e0; padding:.32rem .5rem; font-size:.82rem; }
        .campaign-ops-influencer-sequence { width:100%; border-collapse:collapse; font-size:.84rem; }
        .campaign-ops-influencer-sequence th { background:#06314a; color:white; text-align:left; padding:.28rem .45rem; font-size:.78rem; }
        .campaign-ops-influencer-sequence td { border-top:1px solid #dbe4e4; padding:.26rem .45rem; vertical-align:top; }
        .campaign-ops-influencer-sequence-date { width:4.2rem; white-space:nowrap; color:#223b44; font-weight:700; }
        .campaign-ops-influencer-sequence-status { width:7.2rem; color:#38545c; }
        .campaign-ops-influencer-status-grid { display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); border-top:1px solid #ccdada; }
        .campaign-ops-influencer-status-item { padding:.35rem .5rem; border-right:1px solid #e0e8e8; min-width:0; }
        .campaign-ops-influencer-status-label { color:#526970; font-size:.72rem; font-weight:800; text-transform:uppercase; }
        .campaign-ops-influencer-status-value { color:#102a32; font-size:.84rem; line-height:1.25; overflow-wrap:anywhere; }
        .campaign-ops-influencer-empty { border-top:1px solid #dbe4e4; padding:.4rem .55rem; color:#62747a; font-size:.86rem; }
        @media (max-width: 900px) { .campaign-ops-influencer-status-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_planning(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    st.markdown("### Influencer Planning")
    tabs = st.radio("Planning view", ["All Planning", "T - In Planning", "L - In Planning", "New Influencer Campaign"], horizontal=True, key="campaign_ops_influencer_planning_view")
    if tabs == "New Influencer Campaign" or st.session_state.get("campaign_ops_influencer_create_open"):
        render_new_campaign(actor, service, users)
        return
    manager_id = None
    if tabs.startswith("T"):
        manager_id = next((u.id for u in users if u.display_name == "T"), None)
    if tabs.startswith("L"):
        manager_id = next((u.id for u in users if u.display_name == "L"), None)
    render_portfolio(actor, service, manager_id, current_view=tabs)


def render_portfolio(actor: CampaignOpsUser, service: CampaignOpsService, manager_user_id: str | None, *, current_view: str = "All Planning") -> None:
    st.caption(f"Current view: {current_view}")
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
    show_manager_filter = manager_user_id is None
    filters = render_filters(campaigns, show_manager_filter=show_manager_filter)
    campaigns = sort_campaigns(filter_campaigns(campaigns, filters), str(filters.get("sort_by") or "updated_at"))
    if not campaigns:
        st.info("No influencer campaigns match these filters.")
        return
    for campaign in campaigns:
        try:
            steps = service.list_influencer_planning_steps(actor, campaign.id)
        except CampaignOpsError:
            steps = []
        render_campaign_block(campaign, steps, compact=current_view == "All Planning")


def render_filters(campaigns: list[Any], *, show_manager_filter: bool = True) -> dict[str, object]:
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
        if show_manager_filter:
            managers = {"Any": "", **{safe_text(c.manager_display_name): c.manager_user_id for c in campaigns if c.manager_user_id}}
            current["manager_user_id"] = managers[cols[3].selectbox("Manager", list(managers), key="campaign_ops_influencer_filter_manager")]
        else:
            current.pop("manager_user_id", None)
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


def render_campaign_block(campaign: Any, steps: list[Any], *, compact: bool = False) -> None:
    expanded_key = f"campaign_ops_influencer_sequence_full_{campaign.id}"
    expanded = bool(st.session_state.get(expanded_key))
    visible_steps = steps if expanded else planning_sequence_preview(steps, today=date.today(), upcoming_limit=3 if compact else 4, compact=compact)
    next_step = next_sequence_step(steps)
    next_title = safe_text(getattr(next_step, "step_title", None)) if next_step else "Planning sequence complete"
    next_due = compact_date(getattr(next_step, "due_date", None), reference_year=date.today().year) if next_step else ""
    hold_badge = "<span class='campaign-ops-influencer-hold'>ON HOLD</span>" if campaign.is_on_hold else ("<span>ACTIVE</span>" if campaign.is_active else "<span>INACTIVE</span>")
    hold_reason = f"<div class='campaign-ops-influencer-hold-reason'>Hold reason: {escape(safe_text(campaign.hold_reason))}</div>" if campaign.is_on_hold and campaign.hold_reason else ""
    html = f"""
    <div class='campaign-ops-influencer-block'>
      <div class='campaign-ops-influencer-header'>
        <div class='campaign-ops-influencer-header-main'>
          <div>{escape(campaign.campaign_title)}</div>
          <div>{hold_badge}</div>
        </div>
        <div class='campaign-ops-influencer-header-meta'>{escape(safe_text(campaign.manager_display_name))} &middot; {escape(status_label(campaign.planning_status))}</div>
        {hold_reason}
      </div>
    """
    if visible_steps:
        html += "<table class='campaign-ops-influencer-sequence'><thead><tr><th>Date</th><th>Planning Action</th><th>Status</th></tr></thead><tbody>"
        for step in visible_steps:
            html += (
                "<tr>"
                f"<td class='campaign-ops-influencer-sequence-date'>{escape(compact_date(getattr(step, 'due_date', None), reference_year=date.today().year))}</td>"
                f"<td>{escape(safe_text(getattr(step, 'step_title', None)))}</td>"
                f"<td class='campaign-ops-influencer-sequence-status'>{escape(status_label(getattr(step, 'status', None)))}</td>"
                "</tr>"
            )
        html += "</tbody></table>"
    else:
        html += "<div class='campaign-ops-influencer-empty'>No planning steps yet.</div>"
    status_items = [
        ("Latest Update", safe_text(campaign.latest_update)),
        ("Waiting On", safe_text(campaign.waiting_on)),
        ("Next", next_title),
        ("Due", next_due),
        ("Launch", compact_date(campaign.launch_date, reference_year=date.today().year)),
        ("Wrap", compact_date(campaign.wrap_date, reference_year=date.today().year)),
    ]
    html += "<div class='campaign-ops-influencer-status-grid'>"
    html += "".join(f"<div class='campaign-ops-influencer-status-item'><div class='campaign-ops-influencer-status-label'>{escape(label)}</div><div class='campaign-ops-influencer-status-value'>{escape(value)}</div></div>" for label, value in status_items if value or label in {"Next", "Due", "Launch", "Wrap"})
    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)
    cols = st.columns([1, 1, 5])
    label = "Collapse sequence" if expanded else "Show full sequence"
    if steps and cols[0].button(label, key=f"campaign_ops_influencer_sequence_toggle_{campaign.id}"):
        st.session_state[expanded_key] = not expanded
        st.rerun()
    if cols[1].button("Open Campaign", key=f"campaign_ops_influencer_open_{campaign.id}"):
        select_campaign_for_open(st.session_state, campaign.id)
        st.rerun()


def render_new_campaign(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    if st.button("Back to Influencer Planning", key="campaign_ops_influencer_create_back"):
        st.session_state["campaign_ops_influencer_create_open"] = False
        st.rerun()
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    program_options = {f"{p.program_name} | {safe_text(p.client_name)}": p.id for p in programs}
    if not program_options:
        st.info("No active Campaign Operations programs are available for Influencer Planning.")
        return
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
        cols = st.columns(1)
        invoice_status = cols[0].text_input("Invoice Status")
        use_template = st.checkbox("Create standard planning template")
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
    tabs = st.tabs(['Overview', 'Planning Sequence', 'Timeline', 'Program Notes', 'Activity'])
    with tabs[0]:
        render_overview(actor, service, users, campaign)
    with tabs[1]:
        render_steps(actor, service, users, campaign)
    with tabs[2]:
        render_timeline(actor, service, campaign)
    with tabs[3]:
        with st.expander("Program Notes", expanded=False):
            render_notes(actor, service, service.get_program_workspace_summary(actor, campaign.program_id))
    with tabs[4]:
        with st.expander("Activity", expanded=False):
            render_activity(actor, service, campaign)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any) -> None:
    user_options = {"": None, **{u.display_name: u.id for u in users if u.is_active}}
    reverse_users = {v: k for k, v in user_options.items()}
    with st.form(f"campaign_ops_influencer_overview_{campaign.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Campaign Title", value=campaign.campaign_title)
        manager = cols[1].selectbox("Manager", list(user_options), index=list(user_options).index(reverse_users.get(campaign.manager_user_id, "")))
        status = cols[2].selectbox("Planning Status", PLANNING_STATUSES, index=option_index(PLANNING_STATUSES, campaign.planning_status, "not_started"), format_func=status_label)
        cols = st.columns(4)
        stage = cols[0].selectbox("Stage", INFLUENCER_STAGES, index=option_index(INFLUENCER_STAGES, campaign.influencer_stage, "planning"), format_func=status_label)
        waiting = cols[1].text_input("Waiting On", value=safe_text(campaign.waiting_on))
        on_hold = cols[2].checkbox("On Hold", value=campaign.is_on_hold)
        hold_reason = cols[3].text_input("Hold Reason", value=safe_text(campaign.hold_reason))
        latest = st.text_area("Latest Update", value=safe_text(campaign.latest_update))
        cols = st.columns(4)
        launch = cols[0].date_input("Launch Date", value=campaign.launch_date)
        wrap = cols[1].date_input("Wrap Date", value=campaign.wrap_date)
        invoice_date = cols[2].date_input("Invoice Date", value=campaign.invoice_date)
        invoice_status = cols[3].text_input("Invoice Status", value=safe_text(campaign.invoice_status))
        submitted = st.form_submit_button("Save Overview", type="primary")
    if submitted:
        service.update_influencer_campaign(actor, campaign.id, campaign_title=title, manager_user_id=user_options[manager], influencer_stage=stage, planning_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), is_on_hold=on_hold, hold_reason=trim_or_none(hold_reason), launch_date=launch, wrap_date=wrap, invoice_date=invoice_date, invoice_status=trim_or_none(invoice_status))
        st.rerun()
    cols = st.columns(2)
    if campaign.influencer_stage == "planning" and st.button("Move Campaign to Live", key=f"campaign_ops_influencer_move_live_{campaign.id}"):
        service.transition_influencer_campaign_to_live(actor, campaign.id)
        st.session_state["campaign_ops_selected_influencer_live_campaign_id"] = campaign.id
        st.session_state.pop("campaign_ops_selected_influencer_campaign_id", None)
        st.rerun()
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


def render_timeline(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_timeline_add_{campaign.id}"):
        cols = st.columns(4)
        title = cols[0].text_input("Timeline Item")
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


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    rows = [{"Timestamp": format_datetime(e.created_at), "Event": title_label(e.event_type), "Message": safe_text(e.message)} for e in summary.activity if e.event_type.startswith("influencer_") or e.entity_type.startswith("influencer_")]
    st.dataframe(rows, hide_index=True, use_container_width=True)
