from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any

import streamlit as st

from app.campaign_ops.operational_editor import collect_rows, editor_styles, render_rows
from app.campaign_ops.formatting import RISK_LABELS, STATUS_LABELS, format_date, format_datetime, safe_text, title_label
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.program_router import open_program
from app.campaign_ops.retail_media.baseline import action_display_text, current_status_text, next_current_retail_media_action, normalize_retail_media_actions, over_budget
from app.campaign_ops.retail_media.formatting import channel_mix_label, retail_status_label
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsPermissionError
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import can_access_admin, require_program_access
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.retail_media import RETAIL_MEDIA_APPROVAL_STATUSES, RETAIL_MEDIA_CHANNEL_TYPES, RETAIL_MEDIA_STATUSES, RETAIL_MEDIA_STATUS_NOT_STARTED, RETAIL_MEDIA_SUBMISSION_STATUSES
from core.campaign_ops.retail_media_timeline import RetailMediaTimelineService, sort_retail_media_timeline_rows
from core.campaign_ops.service import CampaignOpsService

SELECTED = "campaign_ops_selected_retail_media_campaign_id"

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
    if st.session_state.pop("campaign_ops_retail_media_denied", False):
        st.warning("You do not have access to this program.")
    program_id = st.session_state.get(SELECTED)
    if program_id is None:
        _render_retail_media_program_list(actor, service)
        return
    render_editor(actor, RetailMediaTimelineService(service.repository), str(program_id))
    st.button("Back to programs", key=f"retail_media_back_to_programs_{program_id}", on_click=_back)


def _back():
    st.session_state.pop(SELECTED, None)
    for key in list(st.session_state):
        if key.startswith("campaign_ops_retail_media_draft_"):
            st.session_state.pop(key, None)


def _render_retail_media_program_list(actor, service: CampaignOpsService) -> None:
    try:
        programs = [
            row for row in ProgramRoutingService(service.repository).list_registry(actor)
            if row.primary_workstream_type == WorkstreamType.RETAIL_MEDIA.value
        ]
    except CampaignOpsError as exc:
        st.error(f"Unable to load Retail Media programs: {exc}")
        return

    columns = st.columns([3, 2, 2, 1])
    for column, label in zip(columns, ("Program", "Lead Owner", "Manager", "Open")):
        column.markdown(f"**{label}**")
    if not programs:
        st.info("No active Retail Media programs are available.")
    for program in programs:
        columns = st.columns([3, 2, 2, 1])
        columns[0].write(program.program_name)
        columns[1].write(program.primary_owner_name or "-")
        columns[2].write(program.manager_name or "-")
        columns[3].button(
            "Open",
            key=f"campaign_ops_retail_media_open_{program.id}",
            on_click=open_program,
            args=(st.session_state, actor, service, program.id),
        )


