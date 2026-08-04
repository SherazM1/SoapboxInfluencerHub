from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.formatting import RISK_LABELS, STATUS_LABELS, format_date, format_datetime, safe_text, title_label
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.resource_views import render_resource_actions, resource_table_rows
from app.campaign_ops.retail_media.formatting import (
    PORTFOLIO_COLUMNS,
    channel_mix_label,
    currency,
    percent,
    portfolio_rows,
    retail_status_label,
)
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.retail_media import (
    RETAIL_MEDIA_APPROVAL_STATUSES,
    RETAIL_MEDIA_CHANNEL_TYPES,
    RETAIL_MEDIA_RESOURCE_TYPES,
    RETAIL_MEDIA_STATUSES,
    RETAIL_MEDIA_STATUS_NOT_STARTED,
    RETAIL_MEDIA_SUBMISSION_STATUSES,
)
from core.campaign_ops.service import CampaignOpsService

SORT_OPTIONS = {
    "Recently updated": "updated_at",
    "Campaign name": "campaign_title",
    "Client": "client_name",
    "Program": "program_name",
    "Owner": "owner_display_name",
    "Status": "retail_media_status",
    "Launch date": "launch_date",
    "Next milestone": "next_milestone_date",
    "Spend to date": "total_spend",
    "Risk": "program_risk",
}


