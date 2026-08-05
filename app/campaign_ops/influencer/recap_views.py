from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.formatting import format_date, format_datetime, safe_text, title_label
from app.campaign_ops.influencer.recap_formatting import RECAP_COLUMNS, recap_rows
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.resource_views import render_resource_actions, resource_table_rows
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer import (
    RECAP_LAUNCH_STATUSES,
    RECAP_REQUIREMENT_TYPES,
    RECAP_RESOURCE_TYPES,
    RECAP_STATUSES,
    RESPONSIBLE_PARTIES,
)
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.reporting_requests import REQUEST_CATEGORY_REPORT, REQUEST_CATEGORY_SURVEY
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
    render_recap_portfolio(actor, service, manager_id)


def render_recap_portfolio(actor: CampaignOpsUser, service: CampaignOpsService, manager_user_id: str | None) -> None:
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
    filters = render_filters(campaigns)
    filtered = sort_rows(filter_rows(campaigns, filters), str(filters.get("sort_by") or "updated_at"))
    st.markdown("<div class='campaign-ops-influencer-title'>Influencer Recapping Portfolio</div>", unsafe_allow_html=True)
    st.dataframe(recap_rows(filtered), column_order=RECAP_COLUMNS, hide_index=True, use_container_width=True)
    for campaign in filtered:
        render_recap_block(campaign)
    if filtered:
        labels = {f"{c.campaign_title} | {safe_text(c.client_name)}": c.id for c in filtered}
        cols = st.columns(2)
        chosen = cols[0].selectbox("Open Recapping Campaign", list(labels), key="campaign_ops_influencer_recap_campaign_select")
        if cols[1].button("Open Recapping Workspace", key="campaign_ops_influencer_recap_open"):
            st.session_state["campaign_ops_selected_influencer_recap_campaign_id"] = labels[chosen]
            st.rerun()


def render_filters(campaigns: list[Any]) -> dict[str, object]:
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
        managers = {"Any": "", **{safe_text(c.manager_display_name): c.manager_user_id for c in campaigns if c.manager_user_id}}
        current["manager_user_id"] = managers[cols[3].selectbox("Manager", list(managers), key="campaign_ops_influencer_recap_manager")]
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