@st.fragment
def render_editor(actor, service, program_id):
    draft_key = f"campaign_ops_retail_media_draft_{actor.id}_{program_id}"
    version_key = f"retail_media_timeline_editor_version_{actor.id}_{program_id}"
    repo = service.repository or CampaignOpsRepository()
    try:
        program = require_program_access(repo, actor, program_id, active_only=True)
        if program.primary_workstream_type != WorkstreamType.RETAIL_MEDIA.value:
            raise CampaignOpsError("The selected Program is not a Retail Media Program.")
        snapshot = st.session_state.get(draft_key)
        if snapshot is None:
            _, rows = service.initialize_program(actor, program_id)
            ownership = service.assignment_state(actor, program_id)
            workspace = repo.get_retail_media_program_by_program(program_id)
            snapshot = {
                "rows": deepcopy(rows), "ownership": ownership,
                "editor_owner": ownership["lead_id"], "editor_manager": ownership["manager_id"],
                "lead_names": {u.id: u.display_name for u in service.list_workflow_role_users("retail_media", "lead_owner")},
                "manager_names": {u.id: u.display_name for u in service.list_workflow_role_users("retail_media", "manager")},
                "editor_records": [{"_row_id": r.id, "_draft_id": r.id, "Date": r.due_date,
                    "Action": r.action, "Done": bool(r.done), "Program Notes": r.program_notes or ""}
                    for r in sort_retail_media_timeline_rows(rows)],
                "retail_type": workspace.retail_type if workspace else "general",
            }
            st.session_state[draft_key] = snapshot
    except CampaignOpsPermissionError:
        _back()
        st.session_state["campaign_ops_retail_media_denied"] = True
        st.rerun()
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
        prefix = f"retail_media_rows_{actor.id}_{program_id}_{version}"
        for label, options, field, key in (
            ("Lead Owner", snapshot["lead_names"], "editor_owner", f"{prefix}_lead"),
            ("Manager", snapshot["manager_names"], "editor_manager", f"{prefix}_manager"),
        ):
            snapshot[field] = st.selectbox(label, list(options), format_func=options.get,
                index=list(options).index(snapshot[field]) if snapshot[field] in options else None,
                placeholder=f"Choose a {label}", key=key, disabled=not can_access_admin(actor))
        snapshot["retail_type"] = st.selectbox(
            "Retail Type",
            ["general", "incomm"],
            index=["general", "incomm"].index(snapshot.get("retail_type", "general")),
            key=f"{prefix}_retail_type",
            disabled=not can_access_admin(actor),
        )
        st.markdown("#### Timeline")
        render_rows(snapshot, prefix, actions=(
            "Finalize campaign brief and retailer scope",
            "Confirm retailer setup, login access, and account owner",
            "Collect and align product assortment and SKU list",
            "Lock media placements, exclusions, and targeting",
            "Finalize campaign launch calendar and flighting dates",
            "Submit initial assets and trafficking for review",
            "QA all targeting, creative, and placements",
            "Launch campaign and monitor pacing",
            "Review early performance and optimization opportunities",
            "Refresh creative or targeting based on results",
            "Prepare wrap-up recap and final reporting",
            "Close campaign and archive final learnings",
            "Custom",
        ))
        st.button("Save Changes", type="primary", key=f"retail_media_save_{program_id}", on_click=_save,
            args=(actor, service, program_id, draft_key, version_key, prefix))
        st.caption("Edits stay unsaved until Save Changes. Save before leaving.")


def _save(actor, service, program_id, draft_key, version_key, prefix):
    snapshot = st.session_state[draft_key]
    records = deepcopy(collect_rows(snapshot, prefix))
    lead, manager = st.session_state.get(f"{prefix}_lead"), st.session_state.get(f"{prefix}_manager")
    try:
        changes = service.save_changes(actor, program_id, records, snapshot["rows"],
            snapshot["ownership"], lead, manager, retail_type=snapshot.get("retail_type"))
    except (CampaignOpsError, ValueError) as exc:
        st.session_state[draft_key + "_message"] = (True, f"{exc} Nothing saved.")
    else:
        st.session_state.pop(draft_key, None)
        st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
        st.session_state[draft_key + "_message"] = (False, "Changes saved." if any(changes.values()) else "No changes to save.")


