from __future__ import annotations

from datetime import date
from html import escape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.formatting import format_date, format_datetime, safe_text, title_label
from app.campaign_ops.influencer.live_baseline import (
    compose_live_operational_sequence,
    live_quick_links,
    next_go_live_text,
    select_live_campaign_for_open,
    smart_live_sequence_preview,
)
from app.campaign_ops.influencer.planning_baseline import compact_date
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.resource_views import render_resource_actions, resource_table_rows
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer import (
    INFLUENCER_RESOURCE_TYPES,
    LIVE_EXCEPTION_TYPES,
    LIVE_RESOURCE_TYPES,
    LIVE_STATUSES,
    RESPONSIBLE_PARTIES,
)
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.service import CampaignOpsService

LIVE_COLUMNS = [
    "Campaign",
    "Client",
    "Shared Program",
    "Manager",
    "Live Status",
    "Latest Update",
    "Waiting On",
    "Hold State",
    "Hold Reason",
    "Live Creator Count",
    "Planned Creator Count",
    "Active Waves",
    "Next Go-Live Date",
    "Paid Live End Date",
    "Open Exceptions",
    "Wrap Date",
    "Invoice Status",
    "Track Sheet",
    "Influencer Brief",
    "EOP Survey",
    "Invoice",
    "Click2Cart",
    "Client-Facing Live Doc",
    "Daily Impressions",
    "Risk",
    "Updated Date",
    "Active State",
]

SORT_OPTIONS = {
    "Recently updated": "updated_at",
    "Campaign": "campaign_title",
    "Client": "client_name",
    "Manager": "manager_display_name",
    "Live Status": "live_status",
    "Next Go-Live Date": "next_go_live_date",
    "Open Exceptions": "open_exception_count",
    "Wrap Date": "wrap_date",
    "Risk": "program_risk",
}


