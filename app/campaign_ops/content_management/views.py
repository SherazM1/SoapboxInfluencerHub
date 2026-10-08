from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any

import streamlit as st

from app.campaign_ops.operational_editor import collect_rows, editor_styles, render_rows
from app.campaign_ops.content_management.baseline import action_display_text, next_current_action, normalize_content_actions
from app.campaign_ops.content_management.formatting import content_status_label
from app.campaign_ops.formatting import RISK_LABELS, STATUS_LABELS, format_date, format_datetime, safe_text, title_label
from app.campaign_ops.note_views import render_notes
from app.campaign_ops.program_router import open_program
from app.campaign_ops.state import begin_new_program, set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.content_management import CONTENT_STATUSES, CONTENT_STATUS_NOT_STARTED
from core.campaign_ops.enums import TaskStatus, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsPermissionError
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import can_access_admin, require_program_access
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.content_management_timeline import (
    ContentManagementTimelineService,
    sort_content_management_timeline_rows,
)
from core.campaign_ops.service import CampaignOpsService

SELECTED_WORKSPACE = "campaign_ops_selected_content_program_id"

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
    del users
    st.subheader("Content Management / eCommerce")
    if st.session_state.pop("campaign_ops_content_management_denied", False):
        st.warning("You do not have access to this program.")
    workspace_id = st.session_state.get(SELECTED_WORKSPACE)
    if workspace_id:
        render_operational_editor(actor, service, str(workspace_id))
        return

    if can_access_admin(actor):
        st.button(
            "New Content Program",
            type="primary",
            key="campaign_ops_content_new_operational_program",
            on_click=begin_new_program,
            args=(st.session_state, WorkstreamType.ECOMMERCE.value),
        )
    try:
        programs = [
            row for row in ProgramRoutingService(service.repository).list_registry(actor)
            if row.primary_workstream_type == WorkstreamType.ECOMMERCE.value
        ]
    except CampaignOpsError as exc:
        st.error(f"Unable to load Content Management programs: {exc}")
        return

    columns = st.columns([2, 3, 2, 2, 1])
    for column, label in zip(columns, ("Client", "Program", "Lead Owner", "Manager", "Open")):
        column.markdown(f"**{label}**")
    if not programs:
        st.info("No active Content Management / eCommerce programs are available.")
    for program in programs:
        columns = st.columns([2, 3, 2, 2, 1])
        columns[0].write(safe_text(program.client_name))
        columns[1].write(program.program_name)
        columns[2].write(safe_text(program.primary_owner_name))
        columns[3].write(safe_text(program.manager_name))
        columns[4].button(
            "Open",
            key=f"campaign_ops_content_management_open_{program.id}",
            on_click=open_program,
            args=(st.session_state, actor, service, program.id),
        )


def _back_to_content_programs():
    st.session_state.pop(SELECTED_WORKSPACE, None)
    for key in list(st.session_state):
        if key.startswith("campaign_ops_content_management_draft_"):
            st.session_state.pop(key, None)


@st.fragment
def render_operational_editor(actor, service, workspace_id: str) -> None:
    draft_key = f"campaign_ops_content_management_draft_{actor.id}_{workspace_id}"
    version_key = f"content_management_editor_version_{actor.id}_{workspace_id}"
    repository = service.repository or CampaignOpsRepository()
    try:
        workspace = repository.get_content_management_program(workspace_id)
        if workspace is None or not workspace.is_active:
            raise CampaignOpsError("Content Management workspace is unavailable.")
        program = require_program_access(repository, actor, workspace.program_id, active_only=True)
        if program.primary_workstream_type != WorkstreamType.ECOMMERCE.value:
            raise CampaignOpsError("The selected Program is not a Content Management / eCommerce Program.")
        timeline = ContentManagementTimelineService(service.repository)
        snapshot = st.session_state.get(draft_key)
        if snapshot is None:
            workspace, rows = timeline.initialize_program(actor, program.id)
            ownership = timeline.assignment_state(actor, program.id)
            snapshot = {
                "rows": deepcopy(rows),
                "ownership": ownership,
                "editor_owner": ownership["lead_id"],
                "editor_manager": ownership["manager_id"],
                "lead_names": {
                    user.id: user.display_name
                    for user in timeline.list_workflow_role_users("ecommerce", "lead_owner")
                },
                "manager_names": {
                    user.id: user.display_name
                    for user in timeline.list_workflow_role_users("ecommerce", "manager")
                },
                "editor_records": [
                    {"_row_id": row.id, "_draft_id": row.id, "Date": row.due_date,
                     "Action": row.action, "Done": bool(row.done),
                     "Program Notes": row.program_notes or ""}
                    for row in sort_content_management_timeline_rows(rows)
                ],
            }
            st.session_state[draft_key] = snapshot
    except CampaignOpsPermissionError:
        _back_to_content_programs()
        st.session_state["campaign_ops_content_management_denied"] = True
        st.rerun()
    except CampaignOpsError as exc:
        _back_to_content_programs()
        st.error(str(exc))
        return

    editor_styles()
    with st.container(key="ops_editor"):
        st.markdown(f"### {program.program_name}")
        message = st.session_state.pop(draft_key + "_message", None)
        if message:
            (st.error if message[0] else st.success)(message[1])
        prefix = f"content_management_rows_{actor.id}_{program.id}_{st.session_state.get(version_key, 0)}"
        for label, options, field, suffix in (
            ("Lead Owner", snapshot["lead_names"], "editor_owner", "lead"),
            ("Manager", snapshot["manager_names"], "editor_manager", "manager"),
        ):
            snapshot[field] = st.selectbox(
                label,
                list(options),
                format_func=options.get,
                index=list(options).index(snapshot[field]) if snapshot[field] in options else None,
                placeholder=f"Choose a {label}",
                key=f"{prefix}_{suffix}",
                disabled=not can_access_admin(actor),
            )
        st.markdown("#### Timeline")
        render_rows(snapshot, prefix)
        st.button(
            "Save Changes",
            type="primary",
            key=f"content_management_save_{workspace_id}",
            on_click=_save_content_management_changes,
            args=(actor, timeline, program.id, draft_key, version_key, prefix),
        )
        st.caption("Edits stay unsaved until Save Changes. Save before leaving.")
        st.button("Back to programs", key=f"content_management_back_{workspace_id}",
                  on_click=_back_to_content_programs)


