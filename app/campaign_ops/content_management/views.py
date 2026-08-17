from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.content_management.baseline import (
    action_display_text,
    content_quick_links,
    current_status_text,
    group_fact_text,
    group_facts,
    grouped_content_actions,
    invoice_summary_rows,
    next_current_action,
    normalize_content_actions,
)
from app.campaign_ops.content_management.formatting import PORTFOLIO_COLUMNS, content_status_label, portfolio_rows
from app.campaign_ops.formatting import RISK_LABELS, STATUS_LABELS, format_date, format_datetime, safe_text, title_label
from app.campaign_ops.influencer.planning_baseline import compact_date
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.resource_views import render_resource_actions, resource_table_rows
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.content_management import CONTENT_RESOURCE_TYPES, CONTENT_STATUSES, CONTENT_STATUS_NOT_STARTED
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.service import CampaignOpsService

SORT_OPTIONS = {
    "Recently updated": "updated_at",
    "Program name": "content_program_title",
    "Client": "client_name",
    "Owner": "owner_display_name",
    "Status": "content_status",
    "Total SKUs": "total_sku_count",
    "Live percentage": "live_count",
    "Issue count": "issue_count",
    "Next milestone": "next_milestone_date",
    "Maintenance end date": "maintenance_end_date",
    "Risk": "program_risk",
}