def render_recap_block(campaign: Any) -> None:
    status = title_label(campaign.recap_status)
    html = f"<div class='campaign-ops-influencer-block'><div class='campaign-ops-influencer-title'>{escape(campaign.campaign_title)}</div>"
    html += "<div class='campaign-ops-influencer-bar'>Track Sheet | Influencer Brief | Click2Cart / Bitly | Invoice | EOP Survey | Live Content Tracker</div>"
    rows = [
        f"Status: {escape(status)} | Waiting on: {escape(safe_text(campaign.waiting_on))} | Ready to close: {campaign.ready_to_close_state}",
        f"All creators live: {'TRUE' if campaign.all_creators_live else 'FALSE'} | Creator closeout: {escape(safe_text(campaign.creator_closeout_status))} | Open requirements: {campaign.open_requirement_count}",
        f"EOP Survey: {escape(safe_text(campaign.eop_survey_status))} | Performance data: {escape(safe_text(campaign.final_performance_data_status))} | Sales lift: {escape(safe_text(campaign.sales_lift_analysis_status))}",
        f"Recap deck: {escape(safe_text(campaign.recap_deck_status))} | Client recap: {format_date(campaign.client_recap_date)} | Invoice: {escape(safe_text(campaign.invoice_status))}",
        f"Program Notes: {escape(safe_text(campaign.latest_update))}",
    ]
    html += "".join(f"<div class='campaign-ops-influencer-row'>{row}</div>" for row in rows)
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


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
    st.info(f"Creators {summary.creator_closeout.live_creators}/{summary.creator_closeout.total_creators} live | Completed {summary.creator_closeout.completed_creators} | Missing links {summary.creator_closeout.missing_final_links} | Missing impressions {summary.creator_closeout.missing_final_impressions} | Open exceptions {summary.creator_closeout.open_creator_exceptions}")
    tabs = st.tabs(["Overview", "Recap Checklist", "Reporting & Analysis", "Product / Retailer Launches", "Creator Closeout", "Invoice & Financial Close", "Timeline", "Resources", "Program Notes", "Activity"])
    with tabs[0]:
        render_overview(actor, service, users, summary)
    with tabs[1]:
        render_checklist(actor, service, users, campaign)
    with tabs[2]:
        render_requirements(actor, service, campaign)
    with tabs[3]:
        render_launch_items(actor, service, campaign)
    with tabs[4]:
        render_creator_closeout(summary)
    with tabs[5]:
        render_financial(actor, service, summary)
    with tabs[6]:
        render_timeline(actor, service, campaign)
    with tabs[7]:
        render_resources(actor, service, campaign)
    with tabs[8]:
        render_notes(actor, service, campaign.program_id, campaign.workstream_id)
    with tabs[9]:
        render_activity(actor, service, campaign)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], summary: Any) -> None:
    campaign = summary.campaign
    record = summary.recap_record
    user_options = {u.display_name: u.id for u in users if u.is_active}
    with st.form(f"campaign_ops_influencer_recap_overview_{campaign.id}"):
        cols = st.columns(4)
        manager = cols[0].selectbox("Manager", list(user_options), index=list(user_options.values()).index(campaign.manager_user_id) if campaign.manager_user_id in user_options.values() else 0)
        recap_status = cols[1].selectbox("Recap Status", RECAP_STATUSES, index=RECAP_STATUSES.index(campaign.recap_status) if campaign.recap_status in RECAP_STATUSES else 0, format_func=title_label)
        waiting = cols[2].text_input("Waiting On", value=safe_text(record.waiting_on if record else campaign.waiting_on, ""))
        sales_required = cols[3].checkbox("Sales Lift Analysis Required", value=bool(record.sales_lift_analysis_required if record else campaign.sales_lift_analysis_required))
        latest = st.text_area("Latest Update", value=safe_text(record.latest_update if record else campaign.latest_update, ""))
        cols = st.columns(5)
        reporting_due = cols[0].date_input("Reporting Due Date", value=record.reporting_due_date if record else None)
        draft_due = cols[1].date_input("Draft Recap Due Date", value=record.draft_recap_due_date if record else None)
        internal_review = cols[2].date_input("Internal Review Date", value=record.internal_review_date if record else None)
        client_review = cols[3].date_input("Client Review Date", value=record.client_review_date if record else None)
        client_recap = cols[4].date_input("Client Recap Date", value=record.client_recap_date if record else None)
        cols = st.columns(5)
        delivered = cols[0].date_input("Recap Delivered Date", value=record.recap_delivered_date if record else None)
        final_close = cols[1].date_input("Final Close Date", value=record.final_close_date if record else None)
        sales_status = cols[2].text_input("Sales Lift Analysis Status", value=safe_text(record.sales_lift_analysis_status if record else "", ""))
        performance_status = cols[3].text_input("Final Performance Data Status", value=safe_text(record.final_performance_data_status if record else "", ""))
        closeout_status = cols[4].text_input("Creator Closeout Status", value=safe_text(record.creator_closeout_status if record else "", ""))
        cols = st.columns(3)
        eop_status = cols[0].text_input("EOP Survey Status", value=safe_text(record.eop_survey_status if record else "", ""))
        invoice_status = cols[1].text_input("Invoice Status", value=safe_text(record.invoice_status if record else campaign.invoice_status, ""))
        financial_status = cols[2].text_input("Financial Close Status", value=safe_text(record.financial_close_status if record else "", ""))
        lessons = st.text_area("Lessons Learned", value=safe_text(record.lessons_learned if record else "", ""))
        submitted = st.form_submit_button("Save Recap Overview", type="primary")
    if submitted:
        service.update_influencer_campaign(actor, campaign.id, manager_user_id=user_options[manager], influencer_stage="recapping", planning_status=recap_status)
        service.create_or_update_influencer_recap_record(actor, campaign.id, recap_status=recap_status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), reporting_due_date=reporting_due, draft_recap_due_date=draft_due, internal_review_date=internal_review, client_review_date=client_review, client_recap_date=client_recap, recap_delivered_date=delivered, final_close_date=final_close, sales_lift_analysis_required=sales_required, sales_lift_analysis_status=trim_or_none(sales_status), final_performance_data_status=trim_or_none(performance_status), creator_closeout_status=trim_or_none(closeout_status), eop_survey_status=trim_or_none(eop_status), invoice_status=trim_or_none(invoice_status), financial_close_status=trim_or_none(financial_status), lessons_learned=trim_or_none(lessons))
        st.rerun()
    st.write(f"Planning history preserved: {len(summary.planning_steps)} planning steps, {len(summary.approval_rounds)} approvals, {len(summary.content_rounds)} content rounds.")
    st.write(f"Live history preserved: {len(summary.live_checkpoints)} checkpoints, {len(summary.waves)} waves, {len(summary.creators)} creators, {len(summary.exceptions)} exceptions.")
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