def render_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-rm-title { background:#2f9f9f; color:#082323; text-align:center; font-weight:700; padding:.35rem; border:1px solid #5ebcbc; }
        .campaign-ops-rm-block { border:1px solid #c7d4d4; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-rm-bar { background:#073149; color:white; padding:.35rem .55rem; font-weight:700; }
        .campaign-ops-rm-row { border-top:1px solid #dbe4e4; padding:.32rem .55rem; font-size:.9rem; }
        .campaign-ops-rm-note { background:#f8fbfb; }
        .campaign-ops-rm-card { border:1px solid #c9d4d4; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-rm-card-head { background:#32a6a6; color:#082525; padding:.42rem .6rem; font-weight:700; border-bottom:1px solid #62bcbc; }
        .campaign-ops-rm-card-meta { color:#244348; font-size:.84rem; font-weight:600; margin-top:.1rem; }
        .campaign-ops-rm-card-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.4rem; padding:.55rem; }
        .campaign-ops-rm-card-cell { border:1px solid #dbe4e4; padding:.38rem .45rem; min-height:3.2rem; }
        .campaign-ops-rm-card-label { color:#587174; font-size:.72rem; text-transform:uppercase; font-weight:700; }
        .campaign-ops-rm-card-value { color:#102f35; font-size:.9rem; margin-top:.12rem; overflow-wrap:anywhere; }
        .campaign-ops-rm-alert { color:#8a4100; font-weight:700; }
        .campaign-ops-rm-baseline { border:1px solid #c9d4d4; margin:.65rem 0 1rem 0; background:#fff; }
        .campaign-ops-rm-baseline-section { border-top:1px solid #dbe4e4; padding:.55rem .65rem; }
        .campaign-ops-rm-baseline-label { color:#587174; font-size:.72rem; text-transform:uppercase; font-weight:700; margin-bottom:.2rem; }
        @media (max-width: 900px) { .campaign-ops-rm-card-grid { grid-template-columns:1fr; } }
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
    board_data = service.get_retail_media_baseline_board_data(actor, filtered) if filtered else {"channels": {}, "activations": {}, "creative": {}, "optimizations": {}, "milestones": {}, "resources": {}}
    st.markdown("<div class='campaign-ops-rm-title'>All Retail Media Programs</div>", unsafe_allow_html=True)
    if not filtered:
        st.info("No retail media campaigns match these filters.")
    for campaign in filtered:
        render_campaign_scan_card(campaign, board_data)


def render_campaign_scan_card(campaign: Any, board_data: dict[str, Any]) -> None:
    channels = board_data.get("channels", {}).get(campaign.id, [])
    actions = normalize_retail_media_actions(
        activations=board_data.get("activations", {}).get(campaign.id, []),
        creative=board_data.get("creative", {}).get(campaign.id, []),
        optimizations=board_data.get("optimizations", {}).get(campaign.id, []),
        milestones=board_data.get("milestones", {}).get(campaign.id, []),
        channels=channels,
    )
    next_action = next_current_retail_media_action(actions)
    status = retail_status_label(campaign.retail_media_status)
    active_state = "Active" if campaign.is_active else "Inactive"
    paused = " | PAUSED" if campaign.is_paused else ""
    pause = f"<br><span class='campaign-ops-rm-alert'>{escape(safe_text(campaign.pause_reason))}</span>" if campaign.is_paused and campaign.pause_reason else ""
    risk_parts = []
    if over_budget(campaign):
        risk_parts.append("Over budget")
    if campaign.is_paused:
        risk_parts.append("Paused")
    if campaign.waiting_on:
        risk_parts.append("Waiting")
    if campaign.program_risk and campaign.program_risk != "unrated":
        risk_parts.append(RISK_LABELS.get(campaign.program_risk, title_label(campaign.program_risk)))
    meta = f"{safe_text(campaign.owner_display_name)} | {status} | {active_state}{paused}"
    dates = " | ".join(part for part in [
        f"Launch {format_date(campaign.launch_date)}" if campaign.launch_date else "",
        f"Wrap {format_date(campaign.wrap_date)}" if campaign.wrap_date else "",
    ] if part)
    html = [
        "<div class='campaign-ops-rm-card'>",
        f"<div class='campaign-ops-rm-card-head'>{escape(campaign.campaign_title)}<div class='campaign-ops-rm-card-meta'>{escape(meta)}</div></div>",
        "<div class='campaign-ops-rm-card-grid'>",
        _card_cell("Channels", escape(channel_mix_label(campaign.channel_mix))),
        _card_cell("Latest Update", escape(safe_text(campaign.latest_update)) if campaign.latest_update else "-"),
        _card_cell("Waiting On", escape(safe_text(campaign.waiting_on)) if campaign.waiting_on else "-"),
        _card_cell("Launch / Wrap", escape(dates) if dates else "-"),
        _card_cell("Current Status", escape(current_status_text(campaign)) + pause),
        _card_cell("Next / Current Action", escape(action_display_text(next_action)) + f"<br>{escape(next_action.status)}" if next_action else "No open media action."),
        _card_cell("Attention", escape(" | ".join(risk_parts)) if risk_parts else "-"),
        "</div>",
        "</div>",
    ]
    st.markdown("".join(html), unsafe_allow_html=True)
    if st.button("Open Retail Media Campaign", key=f"campaign_ops_retail_media_scan_open_{campaign.id}"):
        st.session_state["campaign_ops_selected_retail_media_campaign_id"] = campaign.id
        st.rerun()


def _card_cell(label: str, value: str) -> str:
    return f"<div class='campaign-ops-rm-card-cell'><div class='campaign-ops-rm-card-label'>{escape(label)}</div><div class='campaign-ops-rm-card-value'>{value}</div></div>"


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
        cols = st.columns(2)
        launch_date = cols[0].date_input("Launch Date", value=None)
        wrap_date = cols[1].date_input("Wrap Date", value=None)
        cols = st.columns(3)
        cadence = cols[0].text_input("Reporting Cadence")
        paused = cols[1].checkbox("Paused")
        pause_reason = cols[2].text_input("Pause Reason")
        channels = st.multiselect("Initial Channels", RETAIL_MEDIA_CHANNEL_TYPES, default=[])
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


            is_paused=paused,
            pause_reason=trim_or_none(pause_reason),
            initial_channels=[{"channel_type": channel} for channel in channels],

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
    except CampaignOpsPermissionError:
        st.session_state.pop("campaign_ops_selected_retail_media_campaign_id", None)
        st.warning("You do not have access to this program.")
        render_portfolio(actor, service)
        return
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
        f"Launch: {format_date(campaign.launch_date)} | Wrap: {format_date(campaign.wrap_date)} | "
        f"Paused: {'Yes' if campaign.is_paused else 'No'} | Risk: {RISK_LABELS.get(campaign.program_risk, campaign.program_risk)} | "
        f"Latest: {safe_text(campaign.latest_update)} | Next: {safe_text(campaign.next_milestone)} | Updated: {format_datetime(campaign.updated_at)} | {'Active' if campaign.is_active else 'Inactive'}"
    )
    tabs = st.tabs(['Overview', 'Activations / Flights', 'Creative & Approvals', 'Timeline', 'Notes', 'Activity'])
    with tabs[0]:
        render_overview(actor, service, users, campaign)
    with tabs[1]:
        render_activations(actor, service, campaign)
    with tabs[2]:
        render_creative(actor, service, campaign)
    with tabs[3]:
        render_timeline(actor, service, campaign)
    with tabs[4]:
        with st.expander("Notes", expanded=False):
            render_notes(actor, service, service.get_program_workspace_summary(actor, campaign.program_id))
    with tabs[5]:
        with st.expander("Activity", expanded=False):
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
        cols = st.columns(2)
        launch = cols[0].date_input("Launch Date", value=campaign.launch_date)
        wrap = cols[1].date_input("Wrap Date", value=campaign.wrap_date)
        cols = st.columns(2)
        paused = cols[0].checkbox("Paused", value=campaign.is_paused)
        pause_reason = cols[1].text_input("Pause Reason", value=campaign.pause_reason or "")
        submitted = st.form_submit_button("Save Overview", type="primary")
    st.caption(f"Program: {campaign.program_name} | Client: {safe_text(campaign.client_name)} | Workstream: {safe_text(campaign.workstream_id)} | Program status: {STATUS_LABELS.get(campaign.program_status, campaign.program_status)}")
    if submitted:
        try:
            service.update_retail_media_campaign(actor, campaign.id, campaign_title=title, owner_user_id=user_options[owner], retail_media_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), reporting_cadence=trim_or_none(cadence), launch_date=launch, wrap_date=wrap, is_paused=paused, pause_reason=trim_or_none(pause_reason))
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


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    rows = [
        {"Timestamp": format_datetime(event.created_at), "Event": title_label(event.event_type), "Message": safe_text(event.message)}
        for event in summary.activity
        if event.event_type.startswith("retail_media_") or event.entity_type.startswith("retail_media_")
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)