def _save_content_management_changes(actor, service, program_id, draft_key, version_key, prefix):
    snapshot = st.session_state[draft_key]
    records = deepcopy(collect_rows(snapshot, prefix))
    lead_id = st.session_state.get(f"{prefix}_lead")
    manager_id = st.session_state.get(f"{prefix}_manager")
    try:
        changes = service.save_changes(
            actor, program_id, records, snapshot["rows"], snapshot["ownership"], lead_id, manager_id
        )
    except (CampaignOpsError, ValueError) as exc:
        st.session_state[draft_key + "_message"] = (True, f"{exc} Nothing saved.")
    else:
        st.session_state.pop(draft_key, None)
        st.session_state[version_key] = st.session_state.get(version_key, 0) + 1
        st.session_state[draft_key + "_message"] = (
            False, "Changes saved." if any(changes.values()) else "No changes to save."
        )


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


def render_program_scan_card(program: Any, board_data: dict[str, Any]) -> None:
    groups = board_data.get("groups", {}).get(program.id, [])
    actions = normalize_content_actions(
        groups=groups,
        deliverables=board_data.get("deliverables", {}).get(program.id, []),
        submissions=board_data.get("submissions", {}).get(program.id, []),
        monitoring_updates=board_data.get("monitoring", {}).get(program.id, []),
        milestones=board_data.get("milestones", {}).get(program.id, []),
    )
    next_action = next_current_action(actions, program.next_milestone, program.next_milestone_date)
    meta = f"{safe_text(program.owner_display_name)} | {content_status_label(program.content_status)} | {'Active' if program.is_active else 'Inactive'}"
    html = [
        "<div class='campaign-ops-content-card'>",
        f"<div class='campaign-ops-content-card-head'>{escape(program.content_program_title)}<div class='campaign-ops-content-card-meta'>{escape(meta)}</div></div>",
        "<div class='campaign-ops-content-card-grid'>",
        _card_cell("Latest Update", escape(safe_text(program.latest_update)) if program.latest_update else "-"),
        _card_cell("Waiting On", escape(safe_text(program.waiting_on)) if program.waiting_on else "-"),
        _card_cell("Monitoring / Maintenance", escape(f"{format_date(program.monitoring_start_date)} / {format_date(program.maintenance_end_date)}")),
        _card_cell("Issues", f"{program.issue_count}" + (f"<br>Delivered {program.delivered_count} | Live {program.live_count}" if program.delivered_count or program.live_count else "")),
        "</div>",
    ]
    if next_action:
        html.append(f"<div class='campaign-ops-content-row'><strong>Next / Current Action</strong><br>{escape(action_display_text(next_action))} | {escape(next_action.status)}</div>")
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    if st.button("Open Content Program", key=f"campaign_ops_content_scan_open_{program.id}"):
        st.session_state["campaign_ops_selected_content_program_id"] = program.id
        st.rerun()


