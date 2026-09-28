from __future__ import annotations

from typing import Any

import streamlit as st

from app.campaign_ops.formatting import format_date, format_datetime, safe_text, title_label
from app.campaign_ops.influencer.recap_baseline import ready_to_close_blockers, select_recap_campaign_for_open
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer import RECAP_REQUIREMENT_STATUSES, RECAP_STATUSES
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.service import CampaignOpsService

SORT_OPTIONS = {
    "Recently updated": "updated_at",
    "Campaign": "campaign_title",
    "Client": "client_name",
    "Manager": "manager_display_name",
    "Recap Status": "recap_status",
    "Reporting Due Date": "reporting_due_date",
    "Client Recap Date": "client_recap_date",
    "Open Requirements": "open_requirement_count",
    "Invoice State": "invoice_status",
    "Risk": "program_risk",
}


def render_recapping(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    render_recap_css()
    selected = st.session_state.get("campaign_ops_selected_influencer_recap_campaign_id")
    if selected:
        render_recap_workspace(actor, service, users, str(selected))
        return
    view = st.radio("Recapping view", ["All Recapping", "T - Recapping", "L - Recapping"], horizontal=True, key="campaign_ops_influencer_recap_view")
    manager_id = None
    if view.startswith("T"):
        manager_id = next((u.id for u in users if u.display_name == "T"), None)
    if view.startswith("L"):
        manager_id = next((u.id for u in users if u.display_name == "L"), None)
    render_recap_portfolio(actor, service, manager_id, current_view=view)


def render_recap_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-recap-block { border:1px solid #b7c7c7; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-recap-header { background:#2fa6a3; color:#082525; padding:.42rem .55rem; border-bottom:1px solid #268f8c; }
        .campaign-ops-recap-header-main { display:flex; justify-content:space-between; gap:.75rem; align-items:flex-start; font-weight:800; line-height:1.2; }
        .campaign-ops-recap-meta { margin-top:.16rem; font-size:.82rem; font-weight:700; color:#123b42; }
        .campaign-ops-recap-hold { background:#b00020; color:#fff; font-weight:800; padding:.12rem .42rem; border-radius:2px; white-space:nowrap; }
        .campaign-ops-recap-hold-reason { margin-top:.2rem; color:#601015; font-weight:700; font-size:.82rem; }
        .campaign-ops-recap-links { border-bottom:1px solid #d7e0e0; padding:.32rem .5rem; font-size:.82rem; }
        .campaign-ops-recap-section-title { background:#06314a; color:white; padding:.28rem .45rem; font-size:.78rem; font-weight:800; text-transform:uppercase; }
        .campaign-ops-recap-status-grid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); border-bottom:1px solid #ccdada; }
        .campaign-ops-recap-status-item { padding:.35rem .5rem; border-right:1px solid #e0e8e8; min-width:0; }
        .campaign-ops-recap-status-label { color:#526970; font-size:.72rem; font-weight:800; text-transform:uppercase; }
        .campaign-ops-recap-status-value { color:#102a32; font-size:.84rem; line-height:1.25; overflow-wrap:anywhere; }
        .campaign-ops-recap-subtext { color:#526970; font-size:.76rem; margin-top:.08rem; }
        .campaign-ops-recap-launch-row { padding:.32rem .5rem; border-bottom:1px solid #dbe4e4; font-size:.84rem; }
        .campaign-ops-recap-launch-group { color:#06314a; font-size:.76rem; font-weight:800; text-transform:uppercase; margin:.1rem 0; }
        .campaign-ops-recap-update-grid { display:grid; grid-template-columns:2fr 1fr; border-bottom:1px solid #ccdada; }
        .campaign-ops-recap-ready { padding:.42rem .5rem; border-bottom:1px solid #ccdada; }
        .campaign-ops-recap-ready-state { font-size:.92rem; font-weight:900; color:#102a32; text-transform:uppercase; }
        .campaign-ops-recap-empty { padding:.38rem .5rem; color:#62747a; font-size:.84rem; }
        @media (max-width: 900px) {
          .campaign-ops-recap-status-grid { grid-template-columns:repeat(2, minmax(0, 1fr)); }
          .campaign-ops-recap-update-grid { grid-template-columns:1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_recap_portfolio(actor: CampaignOpsUser, service: CampaignOpsService, manager_user_id: str | None, *, current_view: str = "All Recapping") -> None:
    st.caption(f"Current view: {current_view}")
    cols = st.columns(4)
    include_inactive = cols[0].checkbox("Show inactive", key="campaign_ops_influencer_recap_show_inactive")
    if cols[1].button("Refresh", key="campaign_ops_influencer_recap_refresh"):
        st.rerun()
    if cols[2].button("Clear filters", key="campaign_ops_influencer_recap_clear"):
        st.session_state["campaign_ops_influencer_recap_filters"] = {}
        st.rerun()
    try:
        campaigns = service.list_influencer_recap_campaigns(actor, include_inactive=include_inactive, manager_user_id=manager_user_id)
    except CampaignOpsError as exc:
        st.error(f"Unable to load Influencer Recapping: {exc}")
        return
    filters = render_filters(campaigns, show_manager_filter=manager_user_id is None)
    filtered = sort_rows(filter_rows(campaigns, filters), str(filters.get("sort_by") or "updated_at"))
    if not filtered:
        st.info("No recapping influencer campaigns match these filters.")
        return
    for campaign in filtered:
        render_recap_block(campaign, compact=current_view == "All Recapping")


def render_filters(campaigns: list[Any], *, show_manager_filter: bool = True) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_influencer_recap_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Recapping filters", expanded=True):
        cols = st.columns(5)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_influencer_recap_search")
        clients = {"Any": "", **{safe_text(c.client_name): c.client_name for c in campaigns if c.client_name}}
        current["client_name"] = clients[cols[1].selectbox("Client", list(clients), key="campaign_ops_influencer_recap_client")]
        programs = {"Any": "", **{c.program_name: c.program_id for c in campaigns}}
        current["program_id"] = programs[cols[2].selectbox("Program", list(programs), key="campaign_ops_influencer_recap_program")]
        if show_manager_filter:
            managers = {"Any": "", **{safe_text(c.manager_display_name): c.manager_user_id for c in campaigns if c.manager_user_id}}
            current["manager_user_id"] = managers[cols[3].selectbox("Manager", list(managers), key="campaign_ops_influencer_recap_manager")]
        else:
            current.pop("manager_user_id", None)
        current["sort_by"] = SORT_OPTIONS[cols[4].selectbox("Sort", list(SORT_OPTIONS), key="campaign_ops_influencer_recap_sort")]
        cols = st.columns(5)
        current["recap_status"] = cols[0].selectbox("Recap status", ["Any", *RECAP_STATUSES], key="campaign_ops_influencer_recap_status", format_func=title_label)
        current["waiting"] = cols[1].selectbox("Waiting On", ["Any", "Has waiting state", "No waiting state"], key="campaign_ops_influencer_recap_waiting")
        current["eop"] = cols[2].selectbox("EOP Survey", ["Any", "Complete", "Open"], key="campaign_ops_influencer_recap_eop")
        current["invoice"] = cols[3].selectbox("Invoice", ["Any", "Complete", "Open"], key="campaign_ops_influencer_recap_invoice")
        current["deck"] = cols[4].selectbox("Recap Deck", ["Any", "Complete", "Open"], key="campaign_ops_influencer_recap_deck")
        cols = st.columns(3)
        current["sales_lift"] = cols[0].selectbox("Sales Lift", ["Any", "Required", "Not required"], key="campaign_ops_influencer_recap_sales")
        current["requirements"] = cols[1].selectbox("Open Requirements", ["Any", "Has open requirements", "No open requirements"], key="campaign_ops_influencer_recap_requirements")
        current["ready"] = cols[2].selectbox("Ready to Close", ["Any", "Not Ready", "Needs Attention", "Ready to Close", "Complete"], key="campaign_ops_influencer_recap_ready")
    st.session_state["campaign_ops_influencer_recap_filters"] = current
    return current


def filter_rows(campaigns: list[Any], filters: dict[str, object]) -> list[Any]:
    rows = campaigns
    search = str(filters.get("search") or "").lower()
    if search:
        rows = [c for c in rows if search in " ".join([c.campaign_title, c.program_name, safe_text(c.client_name), safe_text(c.latest_update), safe_text(c.waiting_on)]).lower()]
    for field in ("client_name", "program_id", "manager_user_id", "recap_status"):
        value = filters.get(field)
        if value and value != "Any":
            rows = [c for c in rows if getattr(c, field) == value]
    if filters.get("waiting") == "Has waiting state":
        rows = [c for c in rows if c.waiting_on]
    if filters.get("waiting") == "No waiting state":
        rows = [c for c in rows if not c.waiting_on]
    if filters.get("eop") == "Complete":
        rows = [c for c in rows if str(c.eop_survey_status or "").lower() == "complete"]
    if filters.get("eop") == "Open":
        rows = [c for c in rows if str(c.eop_survey_status or "").lower() != "complete"]
    if filters.get("invoice") == "Complete":
        rows = [c for c in rows if str(c.invoice_status or "").lower() in ("complete", "sent", "paid")]
    if filters.get("invoice") == "Open":
        rows = [c for c in rows if str(c.invoice_status or "").lower() not in ("complete", "sent", "paid")]
    if filters.get("deck") == "Complete":
        rows = [c for c in rows if str(c.recap_deck_status or "").lower() == "complete"]
    if filters.get("deck") == "Open":
        rows = [c for c in rows if str(c.recap_deck_status or "").lower() != "complete"]
    if filters.get("sales_lift") == "Required":
        rows = [c for c in rows if c.sales_lift_analysis_required]
    if filters.get("sales_lift") == "Not required":
        rows = [c for c in rows if not c.sales_lift_analysis_required]
    if filters.get("requirements") == "Has open requirements":
        rows = [c for c in rows if c.open_requirement_count > 0]
    if filters.get("requirements") == "No open requirements":
        rows = [c for c in rows if c.open_requirement_count == 0]
    if filters.get("ready") and filters.get("ready") != "Any":
        rows = [c for c in rows if c.ready_to_close_state == filters.get("ready")]
    return rows


def sort_rows(campaigns: list[Any], sort_by: str) -> list[Any]:
    return sorted(campaigns, key=lambda c: (getattr(c, sort_by, None) is None, getattr(c, sort_by, None) or "", c.campaign_title))


def render_recap_block(campaign: Any, *, compact: bool = False) -> None:
    hold = "ON HOLD" if campaign.is_on_hold else ("Active" if campaign.is_active else "Inactive")
    st.markdown(f"### {campaign.campaign_title}")
    st.caption(f"{safe_text(campaign.manager_display_name)} | {title_label(campaign.recap_status)} | {hold}")
    if campaign.is_on_hold and campaign.hold_reason:
        st.warning(campaign.hold_reason)
    st.write(f"Recap due: {format_date(campaign.reporting_due_date)} | Next: {safe_text(campaign.next_checkpoint)} | Due: {format_date(campaign.next_checkpoint_due_date)}")
    st.write(f"Ready to close: {campaign.ready_to_close_state}")
    blockers = ready_to_close_blockers(campaign)
    if blockers:
        st.warning(" | ".join(blockers))
    if campaign.latest_update:
        st.write(campaign.latest_update)
    if campaign.waiting_on:
        st.write(f"Waiting on: {campaign.waiting_on}")
    st.caption(f"Invoice: {safe_text(campaign.invoice_status)} | Financial close: {safe_text(campaign.financial_close_status)}")
    if st.button("Open Recapping Campaign", key=f"campaign_ops_influencer_recap_open_{campaign.id}"):
        select_recap_campaign_for_open(st.session_state, campaign.id)
        st.rerun()


def render_recap_workspace(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign_id: str) -> None:
    try:
        summary = service.get_influencer_recap_workspace_summary(actor, campaign_id)
    except CampaignOpsError as exc:
        st.session_state.pop("campaign_ops_selected_influencer_recap_campaign_id", None)
        st.warning(f"Influencer Recapping campaign is no longer available: {exc}")
        return
    campaign = summary.campaign
    if st.button("Back to Influencer Recapping", key="campaign_ops_influencer_recap_back"):
        st.session_state.pop("campaign_ops_selected_influencer_recap_campaign_id", None)
        st.rerun()
    cols = st.columns(3)
    if cols[0].button("Open Program Workspace", key=f"campaign_ops_influencer_recap_program_{campaign.id}"):
        set_selected_program(st.session_state, campaign.program_id); st.rerun()
    if cols[1].button("Open Planning History", key=f"campaign_ops_influencer_recap_planning_{campaign.id}"):
        st.session_state["campaign_ops_selected_influencer_campaign_id"] = campaign.id
        st.session_state["campaign_ops_influencer_view"] = "Planning"
        st.session_state.pop("campaign_ops_selected_influencer_recap_campaign_id", None)
        st.rerun()
    if cols[2].button("Open Live History", key=f"campaign_ops_influencer_recap_live_{campaign.id}"):
        st.session_state["campaign_ops_selected_influencer_live_campaign_id"] = campaign.id
        st.session_state["campaign_ops_influencer_view"] = "Live"
        st.session_state.pop("campaign_ops_selected_influencer_recap_campaign_id", None)
        st.rerun()
    st.markdown(f"### {campaign.campaign_title}")
    st.caption(f"{safe_text(campaign.client_name)} | {campaign.program_name} | Manager: {safe_text(campaign.manager_display_name)} | Stage: {title_label(campaign.influencer_stage)} | Ready to close: {summary.ready_to_close_state}")
    st.caption(f"Creators {summary.creator_closeout.live_creators}/{summary.creator_closeout.total_creators} live | Completed {summary.creator_closeout.completed_creators} | Missing links {summary.creator_closeout.missing_final_links} | Missing impressions {summary.creator_closeout.missing_final_impressions} | Open exceptions {summary.creator_closeout.open_creator_exceptions}")
    tabs = st.tabs(['Overview', 'Recap Checklist', 'Timeline', 'Program Notes', 'Activity'])
    with tabs[0]:
        render_overview(actor, service, users, summary)
    with tabs[1]:
        render_checklist(actor, service, users, campaign)
    with tabs[2]:
        render_timeline(actor, service, campaign)
    with tabs[3]:
        with st.expander("Program Notes", expanded=False):
            render_notes(actor, service, service.get_program_workspace_summary(actor, campaign.program_id))
    with tabs[4]:
        with st.expander("Activity", expanded=False):
            render_activity(actor, service, campaign)

    render_requirement_blocker_editor(actor, service, campaign)
    render_live_blocker_return(actor, service, summary)
    with st.expander("Financial status", expanded=False):
        render_financial(actor, service, summary)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], summary: Any) -> None:
    campaign = summary.campaign
    record = summary.recap_record
    user_options = {u.display_name: u.id for u in users if u.is_active}
    with st.form(f"campaign_ops_influencer_recap_overview_{campaign.id}"):
        cols = st.columns(3)
        manager = cols[0].selectbox("Manager", list(user_options), index=list(user_options.values()).index(campaign.manager_user_id) if campaign.manager_user_id in user_options.values() else 0)
        recap_status = cols[1].selectbox("Recap Status", RECAP_STATUSES, index=RECAP_STATUSES.index(campaign.recap_status) if campaign.recap_status in RECAP_STATUSES else 0, format_func=title_label)
        waiting = cols[2].text_input("Waiting On", value=safe_text(record.waiting_on if record else campaign.waiting_on))
        latest = st.text_area("Latest Update", value=safe_text(record.latest_update if record else campaign.latest_update))
        cols = st.columns(5)
        reporting_due = cols[0].date_input("Reporting Due Date", value=record.reporting_due_date if record else None)
        draft_due = cols[1].date_input("Draft Recap Due Date", value=record.draft_recap_due_date if record else None)
        internal_review = cols[2].date_input("Internal Review Date", value=record.internal_review_date if record else None)
        client_review = cols[3].date_input("Client Review Date", value=record.client_review_date if record else None)
        client_recap = cols[4].date_input("Client Recap Date", value=record.client_recap_date if record else None)
        cols = st.columns(2)
        delivered = cols[0].date_input("Recap Delivered Date", value=record.recap_delivered_date if record else None)
        final_close = cols[1].date_input("Final Close Date", value=record.final_close_date if record else None)
        submitted = st.form_submit_button("Save Recap Overview", type="primary")
    if submitted:
        service.update_influencer_campaign(actor, campaign.id, manager_user_id=user_options[manager], influencer_stage="recapping", planning_status=recap_status)
        service.create_or_update_influencer_recap_record(actor, campaign.id, recap_status=recap_status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), reporting_due_date=reporting_due, draft_recap_due_date=draft_due, internal_review_date=internal_review, client_review_date=client_review, client_recap_date=client_recap, recap_delivered_date=delivered, final_close_date=final_close)
        st.rerun()
    override_close = st.checkbox("Administrator override close readiness", key=f"campaign_ops_influencer_recap_complete_override_{campaign.id}")
    cols = st.columns(3)
    if cols[0].button("Complete Influencer Campaign", key=f"campaign_ops_influencer_recap_complete_{campaign.id}"):
        service.complete_influencer_campaign_from_recapping(actor, campaign.id, allow_override=override_close)
        st.rerun()
    if campaign.is_active and cols[1].button("Deactivate Campaign", key=f"campaign_ops_influencer_recap_deactivate_{campaign.id}"):
        service.deactivate_influencer_campaign(actor, campaign.id); st.rerun()
    if not campaign.is_active and cols[2].button("Reactivate Campaign", key=f"campaign_ops_influencer_recap_reactivate_{campaign.id}"):
        service.reactivate_influencer_campaign(actor, campaign.id); st.rerun()


def render_checklist(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], campaign: Any) -> None:
    if st.button("Create Standard Recap Checklist", key=f"campaign_ops_influencer_recap_template_{campaign.id}"):
        service.create_standard_influencer_recap_template(actor, campaign.id); st.rerun()
    user_options = {"": None, **{u.display_name: u.id for u in users if u.is_active}}
    with st.form(f"campaign_ops_influencer_recap_checkpoint_add_{campaign.id}"):
        cols = st.columns(5)
        title = cols[0].text_input("Title")
        ctype = cols[1].text_input("Type")
        assigned = cols[2].selectbox("Assigned User", list(user_options))
        due = cols[3].date_input("Due Date", value=None)
        order = cols[4].number_input("Sequence Order", min_value=0, value=0)
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Checkpoint", type="primary")
    if submitted:
        service.create_influencer_recap_checkpoint(actor, campaign.id, title, checkpoint_type=trim_or_none(ctype), assigned_user_id=user_options[assigned], due_date=due, sequence_order=order, status="not_started", notes=trim_or_none(notes))
        st.rerun()
    checkpoints = service.list_influencer_recap_checkpoints(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Type": safe_text(c.checkpoint_type), "Title": c.checkpoint_title, "Sequence Order": c.sequence_order, "Responsible Party": safe_text(c.responsible_party), "Due Date": format_date(c.due_date), "Completed Date": format_date(c.completed_date), "Status": title_label(c.status), "Waiting On": safe_text(c.waiting_on), "Notes": safe_text(c.notes), "Hard Deadline": "TRUE" if c.hard_deadline else "FALSE", "Active State": "Active" if c.is_active else "Inactive"} for c in checkpoints], hide_index=True, use_container_width=True)
    for c in checkpoints:
        cols = st.columns(4)
        if cols[0].button("Complete", key=f"campaign_ops_influencer_recap_checkpoint_complete_{c.id}"):
            service.complete_influencer_recap_checkpoint(actor, campaign.id, c.id); st.rerun()
        if cols[1].button("Reopen", key=f"campaign_ops_influencer_recap_checkpoint_reopen_{c.id}"):
            service.reopen_influencer_recap_checkpoint(actor, campaign.id, c.id); st.rerun()
        if c.is_active and cols[2].button("Deactivate", key=f"campaign_ops_influencer_recap_checkpoint_deactivate_{c.id}"):
            service.deactivate_influencer_recap_checkpoint(actor, campaign.id, c.id); st.rerun()
        if not c.is_active and cols[3].button("Reactivate", key=f"campaign_ops_influencer_recap_checkpoint_reactivate_{c.id}"):
            service.reactivate_influencer_recap_checkpoint(actor, campaign.id, c.id); st.rerun()


def render_requirement_blocker_editor(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.expander("Advanced / Resolve recap requirement", expanded=False):
        requirements = service.list_influencer_recap_requirements(actor, campaign.id)
        if not requirements:
            st.caption("No active recap requirements.")
            return
        by_id = {item.id: item for item in requirements}
        selected = st.selectbox("Requirement to resolve", list(by_id), format_func=lambda key: by_id[key].requirement_title, key=f"campaign_ops_requirement_resolve_select_{campaign.id}")
        item = by_id[selected]
        st.caption(f"{item.requirement_type} | Due: {format_date(item.due_date)} | {'Required' if item.required else 'Optional'}")
        with st.form(f"campaign_ops_requirement_resolve_{item.id}"):
            statuses = [None, *RECAP_REQUIREMENT_STATUSES]
            status = st.selectbox("Requirement status", statuses, index=statuses.index(item.status) if item.status in statuses else 0, format_func=lambda value: title_label(value) if value else "Not set")
            due = st.date_input("Due date", value=item.due_date)
            notes = st.text_area("Notes", value=item.notes or "")
            submitted = st.form_submit_button("Save requirement")
        if submitted:
            try:
                service.update_influencer_recap_requirement(actor, campaign.id, item.id, status=status, due_date=due, notes=trim_or_none(notes))
            except CampaignOpsError as exc:
                st.error(f"Requirement was not updated: {exc}")
                return
            st.rerun()


def render_live_blocker_return(actor: CampaignOpsUser, service: CampaignOpsService, summary: Any) -> None:
    closeout = summary.creator_closeout
    if not (closeout.paid_live_incomplete or closeout.missing_final_links or closeout.missing_final_impressions or closeout.open_creator_exceptions):
        return
    with st.expander("Advanced / Resolve live closeout blockers", expanded=False):
        st.caption("Return this campaign to Live to update creator records or resolve exceptions, then move it back to Recapping. Existing recap records are retained.")
        if st.button("Return to Live to resolve blockers", key=f"campaign_ops_recap_resolve_live_{summary.campaign.id}"):
            try:
                service.update_influencer_campaign(actor, summary.campaign.id, influencer_stage="live", planning_status="live")
            except CampaignOpsError as exc:
                st.error(f"Campaign was not returned to Live: {exc}")
                return
            st.session_state.pop("campaign_ops_selected_influencer_recap_campaign_id", None)
            st.session_state["campaign_ops_selected_influencer_live_campaign_id"] = summary.campaign.id
            st.session_state["campaign_ops_influencer_view"] = "Live"
            st.rerun()


def render_financial(actor: CampaignOpsUser, service: CampaignOpsService, summary: Any) -> None:
    campaign = summary.campaign
    record = summary.recap_record
    with st.form(f"campaign_ops_influencer_recap_financial_{campaign.id}"):
        cols = st.columns(3)
        invoice_date = cols[0].date_input("Invoice Date", value=campaign.invoice_date)
        invoice_status = cols[1].text_input("Invoice Status", value=safe_text(campaign.invoice_status))
        final_invoice = cols[2].date_input("Final Invoice Sent Date", value=record.final_invoice_sent_date if record else None)
        financial_close = st.text_input("Payment / Financial Close Status", value=safe_text(record.financial_close_status if record else ""))
        notes = st.text_area("Invoice Notes", value=safe_text(record.lessons_learned if record else ""))
        submitted = st.form_submit_button("Save Financial Closeout", type="primary")
    if submitted:
        service.update_influencer_campaign(actor, campaign.id, influencer_stage="recapping", planning_status=campaign.recap_status, invoice_date=invoice_date, invoice_status=trim_or_none(invoice_status))
        service.create_or_update_influencer_recap_record(actor, campaign.id, final_invoice_sent_date=final_invoice, invoice_status=trim_or_none(invoice_status), financial_close_status=trim_or_none(financial_close), lessons_learned=trim_or_none(notes))
        st.rerun()


def render_timeline(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_recap_timeline_add_{campaign.id}"):
        cols = st.columns(4)
        title = cols[0].text_input("Timeline Item")
        target = cols[1].date_input("Exact Date", value=None)
        start = cols[2].date_input("Start Date", value=None)
        end = cols[3].date_input("End Date", value=None)
        submitted = st.form_submit_button("Add Timeline Item", type="primary")
    if submitted:
        service.create_milestone(actor, campaign.program_id, title, workstream_id=campaign.workstream_id, milestone_type="Influencer Recapping", target_date=target, start_date=start, end_date=end)
        st.rerun()
    milestones = [m for m in service.list_program_milestones(actor, campaign.program_id, include_inactive=True) if m.workstream_id == campaign.workstream_id or m.milestone_type == "Influencer Recapping"]
    st.dataframe([{"Date": format_date(m.target_date or m.start_date), "End": format_date(m.end_date), "Item": m.title, "Status": title_label(m.status), "Active State": "Active" if m.is_active else "Inactive"} for m in milestones], hide_index=True, use_container_width=True)
    for m in milestones:
        cols = st.columns(2)
        if m.status != TaskStatus.COMPLETED.value and cols[0].button("Complete", key=f"campaign_ops_influencer_recap_milestone_complete_{m.id}"):
            service.complete_milestone(actor, m.id); st.rerun()
        if m.status == TaskStatus.COMPLETED.value and cols[1].button("Reopen", key=f"campaign_ops_influencer_recap_milestone_reopen_{m.id}"):
            service.reopen_milestone(actor, m.id); st.rerun()


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    rows = [{"Timestamp": format_datetime(e.created_at), "Event": title_label(e.event_type), "Message": safe_text(e.message)} for e in summary.activity if e.event_type.startswith("influencer_recap_") or e.event_type == "influencer_stage_moved_to_recapping" or e.event_type == "influencer_stage_completed" or e.event_type.startswith("influencer_")]
    st.dataframe(rows, hide_index=True, use_container_width=True)