def render_live(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    render_live_css()
    selected = st.session_state.get("campaign_ops_selected_influencer_live_campaign_id")
    if selected:
        render_live_workspace(actor, service, users, str(selected))
        return
    st.markdown("### Influencer Live")
    view = st.radio("Live view", ["All Live", "T - Live", "L - Live"], horizontal=True, key="campaign_ops_influencer_live_view")
    manager_id = None
    if view.startswith("T"):
        manager_id = next((u.id for u in users if u.display_name == "T"), None)
    if view.startswith("L"):
        manager_id = next((u.id for u in users if u.display_name == "L"), None)
    render_live_portfolio(actor, service, manager_id, current_view=view)


def render_live_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-live-block { border:1px solid #b7c7c7; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-live-header { background:#2fa6a3; color:#082525; padding:.42rem .55rem; border-bottom:1px solid #268f8c; }
        .campaign-ops-live-header-main { display:flex; justify-content:space-between; gap:.75rem; align-items:flex-start; font-weight:800; line-height:1.2; }
        .campaign-ops-live-meta { margin-top:.16rem; font-size:.82rem; font-weight:700; color:#123b42; }
        .campaign-ops-live-hold { background:#b00020; color:#fff; font-weight:800; padding:.12rem .42rem; border-radius:2px; white-space:nowrap; }
        .campaign-ops-live-hold-reason { margin-top:.2rem; color:#601015; font-weight:700; font-size:.82rem; }
        .campaign-ops-live-links { border-bottom:1px solid #d7e0e0; padding:.32rem .5rem; font-size:.82rem; }
        .campaign-ops-live-sequence { width:100%; border-collapse:collapse; font-size:.84rem; }
        .campaign-ops-live-sequence th { background:#06314a; color:white; text-align:left; padding:.28rem .45rem; font-size:.78rem; }
        .campaign-ops-live-sequence td { border-top:1px solid #dbe4e4; padding:.26rem .45rem; vertical-align:top; }
        .campaign-ops-live-date { width:4.2rem; white-space:nowrap; color:#223b44; font-weight:700; }
        .campaign-ops-live-status { width:7rem; color:#38545c; }
        .campaign-ops-live-source { width:6rem; color:#526970; font-size:.76rem; }
        .campaign-ops-live-status-grid { display:grid; grid-template-columns:repeat(6, minmax(0, 1fr)); border-top:1px solid #ccdada; }
        .campaign-ops-live-status-item { padding:.35rem .5rem; border-right:1px solid #e0e8e8; min-width:0; }
        .campaign-ops-live-status-label { color:#526970; font-size:.72rem; font-weight:800; text-transform:uppercase; }
        .campaign-ops-live-status-value { color:#102a32; font-size:.84rem; line-height:1.25; overflow-wrap:anywhere; }
        .campaign-ops-live-empty { border-top:1px solid #dbe4e4; padding:.4rem .55rem; color:#62747a; font-size:.86rem; }
        @media (max-width: 900px) { .campaign-ops-live-status-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_live_portfolio(actor: CampaignOpsUser, service: CampaignOpsService, manager_user_id: str | None, *, current_view: str = "All Live") -> None:
    st.caption(f"Current view: {current_view}")
    cols = st.columns(4)
    include_inactive = cols[0].checkbox("Show inactive", key="campaign_ops_influencer_live_show_inactive")
    if cols[1].button("Refresh", key="campaign_ops_influencer_live_refresh"):
        st.rerun()
    if cols[2].button("Clear filters", key="campaign_ops_influencer_live_clear"):
        st.session_state["campaign_ops_influencer_live_filters"] = {}
        st.rerun()
    try:
        campaigns = service.list_influencer_live_campaigns(actor, include_inactive=include_inactive, manager_user_id=manager_user_id)
    except CampaignOpsError as exc:
        st.error(f"Unable to load Influencer Live: {exc}")
        return
    filters = render_filters(campaigns, show_manager_filter=manager_user_id is None)
    filtered = sort_rows(filter_rows(campaigns, filters), str(filters.get("sort_by") or "updated_at"))
    if not filtered:
        st.info("No live influencer campaigns match these filters.")
        return
    board_data = service.get_influencer_live_manager_board_data(actor, filtered)
    planning_steps = board_data.get("planning_steps", {})
    checkpoints = board_data.get("checkpoints", {})
    waves = board_data.get("waves", {})
    resources_by_program = board_data.get("resources", {})
    for campaign in filtered:
        render_live_block(
            campaign,
            planning_steps.get(campaign.id, []),
            checkpoints.get(campaign.id, []),
            waves.get(campaign.id, []),
            resources_by_program.get(campaign.program_id, []),
            compact=current_view == "All Live",
        )
    with st.expander("Live Portfolio Summary", expanded=False):
        st.dataframe(live_rows(filtered), column_order=LIVE_COLUMNS, hide_index=True, use_container_width=True)
    if filtered:
        labels = {f"{c.campaign_title} | {safe_text(c.client_name)}": c.id for c in filtered}
        cols = st.columns(2)
        chosen = cols[0].selectbox("Open Live Campaign", list(labels), key="campaign_ops_influencer_live_campaign_select")
        if cols[1].button("Open Live Workspace", key="campaign_ops_influencer_live_open"):
            st.session_state["campaign_ops_selected_influencer_live_campaign_id"] = labels[chosen]
            st.rerun()


def render_filters(campaigns: list[Any], *, show_manager_filter: bool = True) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_influencer_live_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Live filters", expanded=True):
        cols = st.columns(5)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_influencer_live_search")
        clients = {"Any": "", **{safe_text(c.client_name): c.client_name for c in campaigns if c.client_name}}
        current["client_name"] = clients[cols[1].selectbox("Client", list(clients), key="campaign_ops_influencer_live_client")]
        programs = {"Any": "", **{c.program_name: c.program_id for c in campaigns}}
        current["program_id"] = programs[cols[2].selectbox("Program", list(programs), key="campaign_ops_influencer_live_program")]
        if show_manager_filter:
            managers = {"Any": "", **{safe_text(c.manager_display_name): c.manager_user_id for c in campaigns if c.manager_user_id}}
            current["manager_user_id"] = managers[cols[3].selectbox("Manager", list(managers), key="campaign_ops_influencer_live_manager")]
        else:
            current.pop("manager_user_id", None)
        current["sort_by"] = SORT_OPTIONS[cols[4].selectbox("Sort", list(SORT_OPTIONS), key="campaign_ops_influencer_live_sort")]
        cols = st.columns(5)
        current["live_status"] = cols[0].selectbox("Live status", ["Any", *LIVE_STATUSES], key="campaign_ops_influencer_live_status", format_func=title_label)
        current["hold"] = cols[1].selectbox("On Hold", ["Any", "On Hold", "Not on hold"], key="campaign_ops_influencer_live_hold")
        current["wave"] = cols[2].selectbox("Waves", ["Any", "Has waves", "No waves"], key="campaign_ops_influencer_live_wave")
        current["exceptions"] = cols[3].selectbox("Open exceptions", ["Any", "Has open exceptions", "No open exceptions"], key="campaign_ops_influencer_live_exceptions")
        current["live_from"] = cols[4].date_input("Live from", value=current.get("live_from"), key="campaign_ops_influencer_live_from")
    st.session_state["campaign_ops_influencer_live_filters"] = current
    return current


def filter_rows(campaigns: list[Any], filters: dict[str, object]) -> list[Any]:
    rows = campaigns
    search = str(filters.get("search") or "").lower()
    if search:
        rows = [c for c in rows if search in " ".join([c.campaign_title, c.program_name, safe_text(c.client_name), safe_text(c.latest_update), safe_text(c.waiting_on)]).lower()]
    for field in ("client_name", "program_id", "manager_user_id", "live_status"):
        value = filters.get(field)
        if value and value != "Any":
            rows = [c for c in rows if getattr(c, field) == value]
    if filters.get("hold") == "On Hold":
        rows = [c for c in rows if c.is_on_hold]
    if filters.get("hold") == "Not on hold":
        rows = [c for c in rows if not c.is_on_hold]
    if filters.get("wave") == "Has waves":
        rows = [c for c in rows if c.active_wave_count > 0]
    if filters.get("wave") == "No waves":
        rows = [c for c in rows if c.active_wave_count == 0]
    if filters.get("exceptions") == "Has open exceptions":
        rows = [c for c in rows if c.open_exception_count > 0]
    if filters.get("exceptions") == "No open exceptions":
        rows = [c for c in rows if c.open_exception_count == 0]
    live_from = filters.get("live_from")
    if live_from:
        rows = [c for c in rows if c.next_go_live_date and c.next_go_live_date >= live_from]
    return rows


def sort_rows(campaigns: list[Any], sort_by: str) -> list[Any]:
    return sorted(campaigns, key=lambda c: (getattr(c, sort_by, None) is None, getattr(c, sort_by, None) or "", c.campaign_title))


def live_rows(campaigns: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "Campaign": c.campaign_title,
            "Client": safe_text(c.client_name),
            "Shared Program": c.program_name,
            "Manager": safe_text(c.manager_display_name),
            "Live Status": title_label(c.live_status),
            "Latest Update": safe_text(c.latest_update),
            "Waiting On": safe_text(c.waiting_on),
            "Hold State": "ON HOLD" if c.is_on_hold else "Active",
            "Hold Reason": safe_text(c.hold_reason),
            "Live Creator Count": str(c.live_creator_count),
            "Planned Creator Count": safe_text(c.planned_creator_count),
            "Active Waves": str(c.active_wave_count),
            "Next Go-Live Date": format_date(c.next_go_live_date),
            "Paid Live End Date": format_date(c.paid_live_end_date),
            "Open Exceptions": str(c.open_exception_count),
            "Wrap Date": format_date(c.wrap_date),
            "Invoice Status": safe_text(c.invoice_status),
            "Track Sheet": "Available" if c.track_sheet_url else "Missing",
            "Influencer Brief": "Available" if c.influencer_brief_url else "Missing",
            "EOP Survey": "Available" if c.eop_survey_url else "Missing",
            "Invoice": "Available" if c.invoice_url else "Missing",
            "Click2Cart": "Available" if c.click2cart_link_url else "Missing",
            "Client-Facing Live Doc": "Available" if c.client_facing_live_doc_url else "Missing",
            "Daily Impressions": "Available" if c.daily_impressions_url else "Missing",
            "Risk": title_label(c.program_risk),
            "Updated Date": format_datetime(c.updated_at),
            "Active State": "Active" if c.is_active else "Inactive",
        }
        for c in campaigns
    ]


def render_live_block(campaign: Any, planning_steps: list[Any], checkpoints: list[Any], waves: list[Any], resources: list[Any], *, compact: bool = False) -> None:
    expanded_key = f"campaign_ops_influencer_live_sequence_full_{campaign.id}"
    expanded = bool(st.session_state.get(expanded_key))
    sequence = compose_live_operational_sequence(planning_steps, checkpoints, waves)
    visible_sequence = sequence if expanded else smart_live_sequence_preview(sequence, today=date.today(), upcoming_limit=3 if compact else 4, compact=compact)
    urgent = " background:#fff9d8;" if campaign.highlighted_exception_count else ""
    hold_badge = "<span class='campaign-ops-live-hold'>ON HOLD</span>" if campaign.is_on_hold else "<span>ACTIVE</span>"
    hold_reason = f"<div class='campaign-ops-live-hold-reason'>Hold reason: {escape(safe_text(campaign.hold_reason))}</div>" if campaign.is_on_hold and campaign.hold_reason else ""
    links = live_quick_links(campaign, resources)
    all_live = bool(campaign.planned_creator_count) and campaign.live_creator_count >= int(campaign.planned_creator_count or 0)
    html = f"""
    <div class='campaign-ops-live-block' style='{urgent}'>
      <div class='campaign-ops-live-header'>
        <div class='campaign-ops-live-header-main'>
          <div>{escape(campaign.campaign_title)}</div>
          <div>{hold_badge}</div>
        </div>
        <div class='campaign-ops-live-meta'>{escape(safe_text(campaign.manager_display_name))} &middot; {escape(title_label(campaign.live_status))}</div>
        {hold_reason}
      </div>
    """
    if links:
        html += "<div class='campaign-ops-live-links'>" + " &nbsp; ".join(f"<a href='{escape(sanitize_link(link.url), quote=True)}' target='_blank'>{escape(link.label)}</a>" for link in links) + "</div>"
    if visible_sequence:
        html += "<table class='campaign-ops-live-sequence'><thead><tr><th>Date</th><th>Operational Action</th><th>Status</th><th>Source</th></tr></thead><tbody>"
        for row in visible_sequence:
            waiting = f"<div class='campaign-ops-live-source'>Waiting: {escape(safe_text(row.waiting_on))}</div>" if row.waiting_on else ""
            html += (
                "<tr>"
                f"<td class='campaign-ops-live-date'>{escape(compact_date(row.display_date, reference_year=date.today().year))}</td>"
                f"<td>{escape(row.action)}{waiting}</td>"
                f"<td class='campaign-ops-live-status'>{escape(row.status)}</td>"
                f"<td class='campaign-ops-live-source'>{escape(row.source)}</td>"
                "</tr>"
            )
        html += "</tbody></table>"
    else:
        html += "<div class='campaign-ops-live-empty'>No operational sequence items yet.</div>"
    status_items = [
        ("Latest Update", safe_text(campaign.latest_update)),
        ("Waiting On", safe_text(campaign.waiting_on)),
        ("Creators Live", f"{campaign.live_creator_count} / {safe_text(campaign.planned_creator_count)}"),
        ("Waves", str(campaign.active_wave_count)),
        ("Next Go-Live", next_go_live_text(campaign.next_go_live_date, all_live=all_live)),
        ("Exceptions", str(campaign.open_exception_count)),
        ("Paid Live End", compact_date(campaign.paid_live_end_date, reference_year=date.today().year)),
        ("Launch", compact_date(campaign.launch_date, reference_year=date.today().year)),
        ("Wrap", compact_date(campaign.wrap_date, reference_year=date.today().year)),
        ("Invoice", f"{compact_date(campaign.invoice_date, reference_year=date.today().year)} {safe_text(campaign.invoice_status)}".strip()),
    ]
    html += "<div class='campaign-ops-live-status-grid'>"
    html += "".join(f"<div class='campaign-ops-live-status-item'><div class='campaign-ops-live-status-label'>{escape(label)}</div><div class='campaign-ops-live-status-value'>{escape(value)}</div></div>" for label, value in status_items if value or label in {"Creators Live", "Waves", "Next Go-Live", "Exceptions", "Paid Live End", "Launch", "Wrap"})
    html += "</div></div>"
    st.markdown(html, unsafe_allow_html=True)
    cols = st.columns([1, 1, 5])
    label = "Collapse sequence" if expanded else "Show full sequence"
    if sequence and cols[0].button(label, key=f"campaign_ops_influencer_live_sequence_toggle_{campaign.id}"):
        st.session_state[expanded_key] = not expanded
        st.rerun()
    if cols[1].button("Open Live Campaign", key=f"campaign_ops_influencer_live_open_{campaign.id}"):
        select_live_campaign_for_open(st.session_state, campaign.id)
        st.rerun()


def render_live_workspace(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign_id: str) -> None:
    try:
        summary = service.get_influencer_live_workspace_summary(actor, campaign_id)
    except CampaignOpsError as exc:
        st.session_state.pop("campaign_ops_selected_influencer_live_campaign_id", None)
        st.warning(f"Influencer Live campaign is no longer available: {exc}")
        return
    campaign = summary.campaign
    if st.button("Back to Influencer Live", key="campaign_ops_influencer_live_back"):
        st.session_state.pop("campaign_ops_selected_influencer_live_campaign_id", None)
        st.rerun()
    cols = st.columns(2)
    if cols[0].button("Open Program Workspace", key=f"campaign_ops_influencer_live_program_{campaign.id}"):
        set_selected_program(st.session_state, campaign.program_id); st.rerun()
    if cols[1].button("Open Planning History", key=f"campaign_ops_influencer_live_planning_{campaign.id}"):
        st.session_state["campaign_ops_selected_influencer_campaign_id"] = campaign.id
        st.session_state.pop("campaign_ops_selected_influencer_live_campaign_id", None)
        st.session_state["campaign_ops_influencer_view"] = "Planning"
        st.rerun()
    st.markdown(f"### {campaign.campaign_title}")
    st.caption(f"{safe_text(campaign.client_name)} | {campaign.program_name} | Manager: {safe_text(campaign.manager_display_name)} | {title_label(campaign.live_status)} | Wrap readiness: {summary.wrap_readiness}")
    st.info(f"Live creators: {campaign.live_creator_count} | Waves: {campaign.active_wave_count} | Open exceptions: {campaign.open_exception_count} | Next go-live: {format_date(campaign.next_go_live_date)} | Paid live end: {format_date(campaign.paid_live_end_date)}")
    tabs = st.tabs(["Overview", "Live Checkpoints", "Creator Waves", "Creator Live Status", "Exceptions", "Timeline", "Resources", "Program Notes", "Activity"])
    with tabs[0]:
        render_overview(actor, service, users, campaign, summary)
    with tabs[1]:
        render_checkpoints(actor, service, users, campaign)
    with tabs[2]:
        render_waves(actor, service, campaign)
    with tabs[3]:
        render_creators(actor, service, campaign)
    with tabs[4]:
        render_exceptions(actor, service, users, campaign)
    with tabs[5]:
        render_timeline(actor, service, campaign)
    with tabs[6]:
        render_resources(actor, service, campaign)
    with tabs[7]:
        render_notes(actor, service, service.get_program_workspace_summary(actor, campaign.program_id))
    with tabs[8]:
        render_activity(actor, service, campaign)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any, summary: Any) -> None:
    user_options = {u.display_name: u.id for u in users if u.is_active}
    with st.form(f"campaign_ops_influencer_live_overview_{campaign.id}"):
        cols = st.columns(4)
        manager = cols[0].selectbox("Manager", list(user_options), index=list(user_options.values()).index(campaign.manager_user_id) if campaign.manager_user_id in user_options.values() else 0)
        live_status = cols[1].selectbox("Live Status", LIVE_STATUSES, index=LIVE_STATUSES.index(campaign.live_status) if campaign.live_status in LIVE_STATUSES else 0, format_func=title_label)
        waiting = cols[2].text_input("Waiting On", value=safe_text(campaign.waiting_on))
        on_hold = cols[3].checkbox("On Hold", value=campaign.is_on_hold)
        hold_reason = st.text_input("Hold Reason", value=safe_text(campaign.hold_reason))
        latest = st.text_area("Latest Update", value=safe_text(campaign.latest_update))
        cols = st.columns(4)
        launch = cols[0].date_input("Launch Date", value=campaign.launch_date)
        wrap = cols[1].date_input("Wrap Date", value=campaign.wrap_date)
        invoice_date = cols[2].date_input("Invoice Date", value=campaign.invoice_date)
        invoice_status = cols[3].text_input("Invoice Status", value=safe_text(campaign.invoice_status))
        invoice_amount = st.number_input("Invoice Amount", min_value=0.0, value=float(campaign.invoice_amount or 0))
        submitted = st.form_submit_button("Save Live Overview", type="primary")
    if submitted:
        service.update_influencer_live_overview(actor, campaign.id, manager_user_id=user_options[manager], planning_status=live_status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), is_on_hold=on_hold, hold_reason=trim_or_none(hold_reason), launch_date=launch, wrap_date=wrap, invoice_date=invoice_date, invoice_status=trim_or_none(invoice_status), invoice_amount=invoice_amount)
        st.rerun()
    st.write(f"Planning history: {len(summary.planning_steps)} planning steps, {len(summary.approval_rounds)} approvals, {len(summary.content_rounds)} content rounds preserved.")
    override = st.checkbox("Administrator override unresolved Live readiness", key=f"campaign_ops_influencer_live_recap_override_{campaign.id}")
    if st.button("Move Campaign to Recapping", key=f"campaign_ops_influencer_live_to_recap_{campaign.id}"):
        service.transition_influencer_campaign_to_recapping(actor, campaign.id, allow_override=override)
        st.session_state["campaign_ops_selected_influencer_recap_campaign_id"] = campaign.id
        st.session_state.pop("campaign_ops_selected_influencer_live_campaign_id", None)
        st.session_state["campaign_ops_influencer_view"] = "Recapping"
        st.rerun()
    cols = st.columns(2)
    if campaign.is_active and cols[0].button("Deactivate Campaign", key=f"campaign_ops_influencer_live_deactivate_{campaign.id}"):
        service.deactivate_influencer_campaign(actor, campaign.id); st.rerun()
    if not campaign.is_active and cols[1].button("Reactivate Campaign", key=f"campaign_ops_influencer_live_reactivate_{campaign.id}"):
        service.reactivate_influencer_campaign(actor, campaign.id); st.rerun()


def render_checkpoints(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any) -> None:
    if st.button("Create Standard Live Checkpoint Template", key=f"campaign_ops_influencer_live_template_{campaign.id}"):
        service.create_standard_influencer_live_template(actor, campaign.id); st.rerun()
    user_options = {"": None, **{u.display_name: u.id for u in users if u.is_active}}
    with st.form(f"campaign_ops_influencer_live_checkpoint_add_{campaign.id}"):
        cols = st.columns(5)
        title = cols[0].text_input("Checkpoint")
        responsible = cols[1].selectbox("Responsible Party", ["", *RESPONSIBLE_PARTIES])
        assigned = cols[2].selectbox("Assigned User", list(user_options))
        due = cols[3].date_input("Due Date", value=None)
        order = cols[4].number_input("Sequence Order", min_value=0, value=0)
        submitted = st.form_submit_button("Add Checkpoint", type="primary")
    if submitted:
        service.create_influencer_live_checkpoint(actor, campaign.id, title, responsible_party=trim_or_none(responsible), assigned_user_id=user_options[assigned], due_date=due, sequence_order=order, status="not_started")
        st.rerun()
    checkpoints = service.list_influencer_live_checkpoints(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Date": format_date(c.due_date or c.start_date), "Checkpoint": c.checkpoint_title, "Responsible": safe_text(c.responsible_party), "Status": title_label(c.status), "Completed": format_date(c.completed_date), "Waiting On": safe_text(c.waiting_on), "Notes": safe_text(c.notes), "Active State": "Active" if c.is_active else "Inactive"} for c in checkpoints], hide_index=True, use_container_width=True)
    for checkpoint in checkpoints:
        cols = st.columns(4)
        if not checkpoint.completed_date and cols[0].button("Complete", key=f"campaign_ops_influencer_live_checkpoint_complete_{checkpoint.id}"):
            service.complete_influencer_live_checkpoint(actor, campaign.id, checkpoint.id); st.rerun()
        if checkpoint.completed_date and cols[1].button("Reopen", key=f"campaign_ops_influencer_live_checkpoint_reopen_{checkpoint.id}"):
            service.reopen_influencer_live_checkpoint(actor, campaign.id, checkpoint.id); st.rerun()
        if checkpoint.is_active and cols[2].button("Deactivate", key=f"campaign_ops_influencer_live_checkpoint_deactivate_{checkpoint.id}"):
            service.deactivate_influencer_live_checkpoint(actor, campaign.id, checkpoint.id); st.rerun()
        if not checkpoint.is_active and cols[3].button("Reactivate", key=f"campaign_ops_influencer_live_checkpoint_reactivate_{checkpoint.id}"):
            service.reactivate_influencer_live_checkpoint(actor, campaign.id, checkpoint.id); st.rerun()


def render_waves(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_wave_add_{campaign.id}"):
        cols = st.columns(5)
        number = cols[0].number_input("Wave Number", min_value=1, value=1)
        name = cols[1].text_input("Wave Name")
        planned_start = cols[2].date_input("Planned Start", value=None)
        planned_end = cols[3].date_input("Planned End", value=None)
        planned_count = cols[4].number_input("Planned Creators", min_value=0, value=0)
        submitted = st.form_submit_button("Add Wave", type="primary")
    if submitted:
        service.create_influencer_creator_wave(actor, campaign.id, number, wave_name=trim_or_none(name), planned_start_date=planned_start, planned_end_date=planned_end, planned_creator_count=planned_count, status="not_started")
        st.rerun()
    waves = service.list_influencer_creator_waves(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Wave": w.wave_number, "Name": safe_text(w.wave_name), "Planned": f"{format_date(w.planned_start_date)} - {format_date(w.planned_end_date)}", "Actual": f"{format_date(w.actual_start_date)} - {format_date(w.actual_end_date)}", "Planned Creators": safe_text(w.planned_creator_count), "Live": safe_text(w.live_creator_count), "Completed": safe_text(w.completed_creator_count), "Status": title_label(w.status), "Active State": "Active" if w.is_active else "Inactive"} for w in waves], hide_index=True, use_container_width=True)
    for wave in waves:
        cols = st.columns(5)
        if cols[0].button("Start", key=f"campaign_ops_influencer_wave_start_{wave.id}"):
            service.start_influencer_creator_wave(actor, campaign.id, wave.id); st.rerun()
        if cols[1].button("Complete", key=f"campaign_ops_influencer_wave_complete_{wave.id}"):
            service.complete_influencer_creator_wave(actor, campaign.id, wave.id); st.rerun()
        if cols[2].button("Reopen", key=f"campaign_ops_influencer_wave_reopen_{wave.id}"):
            service.reopen_influencer_creator_wave(actor, campaign.id, wave.id); st.rerun()
        if wave.is_active and cols[3].button("Deactivate", key=f"campaign_ops_influencer_wave_deactivate_{wave.id}"):
            service.deactivate_influencer_creator_wave(actor, campaign.id, wave.id); st.rerun()
        if not wave.is_active and cols[4].button("Reactivate", key=f"campaign_ops_influencer_wave_reactivate_{wave.id}"):
            service.reactivate_influencer_creator_wave(actor, campaign.id, wave.id); st.rerun()


def render_creators(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    waves = service.list_influencer_creator_waves(actor, campaign.id)
    wave_options = {"": None, **{f"Wave {w.wave_number} {safe_text(w.wave_name)}": w.id for w in waves}}
    with st.form(f"campaign_ops_influencer_live_creator_add_{campaign.id}"):
        cols = st.columns(5)
        name = cols[0].text_input("Creator Name")
        handle = cols[1].text_input("Creator Handle")
        platform = cols[2].text_input("Platform")
        wave = cols[3].selectbox("Wave", list(wave_options))
        scheduled = cols[4].date_input("Scheduled Live Date", value=None)
        urls = st.columns(3)
        content_url = urls[0].text_input("Content URL")
        click2cart_url = urls[1].text_input("Click2Cart URL")
        retailer_url = urls[2].text_input("Retailer URL")
        impressions_required = st.checkbox("Daily Impressions Required")
        submitted = st.form_submit_button("Add Creator", type="primary")
    if submitted:
        service.create_influencer_live_creator(actor, campaign.id, name, creator_handle=trim_or_none(handle), platform=trim_or_none(platform), wave_id=wave_options[wave], scheduled_live_date=scheduled, content_url=trim_or_none(content_url), click2cart_url=trim_or_none(click2cart_url), retailer_url=trim_or_none(retailer_url), impressions_reporting_required=impressions_required, live_status="not_started")
        st.rerun()
    creators = service.list_influencer_live_creators(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Creator": c.creator_name, "Handle": safe_text(c.creator_handle), "Platform": safe_text(c.platform), "Status": title_label(c.live_status), "Draft": title_label(c.draft_status), "Approval": title_label(c.approval_status), "Scheduled": format_date(c.scheduled_live_date), "Actual Live": format_date(c.actual_live_date), "Paid End": format_date(c.paid_live_end_date), "Impressions": safe_text(c.latest_impressions), "Exception": safe_text(c.exception_status), "Active State": "Active" if c.is_active else "Inactive"} for c in creators], hide_index=True, use_container_width=True)
    for creator in creators:
        cols = st.columns(7)
        if cols[0].button("Draft", key=f"campaign_ops_influencer_creator_draft_{creator.id}"):
            service.mark_influencer_live_creator_draft_submitted(actor, campaign.id, creator.id); st.rerun()
        if cols[1].button("Approved", key=f"campaign_ops_influencer_creator_approved_{creator.id}"):
            service.mark_influencer_live_creator_approved(actor, campaign.id, creator.id); st.rerun()
        if cols[2].button("Scheduled", key=f"campaign_ops_influencer_creator_scheduled_{creator.id}"):
            service.mark_influencer_live_creator_scheduled(actor, campaign.id, creator.id, creator.scheduled_live_date); st.rerun()
        if cols[3].button("Live", key=f"campaign_ops_influencer_creator_live_{creator.id}"):
            service.mark_influencer_live_creator_live(actor, campaign.id, creator.id); st.rerun()
        if cols[4].button("Paid Complete", key=f"campaign_ops_influencer_creator_paid_{creator.id}"):
            service.mark_influencer_live_creator_paid_live_complete(actor, campaign.id, creator.id); st.rerun()
        if creator.is_active and cols[5].button("Deactivate", key=f"campaign_ops_influencer_creator_deactivate_{creator.id}"):
            service.deactivate_influencer_live_creator(actor, campaign.id, creator.id); st.rerun()
        if not creator.is_active and cols[6].button("Reactivate", key=f"campaign_ops_influencer_creator_reactivate_{creator.id}"):
            service.reactivate_influencer_live_creator(actor, campaign.id, creator.id); st.rerun()


def render_exceptions(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any) -> None:
    creators = service.list_influencer_live_creators(actor, campaign.id)
    creator_options = {"": None, **{c.creator_name: c.id for c in creators}}
    owner_options = {"": None, **{u.display_name: u.id for u in users if u.is_active}}
    with st.form(f"campaign_ops_influencer_exception_add_{campaign.id}"):
        cols = st.columns(5)
        title = cols[0].text_input("Exception Title")
        ex_type = cols[1].selectbox("Exception Type", ["", *LIVE_EXCEPTION_TYPES])
        creator = cols[2].selectbox("Creator", list(creator_options))
        owner = cols[3].selectbox("Owner", list(owner_options))
        highlighted = cols[4].checkbox("Highlighted")
        description = st.text_area("Description")
        submitted = st.form_submit_button("Add Exception", type="primary")
    if submitted:
        service.create_influencer_live_exception(actor, campaign.id, title, exception_type=trim_or_none(ex_type), live_creator_id=creator_options[creator], owner_user_id=owner_options[owner], description=trim_or_none(description), status="open", opened_date=None, is_highlighted=highlighted)
        st.rerun()
    exceptions = service.list_influencer_live_exceptions(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Urgent": "TRUE" if e.is_highlighted else "FALSE", "Type": safe_text(e.exception_type), "Title": e.exception_title, "Status": title_label(e.status), "Opened": format_date(e.opened_date), "Due": format_date(e.due_date), "Resolved": format_date(e.resolved_date), "Resolution": safe_text(e.resolution_notes), "Active State": "Active" if e.is_active else "Inactive"} for e in exceptions], hide_index=True, use_container_width=True)
    for exception in exceptions:
        cols = st.columns(4)
        if cols[0].button("Resolve", key=f"campaign_ops_influencer_exception_resolve_{exception.id}"):
            service.resolve_influencer_live_exception(actor, campaign.id, exception.id, "Resolved from Live workspace."); st.rerun()
        if cols[1].button("Reopen", key=f"campaign_ops_influencer_exception_reopen_{exception.id}"):
            service.reopen_influencer_live_exception(actor, campaign.id, exception.id); st.rerun()
        if exception.is_active and cols[2].button("Deactivate", key=f"campaign_ops_influencer_exception_deactivate_{exception.id}"):
            service.deactivate_influencer_live_exception(actor, campaign.id, exception.id); st.rerun()
        if not exception.is_active and cols[3].button("Reactivate", key=f"campaign_ops_influencer_exception_reactivate_{exception.id}"):
            service.reactivate_influencer_live_exception(actor, campaign.id, exception.id); st.rerun()


def render_timeline(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_live_timeline_add_{campaign.id}"):
        cols = st.columns(4)
        title = cols[0].text_input("Timeline Item")
        target = cols[1].date_input("Exact Date", value=None)
        start = cols[2].date_input("Start Date", value=None)
        end = cols[3].date_input("End Date", value=None)
        submitted = st.form_submit_button("Add Timeline Item", type="primary")
    if submitted:
        service.create_milestone(actor, campaign.program_id, title, workstream_id=campaign.workstream_id, milestone_type="Influencer Live", target_date=target, start_date=start, end_date=end)
        st.rerun()
    milestones = [m for m in service.list_program_milestones(actor, campaign.program_id, include_inactive=True) if m.workstream_id == campaign.workstream_id or m.milestone_type == "Influencer Live"]
    st.dataframe([{"Date": format_date(m.target_date or m.start_date), "End": format_date(m.end_date), "Item": m.title, "Status": title_label(m.status), "Active State": "Active" if m.is_active else "Inactive"} for m in milestones], hide_index=True, use_container_width=True)
    for m in milestones:
        cols = st.columns(2)
        if m.status != TaskStatus.COMPLETED.value and cols[0].button("Complete", key=f"campaign_ops_influencer_live_milestone_complete_{m.id}"):
            service.complete_milestone(actor, m.id); st.rerun()
        if m.status == TaskStatus.COMPLETED.value and cols[1].button("Reopen", key=f"campaign_ops_influencer_live_milestone_reopen_{m.id}"):
            service.reopen_milestone(actor, m.id); st.rerun()


def render_resources(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    quick = live_quick_links(campaign)
    cols = st.columns(4)
    for index, link in enumerate(quick):
        cols[index % 4].link_button(link.label, sanitize_link(link.url))
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    resources = [r for r in service.list_program_resources(actor, campaign.program_id, include_inactive=True) if r.resource_type in set(INFLUENCER_RESOURCE_TYPES) | set(LIVE_RESOURCE_TYPES) or r.workstream_id == campaign.workstream_id]
    st.dataframe(resource_table_rows(resources), hide_index=True, use_container_width=True)
    with st.form(f"campaign_ops_influencer_live_resource_add_{campaign.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Title")
        resource_type = cols[1].selectbox("Resource type", LIVE_RESOURCE_TYPES)
        url = cols[2].text_input("URL")
        submitted = st.form_submit_button("Add Resource", type="primary")
    if submitted:
        service.create_resource(actor, campaign.program_id, title=title, resource_type=resource_type, workstream_id=campaign.workstream_id, url=trim_or_none(url))
        st.rerun()
    for resource in resources:
        render_resource_actions(actor, service, summary, resource)


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    rows = [{"Timestamp": format_datetime(e.created_at), "Event": title_label(e.event_type), "Message": safe_text(e.message)} for e in summary.activity if e.event_type.startswith("influencer_live_") or e.event_type.startswith("influencer_creator_") or e.event_type == "influencer_stage_moved_to_live"]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