def _card_cell(label: str, value: str) -> str:
    return f"<div class='campaign-ops-content-card-cell'><div class='campaign-ops-content-card-label'>{escape(label)}</div><div class='campaign-ops-content-card-value'>{value}</div></div>"


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
        cols = st.columns(2)
        monitoring_start = cols[0].date_input("Monitoring Start Date", value=None)
        maintenance_end = cols[1].date_input("Maintenance End Date", value=None)
        cols = st.columns(3)
        cadence = cols[0].text_input("Reporting Cadence")
        invoiced = cols[1].checkbox("Invoiced")
        invoice_status = cols[2].text_input("Invoice Status")
        submitted = st.form_submit_button("Create Content Program", type="primary")
    if not submitted:
        return
    try:
        content = service.create_content_program(actor, program_id=program_options[program_label], content_program_title=title, owner_user_id=user_options[owner], content_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), monitoring_start_date=monitoring_start, maintenance_end_date=maintenance_end, reporting_cadence=trim_or_none(cadence), is_invoiced=invoiced, invoice_status=trim_or_none(invoice_status))
    except CampaignOpsError as exc:
        st.error(f"Content Program was not created: {exc}")
        return
    st.session_state["campaign_ops_content_create_open"] = False
    st.session_state["campaign_ops_selected_content_program_id"] = content.id
    st.rerun()


def render_workspace(actor: CampaignOpsUser, service: CampaignOpsService, users: list[CampaignOpsUser], content_program_id: str) -> None:
    try:
        content = service.get_content_program_detail(actor, content_program_id)
    except CampaignOpsPermissionError:
        st.session_state.pop("campaign_ops_selected_content_program_id", None)
        st.warning("You do not have access to this program.")
        render_portfolio(actor, service)
        return
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
    st.caption(f"Client: {safe_text(content.client_name)} | Shared Program: {content.program_name} | Owner: {safe_text(content.owner_display_name)} | Status: {content_status_label(content.content_status)} | Issues: {content.issue_count} | Waiting On: {safe_text(content.waiting_on)} | Maintenance End: {format_date(content.maintenance_end_date)} | Risk: {RISK_LABELS.get(content.program_risk, content.program_risk)} | Latest: {safe_text(content.latest_update)} | Next: {safe_text(content.next_milestone)} | Updated: {format_datetime(content.updated_at)} | {'Active' if content.is_active else 'Inactive'}")
    tabs = st.tabs(['Overview', 'Deliverables', 'Submission & Publication', 'Invoicing', 'Timeline', 'Notes', 'Activity'])
    with tabs[0]:
        render_overview(actor, service, users, content)
    with tabs[1]:
        render_deliverables(actor, service, content)
    with tabs[2]:
        render_submissions(actor, service, content)
    with tabs[3]:
        render_invoices(actor, service, content)
    with tabs[4]:
        render_timeline(actor, service, content)
    with tabs[5]:
        with st.expander("Notes", expanded=False):
            render_notes(actor, service, service.get_program_workspace_summary(actor, content.program_id))
    with tabs[6]:
        with st.expander("Activity", expanded=False):
            render_activity(actor, service, content)


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
        cols = st.columns(2)
        monitoring = cols[0].date_input("Monitoring Start Date", value=content.monitoring_start_date)
        maintenance = cols[1].date_input("Maintenance End Date", value=content.maintenance_end_date)
        cols = st.columns(2)
        invoiced = cols[0].checkbox("Invoiced", value=content.is_invoiced)
        invoice_status = cols[1].text_input("Invoice Status", value=content.invoice_status or "")
        submitted = st.form_submit_button("Save Overview", type="primary")
    st.caption(f"Program: {content.program_name} | Client: {safe_text(content.client_name)} | Workstream: {safe_text(content.workstream_id)} | Program status: {STATUS_LABELS.get(content.program_status, content.program_status)}")
    if submitted:
        service.update_content_program(actor, content.id, content_program_title=title, owner_user_id=user_options[owner], content_status=status, latest_update=trim_or_none(latest), waiting_on=trim_or_none(waiting), reporting_cadence=trim_or_none(cadence), monitoring_start_date=monitoring, maintenance_end_date=maintenance, is_invoiced=invoiced, invoice_status=trim_or_none(invoice_status))
        st.rerun()
    cols = st.columns(2)
    if content.is_active and cols[0].button("Deactivate Content Program", key=f"campaign_ops_content_deactivate_{content.id}"):
        service.deactivate_content_program(actor, content.id)
        st.rerun()
    if not content.is_active and cols[1].button("Reactivate Content Program", key=f"campaign_ops_content_reactivate_{content.id}"):
        service.reactivate_content_program(actor, content.id)
        st.rerun()


def group_options(groups: list[Any]) -> dict[str, str | None]:
    return {"Program-level": None, **{g.group_name: g.id for g in groups if g.is_active}}


def sku_options(skus: list[Any]) -> dict[str, str | None]:
    return {"No SKU": None, **{s.product_name: s.id for s in skus if s.is_active}}


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


def render_activity(actor: CampaignOpsUser, service: CampaignOpsService, content: Any) -> None:
    summary = service.get_program_workspace_summary(actor, content.program_id)
    rows = [{"Timestamp": format_datetime(e.created_at), "Event": title_label(e.event_type), "Message": safe_text(e.message)} for e in summary.activity if e.event_type.startswith("content_") or e.entity_type.startswith("content_")]
    st.dataframe(rows, hide_index=True, use_container_width=True)