def render_content_management(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    st.subheader("Content Management")
    render_css()
    selected_id = st.session_state.get("campaign_ops_selected_content_program_id")
    if selected_id:
        render_workspace(actor, service, users, str(selected_id))
        return
    view = st.radio("Content view", ["Content Management Portfolio", "New Content Program"], horizontal=True, key="campaign_ops_content_view")
    if view == "New Content Program" or st.session_state.get("campaign_ops_content_create_open"):
        render_new_program(actor, service, users)
    else:
        render_portfolio(actor, service)


def render_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-content-title { background:#32a6a6; color:#082525; text-align:center; font-weight:700; padding:.35rem; border:1px solid #62bcbc; }
        .campaign-ops-content-block { border:1px solid #c9d4d4; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-content-bar { background:#073149; color:white; padding:.35rem .55rem; font-weight:700; }
        .campaign-ops-content-row { border-top:1px solid #dbe4e4; padding:.32rem .55rem; font-size:.9rem; }
        .campaign-ops-content-subhead { background:#eef2f2; font-weight:700; padding:.25rem .45rem; border:1px solid #cfd8d8; }
        .campaign-ops-content-card { border:1px solid #c9d4d4; margin:.55rem 0 .9rem 0; background:#fff; }
        .campaign-ops-content-card-head { background:#32a6a6; color:#082525; padding:.42rem .6rem; font-weight:700; border-bottom:1px solid #62bcbc; }
        .campaign-ops-content-card-meta { color:#244348; font-size:.84rem; font-weight:600; margin-top:.1rem; }
        .campaign-ops-content-card-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.4rem; padding:.55rem; }
        .campaign-ops-content-card-cell { border:1px solid #dbe4e4; padding:.38rem .45rem; min-height:3.2rem; }
        .campaign-ops-content-card-label { color:#587174; font-size:.72rem; text-transform:uppercase; font-weight:700; }
        .campaign-ops-content-card-value { color:#102f35; font-size:.9rem; margin-top:.12rem; overflow-wrap:anywhere; }
        .campaign-ops-content-baseline { border:1px solid #c9d4d4; margin:.65rem 0 1rem 0; background:#fff; }
        .campaign-ops-content-baseline-section { border-top:1px solid #dbe4e4; padding:.55rem .65rem; }
        .campaign-ops-content-baseline-label { color:#587174; font-size:.72rem; text-transform:uppercase; font-weight:700; margin-bottom:.2rem; }
        .campaign-ops-content-action-group { margin:.5rem 0; border:1px solid #dbe4e4; }
        .campaign-ops-content-action-group-title { background:#eef2f2; color:#102f35; font-weight:700; padding:.3rem .45rem; }
        @media (max-width: 900px) { .campaign-ops-content-card-grid { grid-template-columns:1fr; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_portfolio(actor: CampaignOpsUser, service: CampaignOpsService) -> None:
    cols = st.columns(4)
    if cols[0].button("New Content Program", type="primary", key="campaign_ops_content_new"):
        st.session_state["campaign_ops_content_create_open"] = True
        st.rerun()
    include_inactive = cols[1].checkbox("Show inactive", key="campaign_ops_content_show_inactive")
    if cols[2].button("Refresh", key="campaign_ops_content_refresh"):
        st.rerun()
    if cols[3].button("Clear filters", key="campaign_ops_content_clear_filters"):
        st.session_state["campaign_ops_content_filters"] = {}
        st.rerun()
    try:
        programs = service.list_content_programs(actor, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load Content Programs: {exc}")
        return
    filters = render_filters(programs)
    filtered = sort_programs(filter_programs(programs, filters), str(filters.get("sort_by") or "updated_at"))
    board_data = service.get_content_baseline_board_data(actor, filtered) if filtered else {"groups": {}, "deliverables": {}, "submissions": {}, "monitoring": {}, "milestones": {}, "resources": {}}
    st.markdown("<div class='campaign-ops-content-title'>All Content Programs</div>", unsafe_allow_html=True)
    if not filtered:
        st.info("No content programs match these filters.")
    for program in filtered:
        render_program_scan_card(program, board_data)
    with st.expander("Content Management Portfolio Summary", expanded=False):
        st.dataframe(portfolio_rows(filtered), column_order=PORTFOLIO_COLUMNS, hide_index=True, use_container_width=True)
    if filtered:
        labels = {f"{item.content_program_title} | {safe_text(item.client_name)}": item.id for item in filtered}
        cols = st.columns(2)
        chosen = cols[0].selectbox("Open Content Program", list(labels), key="campaign_ops_content_program_select")
        if cols[1].button("Open Program", key="campaign_ops_content_program_open"):
            st.session_state["campaign_ops_selected_content_program_id"] = labels[chosen]
            st.rerun()


def render_program_scan_card(program: Any, board_data: dict[str, Any]) -> None:
    groups = board_data.get("groups", {}).get(program.id, [])
    facts = group_facts(groups)
    links = content_quick_links(program, board_data.get("resources", {}).get(program.id, []))
    actions = normalize_content_actions(
        groups=groups,
        deliverables=board_data.get("deliverables", {}).get(program.id, []),
        submissions=board_data.get("submissions", {}).get(program.id, []),
        monitoring_updates=board_data.get("monitoring", {}).get(program.id, []),
        milestones=board_data.get("milestones", {}).get(program.id, []),
    )
    next_action = next_current_action(actions, program.next_milestone, program.next_milestone_date)
    total = program.total_sku_count or program.active_sku_count
    facts_text = group_fact_text(facts, limit=4)
    meta = f"{safe_text(program.owner_display_name)} | {content_status_label(program.content_status)} | {'Active' if program.is_active else 'Inactive'}"
    html = [
        "<div class='campaign-ops-content-card'>",
        f"<div class='campaign-ops-content-card-head'>{escape(program.content_program_title)}<div class='campaign-ops-content-card-meta'>{escape(meta)}</div></div>",
        "<div class='campaign-ops-content-card-grid'>",
        _card_cell("Program Facts", f"{safe_text(total)} SKUs" + (f"<br>{escape(facts_text)}" if facts_text else "") + (f"<br>{safe_text(program.default_graphics_per_sku)} graphics per SKU" if program.default_graphics_per_sku else "")),
        _card_cell("Latest Update", escape(safe_text(program.latest_update)) if program.latest_update else "-"),
        _card_cell("Waiting On", escape(safe_text(program.waiting_on)) if program.waiting_on else "-"),
        _card_cell("Issues", f"{program.issue_count}" + (f"<br>Delivered {program.delivered_count} | Live {program.live_count}" if program.delivered_count or program.live_count else "")),
        "</div>",
    ]
    if next_action:
        html.append(f"<div class='campaign-ops-content-row'><strong>Next / Current Action</strong><br>{escape(action_display_text(next_action))} | {escape(next_action.status)}</div>")
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    if links:
        cols = st.columns(min(len(links), 6))
        for index, link in enumerate(links[:6]):
            cols[index % len(cols)].link_button(link.label, sanitize_link(link.url), key=f"campaign_ops_content_scan_link_{program.id}_{index}")
    if st.button("Open Content Program", key=f"campaign_ops_content_scan_open_{program.id}"):
        st.session_state["campaign_ops_selected_content_program_id"] = program.id
        st.rerun()


def _card_cell(label: str, value: str) -> str:
    return f"<div class='campaign-ops-content-card-cell'><div class='campaign-ops-content-card-label'>{escape(label)}</div><div class='campaign-ops-content-card-value'>{value}</div></div>"


def render_program_block(program: Any) -> None:
    html = f"<div class='campaign-ops-content-block'><div class='campaign-ops-content-bar'>{escape(program.content_program_title)}</div>"
    rows = [
        f"Status: {escape(content_status_label(program.content_status))} | SKUs: {safe_text(program.total_sku_count or program.active_sku_count)} | Groups: {escape(', '.join(program.group_names) if program.group_names else '-')}",
        f"Latest update: {escape(safe_text(program.latest_update))}",
        f"Delivered: {program.delivered_count} | Live: {program.live_count} | Issues: {program.issue_count} | Waiting on: {escape(safe_text(program.waiting_on))}",
        f"Resources: SKU List {'Available' if program.sku_list_url else 'Missing'} | Tracksheet {'Available' if program.tracksheet_url else 'Missing'} | Keyword Insights {'Available' if program.keyword_insights_url else 'Missing'}",
    ]
    html += "".join(f"<div class='campaign-ops-content-row'>{row}</div>" for row in rows)
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_filters(programs: list[Any]) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_content_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Content filters", expanded=True):
        cols = st.columns(4)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_content_filter_search")
        clients = {"Any": "", **{safe_text(item.client_name): item.client_name for item in programs if item.client_name}}
        current["client_name"] = clients[cols[1].selectbox("Client", list(clients), key="campaign_ops_content_filter_client")]
        owners = {"Any": "", **{safe_text(item.owner_display_name): item.owner_user_id for item in programs if item.owner_user_id}}
        current["owner_user_id"] = owners[cols[2].selectbox("Owner", list(owners), key="campaign_ops_content_filter_owner")]
        current["sort_by"] = SORT_OPTIONS[cols[3].selectbox("Sort", list(SORT_OPTIONS), key="campaign_ops_content_filter_sort")]
        cols = st.columns(4)
        current["content_status"] = cols[0].selectbox("Status", ["Any", *CONTENT_STATUSES], key="campaign_ops_content_filter_status", format_func=content_status_label)
        current["sku_group"] = cols[1].text_input("SKU group", value=str(current.get("sku_group", "")), key="campaign_ops_content_filter_group")
        current["issue_state"] = cols[2].selectbox("Issues", ["Any", "Has issues", "No issues"], key="campaign_ops_content_filter_issues")
        current["maintenance_state"] = cols[3].selectbox("Maintenance", ["Any", "Has maintenance end", "No maintenance end"], key="campaign_ops_content_filter_maintenance")
    st.session_state["campaign_ops_content_filters"] = current
    return current


def filter_programs(programs: list[Any], filters: dict[str, object]) -> list[Any]:
    result = programs
    search = str(filters.get("search") or "").strip().lower()
    if search:
        result = [p for p in result if search in p.content_program_title.lower() or search in p.program_name.lower() or search in (p.client_name or "").lower() or search in (p.latest_update or "").lower()]
    for field in ("client_name", "owner_user_id", "content_status"):
        value = filters.get(field)
        if value and value != "Any":
            result = [p for p in result if getattr(p, field) == value]
    group = str(filters.get("sku_group") or "").strip().lower()
    if group:
        result = [p for p in result if any(group in name.lower() for name in p.group_names)]
    if filters.get("issue_state") == "Has issues":
        result = [p for p in result if p.issue_count > 0]
    if filters.get("issue_state") == "No issues":
        result = [p for p in result if p.issue_count == 0]
    if filters.get("maintenance_state") == "Has maintenance end":
        result = [p for p in result if p.maintenance_end_date]
    if filters.get("maintenance_state") == "No maintenance end":
        result = [p for p in result if not p.maintenance_end_date]
    return result


def sort_programs(programs: list[Any], sort_by: str) -> list[Any]:
    return sorted(programs, key=lambda item: (getattr(item, sort_by, None) is None, str(getattr(item, sort_by, "") or ""), item.content_program_title.lower()), reverse=sort_by == "updated_at")


def render_new_program(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser]) -> None:
    if st.button("Back to Content Management Portfolio", key="campaign_ops_content_create_back"):
        st.session_state["campaign_ops_content_create_open"] = False
        st.rerun()
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    program_options = {program.program_name: program.id for program in programs}
    user_options = {"Unassigned": None, **{user.display_name: user.id for user in users if user.is_active}}
    if not program_options:
        st.warning("No active programs are available.")
        return
    with st.form("campaign_ops_content_create_form"):
        cols = st.columns(3)
        program_label = cols[0].selectbox("Existing Program", list(program_options))
        title = cols[1].text_input("Content Program Title")
        owner = cols[2].selectbox("Owner", list(user_options))
        cols = st.columns(3)
        status = cols[0].selectbox("Status", CONTENT_STATUSES, index=CONTENT_STATUSES.index(CONTENT_STATUS_NOT_STARTED), format_func=content_status_label)
        latest = cols[1].text_input("Latest Update")
        waiting = cols[2].text_input("Waiting On")
        cols = st.columns(4)
        total_skus = cols[0].number_input("Total SKU Count", min_value=0, value=0)
        graphics = cols[1].number_input("Default Graphics per SKU", min_value=0, value=0)
        monitoring_start = cols[2].date_input("Monitoring Start Date", value=None)
        maintenance_end = cols[3].date_input("Maintenance End Date", value=None)
        cols = st.columns(3)
        cadence = cols[0].text_input("Reporting Cadence")
        invoiced = cols[1].checkbox("Invoiced")
        invoice_status = cols[2].text_input("Invoice Status")
        groups_text = st.text_area("Initial SKU Groups", placeholder="FS, 70\n3PG, 228\nGaming, 73")
        resource_urls = {resource_type: st.text_input(resource_type) for resource_type in CONTENT_RESOURCE_TYPES[:6]}
        submitted = st.form_submit_button("Create Content Program", type="primary")
    if not submitted:
        return
    groups = []
    for index, line in enumerate(groups_text.splitlines()):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",", 1)]
        groups.append({"group_name": parts[0], "expected_sku_count": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None, "sort_order": index})
    try:
        content = service.create_content_program(actor, program_id=program_options[program_label], content_program_title=title, owner_user_id=user_options[owner], content_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), total_sku_count=total_skus, default_graphics_per_sku=graphics, monitoring_start_date=monitoring_start, maintenance_end_date=maintenance_end, reporting_cadence=trim_or_none(cadence), is_invoiced=invoiced, invoice_status=trim_or_none(invoice_status), initial_sku_groups=groups, initial_resources={k: trim_or_none(v) for k, v in resource_urls.items()})
    except CampaignOpsError as exc:
        st.error(f"Content Program was not created: {exc}")
        return
    st.session_state["campaign_ops_content_create_open"] = False
    st.session_state["campaign_ops_selected_content_program_id"] = content.id
    st.rerun()


def render_workspace(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], content_program_id: str) -> None:
    try:
        content = service.get_content_program_detail(actor, content_program_id)
    except CampaignOpsError as exc:
        st.session_state.pop("campaign_ops_selected_content_program_id", None)
        st.error(f"Content Program unavailable: {exc}")
        return
    if st.button("Back to Content Management Portfolio", key="campaign_ops_content_workspace_back"):
        st.session_state.pop("campaign_ops_selected_content_program_id", None)
        st.rerun()
    if st.button("Open Program Workspace", key=f"campaign_ops_content_open_program_{content.id}"):
        set_selected_program(st.session_state, content.program_id)
        st.rerun()
    st.markdown(f"### {content.content_program_title}")
    st.caption(f"Client: {safe_text(content.client_name)} | Shared Program: {content.program_name} | Owner: {safe_text(content.owner_display_name)} | Status: {content_status_label(content.content_status)} | SKUs: {safe_text(content.total_sku_count or content.active_sku_count)} | Groups: {len(content.group_names)} | Delivered: {content.delivered_count} | Live: {content.live_count} | Issues: {content.issue_count} | Waiting On: {safe_text(content.waiting_on)} | Maintenance End: {format_date(content.maintenance_end_date)} | Risk: {RISK_LABELS.get(content.program_risk, content.program_risk)} | Latest: {safe_text(content.latest_update)} | Next: {safe_text(content.next_milestone)} | Updated: {format_datetime(content.updated_at)} | {'Active' if content.is_active else 'Inactive'}")
    render_content_baseline_tracker(actor, service, content)
    tabs = st.tabs(["Overview", "SKU Groups", "SKUs / Products", "Deliverables", "Copy & Attributes", "Graphics / Assets", "Submission & Publication", "Monitoring & Maintenance", "Invoicing", "Timeline", "Resources", "Notes", "Activity"])
    with tabs[0]: render_overview(actor, service, users, content)
    with tabs[1]: render_sku_groups(actor, service, content)
    with tabs[2]: render_skus(actor, service, content)
    with tabs[3]: render_deliverables(actor, service, content)
    with tabs[4]: render_copy_attributes(actor, service, content)
    with tabs[5]: render_graphics(actor, service, content)
    with tabs[6]: render_submissions(actor, service, content)
    with tabs[7]: render_monitoring(actor, service, content)
    with tabs[8]: render_invoices(actor, service, content)
    with tabs[9]: render_timeline(actor, service, content)
    with tabs[10]: render_resources(actor, service, content)
    with tabs[11]: render_notes(actor, service, service.get_program_workspace_summary(actor, content.program_id))
    with tabs[12]: render_activity(actor, service, content)


def render_overview(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], content: Any) -> None:
    user_options = {"Unassigned": None, **{u.display_name: u.id for u in users if u.is_active}}
    current_owner = next((label for label, value in user_options.items() if value == content.owner_user_id), "Unassigned")
    with st.form(f"campaign_ops_content_overview_{content.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Content Program Title", value=content.content_program_title)
        owner = cols[1].selectbox("Owner", list(user_options), index=list(user_options).index(current_owner))
        status = cols[2].selectbox("Status", CONTENT_STATUSES, index=CONTENT_STATUSES.index(content.content_status or CONTENT_STATUS_NOT_STARTED), format_func=content_status_label)
        cols = st.columns(3)
        latest = cols[0].text_input("Latest Update", value=content.latest_update or "")
        waiting = cols[1].text_input("Waiting On", value=content.waiting_on or "")
        cadence = cols[2].text_input("Reporting Cadence", value=content.reporting_cadence or "")
        cols = st.columns(4)
        total = cols[0].number_input("Total SKU Count", min_value=0, value=int(content.total_sku_count or 0))
        graphics = cols[1].number_input("Default Graphics per SKU", min_value=0, value=int(content.default_graphics_per_sku or 0))
        monitoring = cols[2].date_input("Monitoring Start Date", value=content.monitoring_start_date)
        maintenance = cols[3].date_input("Maintenance End Date", value=content.maintenance_end_date)
        cols = st.columns(2)
        invoiced = cols[0].checkbox("Invoiced", value=content.is_invoiced)
        invoice_status = cols[1].text_input("Invoice Status", value=content.invoice_status or "")
        submitted = st.form_submit_button("Save Overview", type="primary")
    st.caption(f"Program: {content.program_name} | Client: {safe_text(content.client_name)} | Workstream: {safe_text(content.workstream_id)} | Program status: {STATUS_LABELS.get(content.program_status, content.program_status)}")
    if submitted:
        service.update_content_program(actor, content.id, content_program_title=title, owner_user_id=user_options[owner], content_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), reporting_cadence=trim_or_none(cadence), total_sku_count=total, default_graphics_per_sku=graphics, monitoring_start_date=monitoring, maintenance_end_date=maintenance, is_invoiced=invoiced, invoice_status=trim_or_none(invoice_status))
        st.rerun()
    cols = st.columns(2)
    if content.is_active and cols[0].button("Deactivate Content Program", key=f"campaign_ops_content_deactivate_{content.id}"):
        service.deactivate_content_program(actor, content.id)
        st.rerun()
    if not content.is_active and cols[1].button("Reactivate Content Program", key=f"campaign_ops_content_reactivate_{content.id}"):
        service.reactivate_content_program(actor, content.id)
        st.rerun()


def render_content_baseline_tracker(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    groups = service.list_content_sku_groups(actor, content.id)
    facts = group_facts(groups)
    resources = [r for r in service.list_program_resources(actor, content.program_id, include_inactive=True) if r.resource_type in CONTENT_RESOURCE_TYPES or r.workstream_id == content.workstream_id]
    deliverables = service.list_content_deliverables(actor, content.id, include_inactive=True)
    submissions = service.list_content_submissions(actor, content.id, include_inactive=True)
    monitoring_updates = service.list_content_monitoring_updates(actor, content.id, include_inactive=True)
    milestones = [m for m in service.list_program_milestones(actor, content.program_id, include_inactive=True) if m.workstream_id == content.workstream_id or m.milestone_type == "Content Management"]
    actions = normalize_content_actions(groups=groups, deliverables=deliverables, submissions=submissions, monitoring_updates=monitoring_updates, milestones=milestones)
    links = content_quick_links(content, resources, include_custom=True)
    invoices = invoice_summary_rows(service.list_content_invoice_checkpoints(actor, content.id, include_inactive=True))
    notes = service.list_program_notes(actor, content.program_id, limit=5)

    st.markdown("<div class='campaign-ops-content-baseline'><div class='campaign-ops-content-card-head'>Content Program Baseline</div>", unsafe_allow_html=True)
    header = f"{safe_text(content.owner_display_name)} | {content_status_label(content.content_status)} | {safe_text(content.client_name)} | {content.program_name} | {'Active' if content.is_active else 'Inactive'}"
    st.markdown(f"<div class='campaign-ops-content-baseline-section'><div class='campaign-ops-content-baseline-label'>Program Header</div>{escape(content.content_program_title)}<br><span class='campaign-ops-content-card-meta'>{escape(header)}</span></div>", unsafe_allow_html=True)
    fact_rows = [
        f"Total SKUs {safe_text(content.total_sku_count or content.active_sku_count)}",
        f"Graphics per SKU {safe_text(content.default_graphics_per_sku)}" if content.default_graphics_per_sku else "",
        f"Delivered {content.delivered_count}",
        f"Live {content.live_count}",
        f"Issues {content.issue_count}",
        f"Maintenance ends {format_date(content.maintenance_end_date)}" if content.maintenance_end_date else "",
    ]
    fact_rows.extend(f"{fact.name} {safe_text(fact.expected_sku_count)}" for fact in facts)
    st.markdown(f"<div class='campaign-ops-content-baseline-section'><div class='campaign-ops-content-baseline-label'>Program Facts</div>{escape(' | '.join(item for item in fact_rows if item))}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if links:
        st.markdown("#### Linked Sheets")
        cols = st.columns(min(len(links), 6))
        for index, link in enumerate(links):
            cols[index % len(cols)].link_button(link.label, sanitize_link(link.url), key=f"campaign_ops_content_baseline_link_{content.id}_{index}")

    st.markdown("#### Grouped Content Actions")
    grouped = grouped_content_actions(actions, facts)
    if grouped:
        for group_name, rows in grouped:
            st.markdown(f"<div class='campaign-ops-content-action-group'><div class='campaign-ops-content-action-group-title'>{escape(group_name.upper())}</div></div>", unsafe_allow_html=True)
            st.dataframe(
                [
                    {
                        "Date": compact_date(row.display_date),
                        "Action": row.action,
                        "Status": row.status,
                        "Note": safe_text(row.note or row.waiting_on),
                        "Source": row.source,
                    }
                    for row in rows
                ],
                hide_index=True,
                use_container_width=True,
            )
    else:
        st.info("No content actions yet.")

    st.markdown("#### Current Status")
    st.write(current_status_text(content, monitoring_updates))
    cols = st.columns(2)
    if content.latest_update:
        cols[0].markdown(f"**Latest Update**  \n{content.latest_update}")
    if content.waiting_on:
        cols[1].markdown(f"**Waiting On**  \n{content.waiting_on}")
    if notes:
        st.markdown("#### Program Notes")
        for note in notes[:3]:
            st.caption(f"{safe_text(note.author_display_name)} | {format_datetime(note.created_at)}")
            st.write(note.note_text)
    if invoices:
        st.markdown("#### Invoicing")
        st.dataframe(invoices, hide_index=True, use_container_width=True)
    st.caption("Existing workspace tabs remain below for detailed editing and history.")


def group_options(groups: list[Any]) -> dict[str, str | None]:
    return {"Program-level": None, **{g.group_name: g.id for g in groups if g.is_active}}


def sku_options(skus: list[Any]) -> dict[str, str | None]:
    return {"No SKU": None, **{s.product_name: s.id for s in skus if s.is_active}}


def render_sku_groups(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    st.markdown("<div class='campaign-ops-content-title'>SKU Groups</div>", unsafe_allow_html=True)
    groups = service.list_content_sku_groups(actor, content.id, include_inactive=True)
    with st.form(f"campaign_ops_content_group_add_{content.id}"):
        cols = st.columns(5)
        name = cols[0].text_input("Group Name")
        brand = cols[1].text_input("Brand")
        count = cols[2].number_input("Expected SKU Count", min_value=0, value=0)
        graphics = cols[3].number_input("Graphics per SKU", min_value=0, value=0)
        sort = cols[4].number_input("Sort Order", min_value=0, value=0)
        submitted = st.form_submit_button("Add Group", type="primary")
    if submitted:
        service.create_content_sku_group(actor, content.id, name, brand_name=trim_or_none(brand), expected_sku_count=count, graphics_per_sku=graphics, sort_order=sort)
        st.rerun()
    st.dataframe([{"Group": g.group_name, "Brand": safe_text(g.brand_name), "Expected SKUs": safe_text(g.expected_sku_count), "Graphics/SKU": safe_text(g.graphics_per_sku), "Status": safe_text(g.status), "Active State": "Active" if g.is_active else "Inactive"} for g in groups], hide_index=True, use_container_width=True)
    for g in groups:
        cols = st.columns(3)
        if g.is_active and cols[0].button("Deactivate", key=f"campaign_ops_content_group_deactivate_{g.id}"):
            service.deactivate_content_sku_group(actor, content.id, g.id); st.rerun()
        if not g.is_active and cols[1].button("Reactivate", key=f"campaign_ops_content_group_reactivate_{g.id}"):
            service.reactivate_content_sku_group(actor, content.id, g.id); st.rerun()


def render_skus(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    groups = service.list_content_sku_groups(actor, content.id)
    options = group_options(groups)
    skus = service.list_content_skus(actor, content.id, include_inactive=True)
    with st.form(f"campaign_ops_content_sku_add_{content.id}"):
        cols = st.columns(4)
        product = cols[0].text_input("Product Name")
        sku_code = cols[1].text_input("SKU Code")
        group = cols[2].selectbox("SKU Group", list(options))
        upc = cols[3].text_input("UPC")
        submitted = st.form_submit_button("Add SKU", type="primary")
    if submitted:
        service.create_content_sku(actor, content.id, product_name=product, sku_code=trim_or_none(sku_code), sku_group_id=options[group], upc=trim_or_none(upc))
        st.rerun()
    st.dataframe([{"SKU Code": safe_text(s.sku_code), "Product": s.product_name, "Copy": title_label(s.copy_status), "Attributes": safe_text(s.attribute_status), "Graphics": title_label(s.graphics_status), "Submission": title_label(s.submission_status), "Publication": title_label(s.publication_status), "Issue": safe_text(s.issue_status), "Active State": "Active" if s.is_active else "Inactive"} for s in skus], hide_index=True, use_container_width=True)
    for s in skus:
        cols = st.columns(5)
        if cols[0].button("Mark Live", key=f"campaign_ops_content_sku_live_{s.id}"):
            service.mark_content_sku_live(actor, content.id, s.id, s.live_url); st.rerun()
        if cols[1].button("Mark Issue", key=f"campaign_ops_content_sku_issue_{s.id}"):
            service.mark_content_sku_issue_found(actor, content.id, s.id); st.rerun()
        if cols[2].button("Clear Issue", key=f"campaign_ops_content_sku_clear_{s.id}"):
            service.clear_content_sku_issue(actor, content.id, s.id); st.rerun()
        if s.is_active and cols[3].button("Deactivate", key=f"campaign_ops_content_sku_deactivate_{s.id}"):
            service.deactivate_content_sku(actor, content.id, s.id); st.rerun()
        if not s.is_active and cols[4].button("Reactivate", key=f"campaign_ops_content_sku_reactivate_{s.id}"):
            service.reactivate_content_sku(actor, content.id, s.id); st.rerun()


def render_deliverables(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    groups = service.list_content_sku_groups(actor, content.id)
    skus = service.list_content_skus(actor, content.id)
    group_map = group_options(groups)
    sku_map = sku_options(skus)
    deliverables = service.list_content_deliverables(actor, content.id, include_inactive=True)
    with st.form(f"campaign_ops_content_deliverable_add_{content.id}"):
        cols = st.columns(4)
        name = cols[0].text_input("Deliverable Name")
        dtype = cols[1].text_input("Deliverable Type")
        group = cols[2].selectbox("SKU Group", list(group_map))
        sku = cols[3].selectbox("SKU", list(sku_map))
        cols = st.columns(4)
        due = cols[0].date_input("Due Date", value=None)
        required = cols[1].number_input("Required Quantity", min_value=0, value=0)
        completed = cols[2].number_input("Completed Quantity", min_value=0, value=0)
        waiting = cols[3].text_input("Waiting On")
        submitted = st.form_submit_button("Add Deliverable", type="primary")
    if submitted:
        service.create_content_deliverable(actor, content.id, deliverable_name=name, deliverable_type=trim_or_none(dtype), sku_group_id=group_map[group], sku_id=sku_map[sku], due_date=due, required_quantity=required, completed_quantity=completed, waiting_on=trim_or_none(waiting))
        st.rerun()
    st.dataframe([{"Deliverable": d.deliverable_name, "Type": safe_text(d.deliverable_type), "Status": safe_text(d.status), "Approval": safe_text(d.approval_status), "Due": format_date(d.due_date), "Delivered": format_date(d.delivered_date), "Approved": format_date(d.approved_date), "Active State": "Active" if d.is_active else "Inactive"} for d in deliverables], hide_index=True, use_container_width=True)
    for d in deliverables:
        cols = st.columns(5)
        if cols[0].button("Delivered", key=f"campaign_ops_content_deliverable_delivered_{d.id}"):
            service.mark_content_deliverable_delivered(actor, content.id, d.id); st.rerun()
        if cols[1].button("Approved", key=f"campaign_ops_content_deliverable_approved_{d.id}"):
            service.mark_content_deliverable_approved(actor, content.id, d.id); st.rerun()
        if cols[2].button("Reopen", key=f"campaign_ops_content_deliverable_reopen_{d.id}"):
            service.reopen_content_deliverable(actor, content.id, d.id); st.rerun()
        if d.is_active and cols[3].button("Deactivate", key=f"campaign_ops_content_deliverable_deactivate_{d.id}"):
            service.deactivate_content_deliverable(actor, content.id, d.id); st.rerun()
        if not d.is_active and cols[4].button("Reactivate", key=f"campaign_ops_content_deliverable_reactivate_{d.id}"):
            service.reactivate_content_deliverable(actor, content.id, d.id); st.rerun()


def render_copy_attributes(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    skus = service.list_content_skus(actor, content.id, include_inactive=True)
    st.dataframe([{"SKU / Product": s.product_name, "Copy Status": title_label(s.copy_status), "Attribute Status": safe_text(s.attribute_status), "Waiting On": safe_text(s.waiting_on), "Last Updated": format_datetime(s.updated_at), "Issue State": safe_text(s.issue_status)} for s in skus], hide_index=True, use_container_width=True)


def render_graphics(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    deliverables = [d for d in service.list_content_deliverables(actor, content.id, include_inactive=True) if "graphic" in (d.deliverable_type or d.deliverable_name).lower() or "photo" in (d.deliverable_type or d.deliverable_name).lower()]
    st.dataframe([{"SKU / Group": safe_text(d.sku_id or d.sku_group_id), "Required Graphics": safe_text(d.required_quantity), "Completed Graphics": safe_text(d.completed_quantity), "Graphics Status": safe_text(d.status), "Approval Status": safe_text(d.approval_status), "Due Date": format_date(d.due_date), "Waiting On": safe_text(d.waiting_on)} for d in deliverables], hide_index=True, use_container_width=True)


def render_submissions(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    groups = service.list_content_sku_groups(actor, content.id)
    skus = service.list_content_skus(actor, content.id)
    group_map = group_options(groups)
    sku_map = sku_options(skus)
    with st.form(f"campaign_ops_content_submission_add_{content.id}"):
        cols = st.columns(4)
        group = cols[0].selectbox("SKU Group", list(group_map))
        sku = cols[1].selectbox("SKU", list(sku_map))
        platform = cols[2].text_input("Retailer or Platform")
        stype = cols[3].text_input("Submission Type")
        submitted = st.form_submit_button("Add Submission", type="primary")
    if submitted:
        service.create_content_submission(actor, content.id, sku_group_id=group_map[group], sku_id=sku_map[sku], retailer_or_platform=trim_or_none(platform), submission_type=trim_or_none(stype), status="not_submitted")
        st.rerun()
    submissions = service.list_content_submissions(actor, content.id, include_inactive=True)
    st.dataframe([{"Platform": safe_text(s.retailer_or_platform), "Type": safe_text(s.submission_type), "Status": safe_text(s.status), "Submitted": format_date(s.submitted_date), "Approved": format_date(s.approved_date), "Expected Live": format_date(s.expected_live_date), "Published": format_date(s.published_date), "Issue": safe_text(s.issue_text), "Active State": "Active" if s.is_active else "Inactive"} for s in submissions], hide_index=True, use_container_width=True)
    for s in submissions:
        cols = st.columns(7)
        if cols[0].button("Submitted", key=f"campaign_ops_content_submission_submitted_{s.id}"):
            service.mark_content_submission_submitted(actor, content.id, s.id); st.rerun()
        if cols[1].button("Approved", key=f"campaign_ops_content_submission_approved_{s.id}"):
            service.mark_content_submission_approved(actor, content.id, s.id); st.rerun()
        if cols[2].button("Published", key=f"campaign_ops_content_submission_published_{s.id}"):
            service.mark_content_submission_published(actor, content.id, s.id, live_url=s.live_url); st.rerun()
        if cols[3].button("Issue", key=f"campaign_ops_content_submission_issue_{s.id}"):
            service.mark_content_submission_issue(actor, content.id, s.id, "Publication issue discovered"); st.rerun()
        if cols[4].button("Resolve", key=f"campaign_ops_content_submission_resolve_{s.id}"):
            service.resolve_content_submission_issue(actor, content.id, s.id); st.rerun()
        if s.is_active and cols[5].button("Deactivate", key=f"campaign_ops_content_submission_deactivate_{s.id}"):
            service.deactivate_content_submission(actor, content.id, s.id); st.rerun()
        if not s.is_active and cols[6].button("Reactivate", key=f"campaign_ops_content_submission_reactivate_{s.id}"):
            service.reactivate_content_submission(actor, content.id, s.id); st.rerun()


def render_monitoring(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    with st.form(f"campaign_ops_content_monitoring_add_{content.id}"):
        cols = st.columns(3)
        update_date = cols[0].date_input("Date")
        update_type = cols[1].text_input("Update Type")
        live_reviews = cols[2].number_input("Live Review Count", min_value=0, value=0)
        update = st.text_area("Update")
        submitted = st.form_submit_button("Add Monitoring Update", type="primary")
    if submitted:
        service.create_content_monitoring_update(actor, content.id, update_date, update, update_type=trim_or_none(update_type), live_review_count=live_reviews)
        st.rerun()
    updates = service.list_content_monitoring_updates(actor, content.id, include_inactive=True)
    st.dataframe([{"Date": format_date(u.update_date), "Type": safe_text(u.update_type), "Update": u.update_text, "Live Reviews": safe_text(u.live_review_count), "Publication State": safe_text(u.publication_state), "Active State": "Active" if u.is_active else "Inactive"} for u in updates], hide_index=True, use_container_width=True)
    for update in updates:
        cols = st.columns(2)
        if update.is_active and cols[0].button("Deactivate", key=f"campaign_ops_content_monitoring_deactivate_{update.id}"):
            service.deactivate_content_monitoring_update(actor, content.id, update.id); st.rerun()
        if not update.is_active and cols[1].button("Reactivate", key=f"campaign_ops_content_monitoring_reactivate_{update.id}"):
            service.reactivate_content_monitoring_update(actor, content.id, update.id); st.rerun()


def render_invoices(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    with st.form(f"campaign_ops_content_invoice_add_{content.id}"):
        cols = st.columns(4)
        name = cols[0].text_input("Checkpoint Name")
        due = cols[1].date_input("Due Date", value=None)
        amount = cols[2].number_input("Amount", min_value=0.0, value=0.0)
        status = cols[3].text_input("Status")
        submitted = st.form_submit_button("Add Invoice Checkpoint", type="primary")
    if submitted:
        service.create_content_invoice_checkpoint(actor, content.id, name, due_date=due, amount=amount, status=trim_or_none(status))
        st.rerun()
    checkpoints = service.list_content_invoice_checkpoints(actor, content.id, include_inactive=True)
    st.dataframe([{"Checkpoint": c.checkpoint_name, "Invoice Date": format_date(c.invoice_date), "Due Date": format_date(c.due_date), "Status": safe_text(c.status), "Amount": safe_text(c.amount), "Active State": "Active" if c.is_active else "Inactive"} for c in checkpoints], hide_index=True, use_container_width=True)
    for checkpoint in checkpoints:
        cols = st.columns(4)
        if cols[0].button("Sent", key=f"campaign_ops_content_invoice_sent_{checkpoint.id}"):
            service.mark_content_invoice_sent(actor, content.id, checkpoint.id); st.rerun()
        if cols[1].button("Paid", key=f"campaign_ops_content_invoice_paid_{checkpoint.id}"):
            service.mark_content_invoice_paid(actor, content.id, checkpoint.id); st.rerun()
        if checkpoint.is_active and cols[2].button("Deactivate", key=f"campaign_ops_content_invoice_deactivate_{checkpoint.id}"):
            service.deactivate_content_invoice_checkpoint(actor, content.id, checkpoint.id); st.rerun()
        if not checkpoint.is_active and cols[3].button("Reactivate", key=f"campaign_ops_content_invoice_reactivate_{checkpoint.id}"):
            service.reactivate_content_invoice_checkpoint(actor, content.id, checkpoint.id); st.rerun()


def render_timeline(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    with st.form(f"campaign_ops_content_timeline_add_{content.id}"):
        cols = st.columns(4)
        title = cols[0].text_input("Timeline Item")
        target = cols[1].date_input("Exact Date", value=None)
        start = cols[2].date_input("Start Date", value=None)
        end = cols[3].date_input("End Date", value=None)
        submitted = st.form_submit_button("Add Timeline Item", type="primary")
    if submitted:
        service.create_milestone(actor, content.program_id, title, workstream_id=content.workstream_id, milestone_type="Content Management", target_date=target, start_date=start, end_date=end)
        st.rerun()
    milestones = [m for m in service.list_program_milestones(actor, content.program_id, include_inactive=True) if m.workstream_id == content.workstream_id or m.milestone_type == "Content Management"]
    st.dataframe([{"Date": format_date(m.target_date or m.start_date), "End": format_date(m.end_date), "Item": m.title, "Status": title_label(m.status), "Active State": "Active" if m.is_active else "Inactive"} for m in milestones], hide_index=True, use_container_width=True)
    for m in milestones:
        cols = st.columns(4)
        if m.status != TaskStatus.COMPLETED.value and cols[0].button("Complete", key=f"campaign_ops_content_milestone_complete_{m.id}"):
            service.complete_milestone(actor, m.id); st.rerun()
        if m.status == TaskStatus.COMPLETED.value and cols[1].button("Reopen", key=f"campaign_ops_content_milestone_reopen_{m.id}"):
            service.reopen_milestone(actor, m.id); st.rerun()
        if m.is_active and cols[2].button("Deactivate", key=f"campaign_ops_content_milestone_deactivate_{m.id}"):
            service.deactivate_milestone(actor, m.id); st.rerun()
        if not m.is_active and cols[3].button("Reactivate", key=f"campaign_ops_content_milestone_reactivate_{m.id}"):
            service.reactivate_milestone(actor, m.id); st.rerun()


def render_resources(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    cols = st.columns(5)
    for idx, (label, url) in enumerate((("SKU List", content.sku_list_url), ("Tracksheet", content.tracksheet_url), ("Creative Request Deck", content.creative_request_deck_url), ("Keyword Insights", content.keyword_insights_url), ("Photography", content.photography_url))):
        if url:
            cols[idx].link_button(label, sanitize_link(url), key=f"campaign_ops_content_quick_{label}_{content.id}")
        else:
            cols[idx].metric(label, "Missing")
    summary = service.get_program_workspace_summary(actor, content.program_id)
    resources = [r for r in service.list_program_resources(actor, content.program_id, include_inactive=True) if r.resource_type in CONTENT_RESOURCE_TYPES or r.workstream_id == content.workstream_id]
    st.dataframe(resource_table_rows(resources), hide_index=True, use_container_width=True)
    with st.form(f"campaign_ops_content_resource_add_{content.id}"):
        cols = st.columns(3)
        title = cols[0].text_input("Title")
        resource_type = cols[1].selectbox("Resource type", CONTENT_RESOURCE_TYPES)
        url = cols[2].text_input("URL")
        submitted = st.form_submit_button("Add Resource", type="primary")
    if submitted:
        service.create_resource(actor, content.program_id, title=title, resource_type=resource_type, workstream_id=content.workstream_id, url=trim_or_none(url))
        st.rerun()
    for resource in resources:
        render_resource_actions(actor, service, summary, resource)


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    summary = service.get_program_workspace_summary(actor, content.program_id)
    rows = [{"Timestamp": format_datetime(e.created_at), "Event": title_label(e.event_type), "Message": safe_text(e.message)} for e in summary.activity if e.event_type.startswith("content_") or e.entity_type.startswith("content_")]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