def render_requirements(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    resources = service.list_program_resources(actor, campaign.program_id, include_inactive=True)
    requests = service.list_reporting_requests(actor, include_inactive=True, program_id=campaign.program_id)
    resource_options = {"": None, **{f"{r.resource_type}: {r.title}": r.id for r in resources}}
    request_options = {"": None, **{f"{r.request_type} ({title_label(r.request_category)})": r.id for r in requests}}
    with st.form(f"campaign_ops_influencer_recap_requirement_add_{campaign.id}"):
        cols = st.columns(4)
        rtype = cols[0].selectbox("Requirement Type", RECAP_REQUIREMENT_TYPES)
        title = cols[1].text_input("Requirement Title")
        required = cols[2].checkbox("Required", value=True)
        due = cols[3].date_input("Due Date", value=None)
        cols = st.columns(2)
        resource = cols[0].selectbox("Linked Resource", list(resource_options))
        request = cols[1].selectbox("Linked Survey / Reporting Request", list(request_options))
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Requirement", type="primary")
    if submitted:
        service.create_influencer_recap_requirement(actor, campaign.id, rtype, title, required=required, due_date=due, resource_id=resource_options[resource], reporting_request_id=request_options[request], notes=trim_or_none(notes), status="not_started")
        st.rerun()
    reqs = service.list_influencer_recap_requirements(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Requirement Type": r.requirement_type, "Requirement Title": r.requirement_title, "Required": "TRUE" if r.required else "FALSE", "Status": title_label(r.status), "Due Date": format_date(r.due_date), "Received Date": format_date(r.received_date), "Completed Date": format_date(r.completed_date), "Waiting On": safe_text(r.waiting_on), "Linked Resource": safe_text(r.resource_id), "Linked Request": safe_text(r.reporting_request_id), "Notes": safe_text(r.notes), "Active State": "Active" if r.is_active else "Inactive"} for r in reqs], hide_index=True, use_container_width=True)
    for r in reqs:
        cols = st.columns(5)
        if cols[0].button("Received", key=f"campaign_ops_influencer_recap_req_received_{r.id}"):
            service.mark_influencer_recap_requirement_received(actor, campaign.id, r.id); st.rerun()
        if cols[1].button("Complete", key=f"campaign_ops_influencer_recap_req_complete_{r.id}"):
            service.complete_influencer_recap_requirement(actor, campaign.id, r.id); st.rerun()
        if cols[2].button("Reopen", key=f"campaign_ops_influencer_recap_req_reopen_{r.id}"):
            service.reopen_influencer_recap_requirement(actor, campaign.id, r.id); st.rerun()
        if r.is_active and cols[3].button("Deactivate", key=f"campaign_ops_influencer_recap_req_deactivate_{r.id}"):
            service.deactivate_influencer_recap_requirement(actor, campaign.id, r.id); st.rerun()
        if not r.is_active and cols[4].button("Reactivate", key=f"campaign_ops_influencer_recap_req_reactivate_{r.id}"):
            service.reactivate_influencer_recap_requirement(actor, campaign.id, r.id); st.rerun()


def render_launch_items(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    with st.form(f"campaign_ops_influencer_recap_launch_add_{campaign.id}"):
        cols = st.columns(5)
        group = cols[0].text_input("Group")
        product = cols[1].text_input("Product")
        retailer = cols[2].text_input("Retailer")
        online = cols[3].date_input("Online Launch Date", value=None)
        in_store = cols[4].date_input("In-Store Launch Date", value=None)
        cols = st.columns(3)
        status = cols[0].selectbox("Launch Status", ["", *RECAP_LAUNCH_STATUSES], format_func=title_label)
        product_url = cols[1].text_input("Product URL")
        retailer_url = cols[2].text_input("Retailer URL")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Launch Item", type="primary")
    if submitted:
        service.create_influencer_recap_launch_item(actor, campaign.id, product, group_name=trim_or_none(group), retailer_name=trim_or_none(retailer), online_launch_date=online, in_store_launch_date=in_store, launch_status=trim_or_none(status), product_url=trim_or_none(product_url), retailer_url=trim_or_none(retailer_url), notes=trim_or_none(notes))
        st.rerun()
    items = service.list_influencer_recap_launch_items(actor, campaign.id, include_inactive=True)
    st.dataframe([{"Group": safe_text(i.group_name), "Product": i.product_name, "Retailer": safe_text(i.retailer_name), "Online Launch Date": format_date(i.online_launch_date), "In-Store Launch Date": format_date(i.in_store_launch_date), "Launch Status": title_label(i.launch_status), "Product URL": "Available" if i.product_url else "No Link", "Retailer URL": "Available" if i.retailer_url else "No Link", "Notes": safe_text(i.notes), "Sort Order": i.sort_order, "Active State": "Active" if i.is_active else "Inactive"} for i in items], hide_index=True, use_container_width=True)
    for item in items:
        cols = st.columns(4)
        if cols[0].button("Online Live", key=f"campaign_ops_influencer_recap_launch_online_{item.id}"):
            service.mark_influencer_recap_launch_online(actor, campaign.id, item.id); st.rerun()
        if cols[1].button("In-Store Live", key=f"campaign_ops_influencer_recap_launch_store_{item.id}"):
            service.mark_influencer_recap_launch_in_store(actor, campaign.id, item.id); st.rerun()
        if item.is_active and cols[2].button("Deactivate", key=f"campaign_ops_influencer_recap_launch_deactivate_{item.id}"):
            service.deactivate_influencer_recap_launch_item(actor, campaign.id, item.id); st.rerun()
        if not item.is_active and cols[3].button("Reactivate", key=f"campaign_ops_influencer_recap_launch_reactivate_{item.id}"):
            service.reactivate_influencer_recap_launch_item(actor, campaign.id, item.id); st.rerun()


def render_creator_closeout(summary: Any) -> None:
    c = summary.creator_closeout
    st.dataframe([{"Total Creators": c.total_creators, "Live Creators": c.live_creators, "Completed Creators": c.completed_creators, "Missing Final Links": c.missing_final_links, "Missing Final Impressions": c.missing_final_impressions, "Open Creator Exceptions": c.open_creator_exceptions, "Paid-Live Periods Incomplete": c.paid_live_incomplete, "Creator Closeout Status": safe_text(c.creator_closeout_status)}], hide_index=True, use_container_width=True)
    st.dataframe([{"Creator": creator.creator_name, "Status": title_label(creator.live_status), "Content URL": "Available" if creator.content_url else "Missing", "Impressions Required": "TRUE" if creator.impressions_reporting_required else "FALSE", "Latest Impressions": safe_text(creator.latest_impressions), "Paid Live End": format_date(creator.paid_live_end_date), "Active State": "Active" if creator.is_active else "Inactive"} for creator in summary.creators], hide_index=True, use_container_width=True)


def render_financial(actor: CampaignOpsUser, service: CampaignOpsService, summary: Any) -> None:
    campaign = summary.campaign
    record = summary.recap_record
    with st.form(f"campaign_ops_influencer_recap_financial_{campaign.id}"):
        cols = st.columns(4)
        invoice_date = cols[0].date_input("Invoice Date", value=campaign.invoice_date)
        invoice_status = cols[1].text_input("Invoice Status", value=safe_text(campaign.invoice_status, ""))
        invoice_amount = cols[2].number_input("Invoice Amount", min_value=0.0, value=float(campaign.invoice_amount or 0))
        final_invoice = cols[3].date_input("Final Invoice Sent Date", value=record.final_invoice_sent_date if record else None)
        financial_close = st.text_input("Payment / Financial Close Status", value=safe_text(record.financial_close_status if record else "", ""))
        notes = st.text_area("Invoice Notes", value=safe_text(record.lessons_learned if record else "", ""))
        submitted = st.form_submit_button("Save Financial Closeout", type="primary")
    if submitted:
        service.update_influencer_campaign(actor, campaign.id, influencer_stage="recapping", planning_status=campaign.recap_status, invoice_date=invoice_date, invoice_status=trim_or_none(invoice_status), invoice_amount=invoice_amount)
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


def render_resources(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    quick = [("Track Sheet", campaign.track_sheet_url), ("Influencer Brief", campaign.influencer_brief_url), ("Click2Cart Link", campaign.click2cart_link_url), ("Bitly Link", campaign.bitly_link_url), ("Invoice", campaign.invoice_url), ("EOP Survey", campaign.eop_survey_url), ("Live Content Tracker", campaign.live_content_tracker_url), ("Recap Deck", campaign.recap_deck_url), ("Final Performance Data", campaign.final_performance_data_url), ("Sales Lift Analysis", campaign.sales_lift_analysis_url)]
    st.markdown("<div class='campaign-ops-influencer-bar'>Recapping Quick Links</div>", unsafe_allow_html=True)
    cols = st.columns(4)
    for index, (label, url) in enumerate(quick):
        if url:
            cols[index % 4].link_button(label, sanitize_link(url), key=f"campaign_ops_influencer_recap_quick_{label}_{campaign.id}")
        else:
            cols[index % 4].metric(label, "No Link")
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    resources = [r for r in service.list_program_resources(actor, campaign.program_id, include_inactive=True) if r.resource_type in RECAP_RESOURCE_TYPES or r.workstream_id == campaign.workstream_id]
    st.dataframe(resource_table_rows(resources), hide_index=True, use_container_width=True)
    with st.form(f"campaign_ops_influencer_recap_resource_add_{campaign.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Title")
        resource_type = cols[1].selectbox("Resource type", RECAP_RESOURCE_TYPES)
        url = cols[2].text_input("URL")
        submitted = st.form_submit_button("Add Resource", type="primary")
    if submitted:
        service.create_resource(actor, campaign.program_id, title=title, resource_type=resource_type, workstream_id=campaign.workstream_id, url=trim_or_none(url))
        st.rerun()
    for resource in resources:
        render_resource_actions(actor, service, summary, resource)


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, campaign: Any) -> None:
    summary = service.get_program_workspace_summary(actor, campaign.program_id)
    rows = [{"Timestamp": format_datetime(e.created_at), "Event": title_label(e.event_type), "Message": safe_text(e.message)} for e in summary.activity if e.event_type.startswith("influencer_recap_") or e.event_type == "influencer_stage_moved_to_recapping" or e.event_type == "influencer_stage_completed" or e.event_type.startswith("influencer_")]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