def render_retail_media(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    st.subheader("Retail Media")
    render_css()
    selected_id = st.session_state.get("campaign_ops_selected_retail_media_campaign_id")
    if selected_id:
        render_workspace(actor, service, users, str(selected_id))
        return
    view = st.radio("Retail Media view", ["Retail Media Portfolio", "New Retail Media Campaign"], horizontal=True, key="campaign_ops_retail_media_view")
    if view == "New Retail Media Campaign" or st.session_state.get("campaign_ops_retail_media_create_open"):
        render_new_campaign(actor, service, users)
    else:
        render_portfolio(actor, service)


def render_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-rm-title { background:#2f9f9f; color:#082323; text-align:center; font-weight:700; padding:.35rem; border:1px solid #5ebcbc; }
        .campaign-ops-rm-block { border:1px solid #c7d4d4; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-rm-bar { background:#073149; color:white; padding:.35rem .55rem; font-weight:700; }
        .campaign-ops-rm-row { border-top:1px solid #dbe4e4; padding:.32rem .55rem; font-size:.9rem; }
        .campaign-ops-rm-note { background:#f8fbfb; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_portfolio(actor: CampaignOpsUser, service: CampaignOpsService) -> None:
    cols = st.columns(4)
    if cols[0].button("New Retail Media Campaign", type="primary", key="campaign_ops_retail_media_new"):
        st.session_state["campaign_ops_retail_media_create_open"] = True
        st.rerun()
    include_inactive = cols[1].checkbox("Show inactive", key="campaign_ops_retail_media_show_inactive")
    if cols[2].button("Refresh", key="campaign_ops_retail_media_refresh"):
        st.rerun()
    if cols[3].button("Clear filters", key="campaign_ops_retail_media_clear_filters"):
        st.session_state["campaign_ops_retail_media_filters"] = {}
        st.rerun()
    try:
        campaigns = service.list_retail_media_campaigns(actor, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load Retail Media campaigns: {exc}")
        return
    filters = render_filters(campaigns)
    filtered = sort_campaigns(filter_campaigns(campaigns, filters), str(filters.get("sort_by") or "updated_at"))
    st.markdown("<div class='campaign-ops-rm-title'>Retail Media Portfolio</div>", unsafe_allow_html=True)
    st.dataframe(portfolio_rows(filtered), column_order=PORTFOLIO_COLUMNS, hide_index=True, use_container_width=True)
    for campaign in filtered:
        render_campaign_block(campaign)
    if filtered:
        labels = {f"{item.campaign_title} | {safe_text(item.client_name)}": item.id for item in filtered}
        cols = st.columns(2)
        chosen = cols[0].selectbox("Open campaign", list(labels), key="campaign_ops_retail_media_campaign_select")
        if cols[1].button("Open Campaign", key="campaign_ops_retail_media_campaign_open"):
            st.session_state["campaign_ops_selected_retail_media_campaign_id"] = labels[chosen]
            st.rerun()


def render_campaign_block(campaign: Any) -> None:
    rows = [
        f"Channel mix: {escape(channel_mix_label(campaign.channel_mix))} | Status: {escape(retail_status_label(campaign.retail_media_status))}",
        f"Latest update: {escape(safe_text(campaign.latest_update))}",
        f"Launch: {format_date(campaign.launch_date)} | Wrap: {format_date(campaign.wrap_date)} | Budget: {currency(campaign.overall_budget)} | Spend: {currency(campaign.total_spend)}",
        f"Tracksheet: {'Available' if campaign.tracksheet_url else 'Missing'} | Budget Tracker: {'Available' if campaign.budget_tracker_url else 'Missing'} | Optimization Log: {'Available' if campaign.optimization_log_url else 'Missing'}",
    ]
    html = f"<div class='campaign-ops-rm-block'><div class='campaign-ops-rm-bar'>{escape(campaign.campaign_title)}</div>"
    html += "".join(f"<div class='campaign-ops-rm-row'>{row}</div>" for row in rows)
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_filters(campaigns: list[Any]) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_retail_media_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Retail Media filters", expanded=True):
        cols = st.columns(4)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_retail_media_filter_search")
        clients = {"Any": "", **{safe_text(item.client_name): item.client_name for item in campaigns if item.client_name}}
        current["client_name"] = clients[cols[1].selectbox("Client", list(clients), key="campaign_ops_retail_media_filter_client")]
        programs = {"Any": "", **{item.program_name: item.program_id for item in campaigns}}
        current["program_id"] = programs[cols[2].selectbox("Program", list(programs), key="campaign_ops_retail_media_filter_program")]
        owners = {"Any": "", **{safe_text(item.owner_display_name): item.owner_user_id for item in campaigns if item.owner_user_id}}
        current["owner_user_id"] = owners[cols[3].selectbox("Owner", list(owners), key="campaign_ops_retail_media_filter_owner")]
        cols = st.columns(5)
        current["channel"] = cols[0].selectbox("Channel", ["Any", *RETAIL_MEDIA_CHANNEL_TYPES], key="campaign_ops_retail_media_filter_channel")
        current["retail_media_status"] = cols[1].selectbox("Status", ["Any", *RETAIL_MEDIA_STATUSES], key="campaign_ops_retail_media_filter_status", format_func=retail_status_label)
        current["program_risk"] = cols[2].selectbox("Risk", ["Any", *RISK_LABELS], key="campaign_ops_retail_media_filter_risk")
        current["paused"] = cols[3].selectbox("Paused", ["Any", "Paused", "Not paused"], key="campaign_ops_retail_media_filter_paused")
        current["sort_by"] = SORT_OPTIONS[cols[4].selectbox("Sort", list(SORT_OPTIONS), key="campaign_ops_retail_media_filter_sort")]
    st.session_state["campaign_ops_retail_media_filters"] = current
    return current


def filter_campaigns(campaigns: list[Any], filters: dict[str, object]) -> list[Any]:
    result = campaigns
    search = str(filters.get("search") or "").strip().lower()
    if search:
        result = [item for item in result if search in item.campaign_title.lower() or search in item.program_name.lower() or search in (item.client_name or "").lower() or search in (item.latest_update or "").lower()]
    for field in ("client_name", "program_id", "owner_user_id", "retail_media_status", "program_risk"):
        value = filters.get(field)
        if value and value != "Any":
            result = [item for item in result if getattr(item, field) == value]
    if filters.get("channel") and filters["channel"] != "Any":
        result = [item for item in result if filters["channel"] in item.channel_mix]
    if filters.get("paused") == "Paused":
        result = [item for item in result if item.is_paused]
    if filters.get("paused") == "Not paused":
        result = [item for item in result if not item.is_paused]
    return result


def sort_campaigns(campaigns: list[Any], sort_by: str) -> list[Any]:
    return sorted(campaigns, key=lambda item: (getattr(item, sort_by, None) is None, str(getattr(item, sort_by, "") or ""), item.campaign_title.lower()), reverse=sort_by == "updated_at")


def render_new_campaign(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    if st.button("Back to Retail Media Portfolio", key="campaign_ops_retail_media_create_back"):
        st.session_state["campaign_ops_retail_media_create_open"] = False
        st.rerun()
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    program_options = {program.program_name: program.id for program in programs}
    user_options = {"Unassigned": None, **{user.display_name: user.id for user in users if user.is_active}}
    if not program_options:
        st.warning("No active programs are available.")
        return
    with st.form("campaign_ops_retail_media_create_form"):
        cols = st.columns(3)
        program_label = cols[0].selectbox("Existing Program", list(program_options))
        title = cols[1].text_input("Retail Media Campaign Title")
        owner_label = cols[2].selectbox("Owner", list(user_options))
        cols = st.columns(3)
        status = cols[0].selectbox("Status", RETAIL_MEDIA_STATUSES, index=RETAIL_MEDIA_STATUSES.index(RETAIL_MEDIA_STATUS_NOT_STARTED), format_func=retail_status_label)
        latest_update = cols[1].text_input("Latest Update")
        waiting_on = cols[2].text_input("Waiting On")
        cols = st.columns(4)
        launch_date = cols[0].date_input("Launch Date", value=None)
        wrap_date = cols[1].date_input("Wrap Date", value=None)
        budget = cols[2].number_input("Overall Budget", min_value=0.0, value=0.0)
        spend = cols[3].number_input("Total Spend", min_value=0.0, value=0.0)
        cols = st.columns(3)
        cadence = cols[0].text_input("Reporting Cadence")
        paused = cols[1].checkbox("Paused")
        pause_reason = cols[2].text_input("Pause Reason")
        channels = st.multiselect("Initial Channels", RETAIL_MEDIA_CHANNEL_TYPES, default=[])
        st.caption("Optional initial resources")
        resource_urls = {resource_type: st.text_input(resource_type) for resource_type in RETAIL_MEDIA_RESOURCE_TYPES[:7]}
        submitted = st.form_submit_button("Create Retail Media Campaign", type="primary")
    if not submitted:
        return
    try:
        campaign = service.create_retail_media_campaign(
            actor,
            program_id=program_options[program_label],
            campaign_title=title,
            owner_user_id=user_options[owner_label],
            retail_media_status=status,
            latest_update=trim_or_none(latest_update),
            waiting_on=trim_or_none(waiting_on),
            launch_date=launch_date,
            wrap_date=wrap_date,
            reporting_cadence=trim_or_none(cadence),
            overall_budget=budget,
            total_spend=spend,
            is_paused=paused,
            pause_reason=trim_or_none(pause_reason),
            initial_channels=[{"channel_type": channel} for channel in channels],
            initial_resources={k: trim_or_none(v) for k, v in resource_urls.items()},
        )
    except CampaignOpsError as exc:
        st.error(f"Retail Media campaign was not created: {exc}")
        return
    st.session_state["campaign_ops_retail_media_create_open"] = False
    st.session_state["campaign_ops_selected_retail_media_campaign_id"] = campaign.id
    st.rerun()


def render_workspace(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign_id: str) -> None:
    try:
        campaign = service.get_retail_media_campaign_detail(actor, campaign_id)
    except CampaignOpsError as exc:
        st.session_state.pop("campaign_ops_selected_retail_media_campaign_id", None)
        st.error(f"Retail Media campaign unavailable: {exc}")
        return
    if st.button("Back to Retail Media Portfolio", key="campaign_ops_retail_media_workspace_back"):
        st.session_state.pop("campaign_ops_selected_retail_media_campaign_id", None)
        st.rerun()
    if st.button("Open Program Workspace", key=f"campaign_ops_retail_media_open_program_{campaign.id}"):
        set_selected_program(st.session_state, campaign.program_id)
        st.rerun()
    st.markdown(f"### {campaign.campaign_title}")
    st.caption(
        f"Client: {safe_text(campaign.client_name)} | Program: {campaign.program_name} | Owner: {safe_text(campaign.owner_display_name)} | "
        f"Status: {retail_status_label(campaign.retail_media_status)} | Channels: {channel_mix_label(campaign.channel_mix)} | "
        f"Launch: {format_date(campaign.launch_date)} | Wrap: {format_date(campaign.wrap_date)} | Budget: {currency(campaign.overall_budget)} | "
        f"Spend: {currency(campaign.total_spend)} | Paused: {'Yes' if campaign.is_paused else 'No'} | Risk: {RISK_LABELS.get(campaign.program_risk, campaign.program_risk)} | "
        f"Latest: {safe_text(campaign.latest_update)} | Next: {safe_text(campaign.next_milestone)} | Updated: {format_datetime(campaign.updated_at)} | {'Active' if campaign.is_active else 'Inactive'}"
    )
    tabs = st.tabs(["Overview", "Channels", "Activations / Flights", "Budget & Spend", "Creative & Approvals", "Timeline", "Optimization Log", "Resources", "Notes", "Activity"])
    with tabs[0]:
        render_overview(actor, service, users, campaign)
    with tabs[1]:
        render_channels(actor, service, campaign)
    with tabs[2]:
        render_activations(actor, service, campaign)
    with tabs[3]:
        render_budget(actor, service, campaign)
    with tabs[4]:
        render_creative(actor, service, campaign)
    with tabs[5]:
        render_timeline(actor, service, campaign)
    with tabs[6]:
        render_optimization(actor, service, campaign)
    with tabs[7]:
        render_resources(actor, service, campaign)
    with tabs[8]:
        render_notes(actor, service, service.get_program_workspace_summary(actor, campaign.program_id))
    with tabs[9]:
        render_activity(actor, service, campaign)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any) -> None:
    user_options = {"Unassigned": None, **{user.display_name: user.id for user in users if user.is_active}}
    current_owner = next((label for label, value in user_options.items() if value == campaign.owner_user_id), "Unassigned")
    with st.form(f"campaign_ops_retail_media_overview_{campaign.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Campaign Title", value=campaign.campaign_title)
        owner = cols[1].selectbox("Owner", list(user_options), index=list(user_options).index(current_owner))
        status = cols[2].selectbox("Status", RETAIL_MEDIA_STATUSES, index=RETAIL_MEDIA_STATUSES.index(campaign.retail_media_status or RETAIL_MEDIA_STATUS_NOT_STARTED), format_func=retail_status_label)
        cols = st.columns(3)
        latest = cols[0].text_input("Latest Update", value=campaign.latest_update or "")
        waiting = cols[1].text_input("Waiting On", value=campaign.waiting_on or "")
        cadence = cols[2].text_input("Reporting Cadence", value=campaign.reporting_cadence or "")
        cols = st.columns(4)
        launch = cols[0].date_input("Launch Date", value=campaign.launch_date)
        wrap = cols[1].date_input("Wrap Date", value=campaign.wrap_date)
        budget = cols[2].number_input("Overall Budget", min_value=0.0, value=float(campaign.overall_budget or 0))
        spend = cols[3].number_input("Total Spend", min_value=0.0, value=float(campaign.total_spend or 0))
        cols = st.columns(2)
        paused = cols[0].checkbox("Paused", value=campaign.is_paused)
        pause_reason = cols[1].text_input("Pause Reason", value=campaign.pause_reason or "")
        submitted = st.form_submit_button("Save Overview", type="primary")
    st.caption(f"Program: {campaign.program_name} | Client: {safe_text(campaign.client_name)} | Workstream: {safe_text(campaign.workstream_id)} | Program status: {STATUS_LABELS.get(campaign.program_status, campaign.program_status)}")
    if submitted:
        try:
            service.update_retail_media_campaign(actor, campaign.id, campaign_title=title, owner_user_id=user_options[owner], retail_media_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), reporting_cadence=trim_or_none(cadence), launch_date=launch, wrap_date=wrap, overall_budget=budget, total_spend=spend, is_paused=paused, pause_reason=trim_or_none(pause_reason))
        except CampaignOpsError as exc:
            st.error(f"Overview was not saved: {exc}")
            return
        st.rerun()
    cols = st.columns(2)
    if campaign.is_active and cols[0].button("Deactivate Campaign", key=f"campaign_ops_retail_media_deactivate_{campaign.id}"):
        service.deactivate_retail_media_campaign(actor, campaign.id)
        st.rerun()
    if not campaign.is_active and cols[1].button("Reactivate Campaign", key=f"campaign_ops_retail_media_reactivate_{campaign.id}"):
        service.reactivate_retail_media_campaign(actor, campaign.id)
        st.rerun()


def channel_options(channels: list[Any]) -> dict[str, str | None]:
    return {"Campaign-level": None, **{channel.channel_type: channel.id for channel in channels if channel.is_active}}


def render_channels(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    st.markdown("<div class='campaign-ops-rm-title'>Channels</div>", unsafe_allow_html=True)
    show_inactive = st.checkbox("Show inactive channels", key="campaign_ops_retail_media_channels_inactive")
    channels = service.list_retail_media_channels(actor, campaign.id, include_inactive=show_inactive)
    with st.form(f"campaign_ops_retail_media_channel_add_{campaign.id}"):
        cols = st.columns(4)
        channel_type = cols[0].selectbox("Channel Type", RETAIL_MEDIA_CHANNEL_TYPES)
        platform = cols[1].text_input("Platform")
        budget = cols[2].number_input("Budget", min_value=0.0, value=0.0)
        spend = cols[3].number_input("Spend to Date", min_value=0.0, value=0.0)
        submitted = st.form_submit_button("Add Channel", type="primary")
    if submitted:
        try:
            service.create_retail_media_channel(actor, campaign.id, channel_type=channel_type, platform_name=trim_or_none(platform), budget=budget, spend_to_date=spend)
        except CampaignOpsError as exc:
            st.error(str(exc))
        st.rerun()
    st.dataframe([{ "Channel Type": c.channel_type, "Platform": safe_text(c.platform_name), "Status": safe_text(c.status), "Budget": currency(c.budget), "Spend": currency(c.spend_to_date), "Active State": "Active" if c.is_active else "Inactive" } for c in channels], hide_index=True, use_container_width=True)
    for c in channels:
        with st.expander(f"Edit Channel: {c.channel_type}", expanded=False):
            with st.form(f"campaign_ops_retail_media_channel_edit_{c.id}"):
                cols = st.columns(4)
                new_type = cols[0].text_input("Channel Type", value=c.channel_type)
                platform = cols[1].text_input("Platform", value=c.platform_name or "")
                status = cols[2].text_input("Status", value=c.status or "")
                reporting = cols[3].text_input("Reporting Requirement", value=c.reporting_requirement or "")
                cols = st.columns(4)
                budget = cols[0].number_input("Budget", min_value=0.0, value=float(c.budget or 0), key=f"budget_{c.id}")
                spend = cols[1].number_input("Spend to Date", min_value=0.0, value=float(c.spend_to_date or 0), key=f"spend_{c.id}")
                launch = cols[2].date_input("Launch Date", value=c.launch_date)
                end = cols[3].date_input("End Date", value=c.end_date)
                save = st.form_submit_button("Save Channel")
            if save:
                service.update_retail_media_channel(actor, campaign.id, c.id, channel_type=new_type, platform_name=trim_or_none(platform), status=trim_or_none(status), reporting_requirement=trim_or_none(reporting), budget=budget, spend_to_date=spend, launch_date=launch, end_date=end)
                st.rerun()
            if c.is_active and st.button("Deactivate Channel", key=f"campaign_ops_retail_media_channel_deactivate_{c.id}"):
                service.deactivate_retail_media_channel(actor, campaign.id, c.id)
                st.rerun()
            if not c.is_active and st.button("Reactivate Channel", key=f"campaign_ops_retail_media_channel_reactivate_{c.id}"):
                service.reactivate_retail_media_channel(actor, campaign.id, c.id)
                st.rerun()


def render_activations(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    st.markdown("<div class='campaign-ops-rm-title'>Activations / Flights</div>", unsafe_allow_html=True)
    channels = service.list_retail_media_channels(actor, campaign.id, include_inactive=False)
    options = channel_options(channels)
    activations = service.list_retail_media_activations(actor, campaign.id, include_inactive=True)
    with st.form(f"campaign_ops_retail_media_activation_add_{campaign.id}"):
        cols = st.columns(4)
        name = cols[0].text_input("Activation Name")
        channel_label = cols[1].selectbox("Channel", list(options))
        status = cols[2].text_input("Status")
        hard = cols[3].checkbox("Hard Deadline")
        cols = st.columns(3)
        start = cols[0].date_input("Start Date", value=None)
        end = cols[1].date_input("End Date", value=None)
        update = cols[2].text_input("Latest Update")
        submitted = st.form_submit_button("Add Activation", type="primary")
    if submitted:
        service.create_retail_media_activation(actor, campaign.id, activation_name=name, channel_id=options[channel_label], status=trim_or_none(status), start_date=start, end_date=end, hard_deadline=hard, latest_update=trim_or_none(update))
        st.rerun()
    st.dataframe([{ "Activation": a.activation_name, "Status": safe_text(a.status), "Start": format_date(a.start_date), "End": format_date(a.end_date), "Complete": "Yes" if a.completed_at else "No", "Active State": "Active" if a.is_active else "Inactive" } for a in activations], hide_index=True, use_container_width=True)
    for a in activations:
        cols = st.columns(4)
        if not a.completed_at and cols[0].button("Complete", key=f"campaign_ops_retail_media_activation_complete_{a.id}"):
            service.complete_retail_media_activation(actor, campaign.id, a.id)
            st.rerun()
        if a.completed_at and cols[1].button("Reopen", key=f"campaign_ops_retail_media_activation_reopen_{a.id}"):
            service.reopen_retail_media_activation(actor, campaign.id, a.id)
            st.rerun()
        if a.is_active and cols[2].button("Deactivate", key=f"campaign_ops_retail_media_activation_deactivate_{a.id}"):
            service.deactivate_retail_media_activation(actor, campaign.id, a.id)
            st.rerun()
        if not a.is_active and cols[3].button("Reactivate", key=f"campaign_ops_retail_media_activation_reactivate_{a.id}"):
            service.reactivate_retail_media_activation(actor, campaign.id, a.id)
            st.rerun()


def render_budget(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    channels = service.list_retail_media_channels(actor, campaign.id, include_inactive=False)
    summary = service.retail_media_budget_summary(campaign, channels)
    cols = st.columns(4)
    cols[0].metric("Overall Budget", currency(summary["budget"]))
    cols[1].metric("Total Spend", currency(summary["spend"]))
    cols[2].metric("Remaining Budget", currency(summary["remaining"]))
    cols[3].metric("Spend Percentage", percent(summary["spend_percentage"]))
    if summary["over_budget"]:
        st.warning("Spend is over budget.")
    st.dataframe([{ "Channel": c.channel_type, "Budget": currency(c.budget), "Spend": currency(c.spend_to_date), "Remaining": currency((c.budget or 0) - (c.spend_to_date or 0)) if c.budget is not None else "-" } for c in channels], hide_index=True, use_container_width=True)


def render_creative(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    channels = service.list_retail_media_channels(actor, campaign.id)
    options = channel_options(channels)
    creative = service.list_retail_media_creative(actor, campaign.id, include_inactive=True)
    with st.form(f"campaign_ops_retail_media_creative_add_{campaign.id}"):
        cols = st.columns(4)
        name = cols[0].text_input("Creative Name")
        channel_label = cols[1].selectbox("Channel", list(options))
        approval = cols[2].selectbox("Approval Status", RETAIL_MEDIA_APPROVAL_STATUSES, format_func=title_label)
        submission = cols[3].selectbox("Submission Status", RETAIL_MEDIA_SUBMISSION_STATUSES, format_func=title_label)
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Creative Item", type="primary")
    if submitted:
        service.create_retail_media_creative(actor, campaign.id, creative_name=name, channel_id=options[channel_label], approval_status=approval, submission_status=submission, notes=trim_or_none(notes))
        st.rerun()
    st.dataframe([{ "Creative": c.creative_name, "Approval": title_label(c.approval_status), "Submission": title_label(c.submission_status), "Submitted": format_date(c.submitted_date), "Approved": format_date(c.approved_date), "Active State": "Active" if c.is_active else "Inactive" } for c in creative], hide_index=True, use_container_width=True)
    for c in creative:
        cols = st.columns(4)
        if cols[0].button("Mark Submitted", key=f"campaign_ops_retail_media_creative_submitted_{c.id}"):
            service.mark_retail_media_creative_submitted(actor, campaign.id, c.id)
            st.rerun()
        if cols[1].button("Mark Approved", key=f"campaign_ops_retail_media_creative_approved_{c.id}"):
            service.mark_retail_media_creative_approved(actor, campaign.id, c.id)
            st.rerun()
        if c.is_active and cols[2].button("Deactivate", key=f"campaign_ops_retail_media_creative_deactivate_{c.id}"):
            service.deactivate_retail_media_creative(actor, campaign.id, c.id)
            st.rerun()
        if not c.is_active and cols[3].button("Reactivate", key=f"campaign_ops_retail_media_creative_reactivate_{c.id}"):
            service.reactivate_retail_media_creative(actor, campaign.id, c.id)
            st.rerun()


def render_timeline(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    st.markdown("<div class='campaign-ops-rm-title'>Timeline</div>", unsafe_allow_html=True)
    with st.form(f"campaign_ops_retail_media_timeline_add_{campaign.id}"):
        cols = st.columns(4)
        title = cols[0].text_input("Timeline Item")
        target = cols[1].date_input("Exact Date", value=None)
        start = cols[2].date_input("Start Date", value=None)
        end = cols[3].date_input("End Date", value=None)
        hard = st.checkbox("Hard Deadline")
        submitted = st.form_submit_button("Add Timeline Item", type="primary")
    if submitted:
        service.create_milestone(actor, campaign.program_id, title, workstream_id=campaign.workstream_id, milestone_type="Retail Media", target_date=target, start_date=start, end_date=end, hard_deadline=hard)
        st.rerun()
    milestones = [m for m in service.list_program_milestones(actor, campaign.program_id, include_inactive=True) if m.workstream_id == campaign.workstream_id or m.milestone_type == "Retail Media"]
    st.dataframe([{ "Date": format_date(m.target_date or m.start_date), "End": format_date(m.end_date), "Item": m.title, "Status": title_label(m.status), "Hard Deadline": "Yes" if m.hard_deadline else "No", "Active State": "Active" if m.is_active else "Inactive" } for m in milestones], hide_index=True, use_container_width=True)
    for m in milestones:
        cols = st.columns(4)
        if m.status != TaskStatus.COMPLETED.value and cols[0].button("Complete", key=f"campaign_ops_retail_media_milestone_complete_{m.id}"):
            service.complete_milestone(actor, m.id)
            st.rerun()
        if m.status == TaskStatus.COMPLETED.value and cols[1].button("Reopen", key=f"campaign_ops_retail_media_milestone_reopen_{m.id}"):
            service.reopen_milestone(actor, m.id)
            st.rerun()
        if m.is_active and cols[2].button("Deactivate", key=f"campaign_ops_retail_media_milestone_deactivate_{m.id}"):
            service.deactivate_milestone(actor, m.id)
            st.rerun()
        if not m.is_active and cols[3].button("Reactivate", key=f"campaign_ops_retail_media_milestone_reactivate_{m.id}"):
            service.reactivate_milestone(actor, m.id)
            st.rerun()


def render_optimization(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    channels = service.list_retail_media_channels(actor, campaign.id)
    options = channel_options(channels)
    with st.form(f"campaign_ops_retail_media_optimization_add_{campaign.id}"):
        cols = st.columns(3)
        update_date = cols[0].date_input("Date")
        channel_label = cols[1].selectbox("Channel", list(options))
        opt_type = cols[2].text_input("Optimization Type")
        text = st.text_area("Update")
        submitted = st.form_submit_button("Add Optimization Update", type="primary")
    if submitted:
        service.create_retail_media_optimization(actor, campaign.id, update_date, text, channel_id=options[channel_label], optimization_type=trim_or_none(opt_type))
        st.rerun()
    updates = service.list_retail_media_optimizations(actor, campaign.id, include_inactive=True)
    st.dataframe([{ "Date": format_date(u.update_date), "Type": safe_text(u.optimization_type), "Update": u.update_text, "Active State": "Active" if u.is_active else "Inactive" } for u in updates], hide_index=True, use_container_width=True)
    for u in updates:
        cols = st.columns(2)
        if u.is_active and cols[0].button("Deactivate", key=f"campaign_ops_retail_media_optimization_deactivate_{u.id}"):
            service.deactivate_retail_media_optimization(actor, campaign.id, u.id)
            st.rerun()
        if not u.is_active and cols[1].button("Reactivate", key=f"campaign_ops_retail_media_optimization_reactivate_{u.id}"):
            service.reactivate_retail_media_optimization(actor, campaign.id, u.id)
            st.rerun()


def render_resources(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    st.markdown("<div class='campaign-ops-rm-title'>Resources</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for idx, (label, url) in enumerate((("Tracksheet", campaign.tracksheet_url), ("Budget Tracker", campaign.budget_tracker_url), ("Optimization Log", campaign.optimization_log_url))):
        if url:
            cols[idx].link_button(label, sanitize_link(url), key=f"campaign_ops_retail_media_quick_{label}_{campaign.id}")
        else:
            cols[idx].metric(label, "Missing")
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    resources = [r for r in service.list_program_resources(actor, campaign.program_id, include_inactive=True) if r.resource_type in RETAIL_MEDIA_RESOURCE_TYPES or r.workstream_id == campaign.workstream_id]
    st.dataframe(resource_table_rows(resources), hide_index=True, use_container_width=True)
    with st.form(f"campaign_ops_retail_media_resource_add_{campaign.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Title")
        resource_type = cols[1].selectbox("Resource type", RETAIL_MEDIA_RESOURCE_TYPES)
        url = cols[2].text_input("URL")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Resource", type="primary")
    if submitted:
        service.create_resource(actor, campaign.program_id, title=title, resource_type=resource_type, workstream_id=campaign.workstream_id, url=trim_or_none(url), notes=trim_or_none(notes))
        st.rerun()
    for resource in resources:
        render_resource_actions(actor, service, summary, resource)


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    rows = [
        {"Timestamp": format_datetime(event.created_at), "Event": title_label(event.event_type), "Message": safe_text(event.message)}
        for event in summary.activity
        if event.event_type.startswith("retail_media_") or event.entity_type.startswith("retail_media_")
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
