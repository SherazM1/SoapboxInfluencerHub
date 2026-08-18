from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.formatting import RISK_LABELS, WORKFLOW_LABELS, format_date, format_datetime, safe_text
from app.campaign_ops.reporting_requests.formatting import (
    ALL_REQUEST_COLUMNS,
    REPORTING_COLUMNS,
    SURVEY_COLUMNS,
    all_request_rows,
    attention_label,
    next_gate_label,
    program_context_label,
    reporting_request_rows,
    status_label,
    survey_request_rows,
)
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import RiskLevel, WaitingOn
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, ProgramPortfolioRow, ReportingRequestListRow
from core.campaign_ops.reporting_requests import (
    REQUEST_CATEGORY_REPORT,
    REQUEST_CATEGORY_SURVEY,
    REQUEST_STATUS_REQUESTED,
    REQUEST_STATUSES,
)
from core.campaign_ops.service import CampaignOpsService

REQUEST_VIEW_OPTIONS = ["Survey Requests", "Reporting Requests", "All Requests", "New Request"]
SORT_OPTIONS = {
    "Due date": "due_date",
    "Program": "program_name",
    "AM": "am_display_name",
    "Type": "request_type",
    "Status": "status",
    "Updated date": "updated_at",
}


def render_reporting_requests(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
) -> None:
    st.subheader("Requests")
    render_workbook_css()
    view = st.radio(
        "Request view",
        REQUEST_VIEW_OPTIONS,
        horizontal=True,
        key="campaign_ops_requests_view",
    )
    include_inactive = st.checkbox("Show inactive requests", key="campaign_ops_request_show_inactive")
    try:
        requests = service.list_reporting_requests(actor, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load requests: {exc}")
        return

    selected_id = st.session_state.get("campaign_ops_selected_request_id")
    if selected_id and not any(request.id == selected_id for request in requests):
        st.session_state.pop("campaign_ops_selected_request_id", None)

    if view == "New Request":
        render_request_form(actor, service, users, None)
        return

    category = REQUEST_CATEGORY_SURVEY if view == "Survey Requests" else REQUEST_CATEGORY_REPORT if view == "Reporting Requests" else ""
    filters = render_filters(requests, category)
    filtered = sort_requests(filter_requests(requests, filters, category), str(filters.get("sort_by") or "due_date"))
    if view == "Survey Requests":
        render_section_table("Survey Requests", survey_request_rows(filtered), SURVEY_COLUMNS)
    elif view == "Reporting Requests":
        render_section_table("Reporting Requests", reporting_request_rows(filtered), REPORTING_COLUMNS)
    else:
        render_section_table("All Requests", all_request_rows(filtered), ALL_REQUEST_COLUMNS)
    render_request_selector(filtered)
    selected = next((request for request in filtered if request.id == st.session_state.get("campaign_ops_selected_request_id")), None)
    if selected:
        st.divider()
        render_request_detail(actor, service, users, selected.id)


def render_workbook_css() -> None:
    st.markdown(
        """
        <style>
        .campaign-ops-sheet-title {
            background: #3aa6a6;
            color: #102222;
            text-align: center;
            font-weight: 700;
            padding: 0.35rem;
            border: 1px solid #6fbfbf;
        }
        div[data-testid="stDataFrame"] {
            background: white;
            border: 1px solid #d8dee4;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_section_table(title: str, rows: list[dict[str, str]], columns: list[str]) -> None:
    st.markdown(f"<div class='campaign-ops-sheet-title'>{title}</div>", unsafe_allow_html=True)
    ordered_rows = [{column: row.get(column, "") for column in columns} for row in rows]
    if ordered_rows:
        column_config = {
            "Questions / Notes": st.column_config.TextColumn("Questions / Notes", width="medium"),
            "Special Requests": st.column_config.TextColumn("Special Requests", width="medium"),
        }
        st.dataframe(ordered_rows, hide_index=True, use_container_width=True, column_config=column_config)
    else:
        empty_messages = {
            "Survey Requests": "No survey requests match these filters.",
            "Reporting Requests": "No reporting requests match these filters.",
            "All Requests": "No requests match these filters.",
        }
        st.info(empty_messages.get(title, f"No {title.lower()} match this view."))


def render_filters(requests: list[ReportingRequestListRow], category: str) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_request_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Request filters", expanded=True):
        cols = st.columns(4)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_request_filter_search")
        am_options = {"Any": "", **{request.am_display_name: request.am_user_id for request in requests}}
        current["am_user_id"] = am_options[cols[1].selectbox("AM", list(am_options), key="campaign_ops_request_filter_am")]
        program_options = {"Any": "", **{request.program_name: request.program_id for request in requests}}
        current["program_id"] = program_options[cols[2].selectbox("Program", list(program_options), key="campaign_ops_request_filter_program")]
        current["sort_by"] = SORT_OPTIONS[cols[3].selectbox("Sort", list(SORT_OPTIONS), key="campaign_ops_request_filter_sort")]
        cols = st.columns(4)
        current["delivered"] = cols[0].selectbox("Delivered", ["Any", "Yes", "No"], key="campaign_ops_request_filter_delivered")
        state_label = "Review" if category == REQUEST_CATEGORY_SURVEY else "Approval" if category == REQUEST_CATEGORY_REPORT else "Review / Approval"
        current["state"] = cols[1].selectbox(state_label, ["Any", "Required", "Complete"], key="campaign_ops_request_filter_state")
        current["status"] = cols[2].selectbox("Status", ["Any", *sorted(REQUEST_STATUSES)], key="campaign_ops_request_filter_status")
        current["risk"] = cols[3].selectbox("Risk", ["Any", *RISK_LABELS], key="campaign_ops_request_filter_risk")
        cols = st.columns(2)
        current["due_from"] = cols[0].date_input("Due from", value=current.get("due_from"), key="campaign_ops_request_filter_due_from")
        current["due_to"] = cols[1].date_input("Due to", value=current.get("due_to"), key="campaign_ops_request_filter_due_to")
        cols = st.columns(2)
        if cols[0].button("Refresh", key="campaign_ops_request_refresh"):
            st.rerun()
        if cols[1].button("Clear filters", key="campaign_ops_request_clear_filters"):
            st.session_state["campaign_ops_request_filters"] = {}
            st.rerun()
    st.session_state["campaign_ops_request_filters"] = current
    return current


def filter_requests(requests: list[ReportingRequestListRow], filters: dict[str, object], category: str) -> list[ReportingRequestListRow]:
    result = [request for request in requests if not category or request.request_category == category]
    search = str(filters.get("search") or "").strip().lower()
    if search:
        result = [
            request for request in result
            if search in request.request_type.lower()
            or search in request.program_name.lower()
            or search in (request.client_name or "").lower()
        ]
    for field in ("am_user_id", "program_id", "status", "risk"):
        value = filters.get(field)
        if value and value != "Any":
            result = [request for request in result if getattr(request, field) == value]
    if filters.get("delivered") == "Yes":
        result = [request for request in result if request.delivered]
    if filters.get("delivered") == "No":
        result = [request for request in result if not request.delivered]
    if filters.get("state") == "Required":
        result = [request for request in result if (request.review_required and not request.review_complete) or (request.approval_required and not request.approved)]
    if filters.get("state") == "Complete":
        result = [request for request in result if request.review_complete or request.approved]
    due_from = filters.get("due_from")
    due_to = filters.get("due_to")
    if isinstance(due_from, date):
        result = [request for request in result if request.due_date and request.due_date >= due_from]
    if isinstance(due_to, date):
        result = [request for request in result if request.due_date and request.due_date <= due_to]
    return result


def sort_requests(requests: list[ReportingRequestListRow], sort_by: str) -> list[ReportingRequestListRow]:
    return sorted(
        requests,
        key=lambda request: (
            getattr(request, sort_by, None) is None,
            str(getattr(request, sort_by, "") or ""),
            request.request_type.lower(),
        ),
    )


def render_request_selector(requests: list[ReportingRequestListRow]) -> None:
    if not requests:
        return
    labels = {f"{request.request_type} | {request.program_name} | {request.am_display_name}": request.id for request in requests}
    cols = st.columns(2)
    selected = cols[0].selectbox("Select request", list(labels), key="campaign_ops_request_select")
    if cols[1].button("Open Request", key="campaign_ops_request_open_selected"):
        st.session_state["campaign_ops_selected_request_id"] = labels[selected]
        st.rerun()


def render_request_detail(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
    request_id: str,
) -> None:
    try:
        request = service.get_reporting_request_detail(actor, request_id)
    except CampaignOpsError as exc:
        st.session_state.pop("campaign_ops_selected_request_id", None)
        st.error(f"Request is not available: {exc}")
        return
    st.markdown(f"### {request.request_type}")
    st.caption(program_context_label(request))
    render_deadline_summary(request)
    cols = st.columns(4)
    if cols[0].button("Open Program", key=f"campaign_ops_request_open_program_{request.id}"):
        set_selected_program(st.session_state, request.program_id)
        st.rerun()
    cols[1].button("Open Tasks", key=f"campaign_ops_request_open_tasks_{request.id}", disabled=True)
    cols[2].button("Open Resources", key=f"campaign_ops_request_open_resources_{request.id}", disabled=True)
    cols[3].button("Open Notes", key=f"campaign_ops_request_open_notes_{request.id}", disabled=True)
    render_request_form(actor, service, users, request)


def render_deadline_summary(request: ReportingRequestListRow) -> None:
    rows = [
        {
            "Due Date": format_date(request.due_date),
            "Status": status_label(request.status),
            "Next Gate": next_gate_label(request),
            "Attention": attention_label(request),
        }
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)


def render_request_form(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
    request: ReportingRequestListRow | None,
) -> None:
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    program_options = {program.program_name: program.id for program in programs}
    if request and request.program_name not in program_options:
        program_options = {request.program_name: request.program_id, **program_options}
    if not program_options:
        st.warning("No accessible programs are available for requests.")
        return
    user_options = {"Unassigned": None, **{user.display_name: user.id for user in users if user.is_active}}
    am_options = {user.display_name: user.display_name for user in users if user.display_name in {"Bailey", "T", "L"} and user.is_active}
    current_program = request.program_name if request else next(iter(program_options))
    current_am = request.am_display_name if request else next(iter(am_options), "Bailey")
    current_assigned = next((name for name, user_id in user_options.items() if request and user_id == request.assigned_user_id), "Unassigned")
    with st.form(f"campaign_ops_request_form_{request.id if request else 'new'}"):
        cols = st.columns(4)
        category_label_selected = cols[0].selectbox(
            "Request category",
            ["Survey Request", "Reporting Request"],
            index=0 if (not request or request.request_category == REQUEST_CATEGORY_SURVEY) else 1,
        )
        request_category = REQUEST_CATEGORY_SURVEY if category_label_selected == "Survey Request" else REQUEST_CATEGORY_REPORT
        request_type = cols[1].text_input("Request type", value=request.request_type if request else ("EOP Survey" if request_category == REQUEST_CATEGORY_SURVEY else "Program Recap"))
        program_label = cols[2].selectbox("Program", list(program_options), index=list(program_options).index(current_program))
        am_label = cols[3].selectbox("AM", list(am_options), index=list(am_options).index(current_am) if current_am in am_options else 0)
        cols = st.columns(4)
        assigned_label = cols[0].selectbox("Assigned reporting owner", list(user_options), index=list(user_options).index(current_assigned))
        due_date = cols[1].date_input("Due date", value=request.due_date if request else None)
        status = cols[2].selectbox("Status", sorted(REQUEST_STATUSES), index=sorted(REQUEST_STATUSES).index(request.status if request else REQUEST_STATUS_REQUESTED), format_func=lambda value: value.replace("_", " ").title())
        risk = cols[3].selectbox("Risk", list(RISK_LABELS), index=list(RISK_LABELS).index(request.risk if request else RiskLevel.UNRATED.value), format_func=lambda value: RISK_LABELS[value])
        waiting_on = st.selectbox(
            "Waiting on",
            ["None", *[item.value for item in WaitingOn]],
            index=(["None", *[item.value for item in WaitingOn]].index(request.waiting_on) if request and request.waiting_on in [item.value for item in WaitingOn] else 0),
            format_func=lambda value: value.replace("_", " ").title(),
        )
        brief_url = None
        brief_status_text = None
        recap_date_with_client = None
        recap_date_text = None
        review_required = False
        review_complete = False
        approval_required = False
        approved = False
        if request_category == REQUEST_CATEGORY_SURVEY:
            cols = st.columns(4)
            brief_url = cols[0].text_input("Link to Brief", value=request.brief_url or "" if request else "")
            brief_status_text = cols[1].text_input("Brief status text", value=request.brief_status_text or "" if request else "")
            delivered = cols[2].checkbox("Delivered", value=request.delivered if request else False)
            review_required = cols[3].checkbox("Review required", value=request.review_required if request else False)
            review_complete = st.checkbox("Review complete", value=request.review_complete if request else False)
        else:
            cols = st.columns(4)
            recap_date_with_client = cols[0].date_input("Recap Date with Client", value=request.recap_date_with_client if request else None)
            recap_date_text = cols[1].text_input("Recap Date text", value=request.recap_date_text or "" if request else "")
            delivered = cols[2].checkbox("Delivered", value=request.delivered if request else False)
            approval_required = cols[3].checkbox("Approval required", value=request.approval_required if request else False)
            approved = st.checkbox("Approved", value=request.approved if request else False)
        render_detail_text_blocks(request)
        questions_requested = st.text_area("Questions You'd Like Included", value=request.questions_requested or "" if request else "", height=140, key=f"campaign_ops_request_questions_input_{request.id if request else 'new'}")
        special_requests = st.text_area("Special Requests", value=request.special_requests or "" if request else "", height=140, key=f"campaign_ops_request_special_input_{request.id if request else 'new'}")
        submitted = st.form_submit_button("Save Request" if request else "Create Request", type="primary")
    if not submitted:
        if request:
            st.caption(
                f"Created: {format_datetime(request.created_at)} | Updated: {format_datetime(request.updated_at)} | "
                f"Completed: {format_datetime(request.completed_at)} | State: {'Active' if request.is_active else 'Inactive'}"
            )
            render_request_state_actions(actor, service, request)
        return
    payload = {
        "request_category": request_category,
        "request_type": request_type,
        "program_id": program_options[program_label],
        "am_name": am_label,
        "assigned_user_id": user_options[assigned_label],
        "due_date": due_date,
        "status": status,
        "risk": risk,
        "waiting_on": None if waiting_on == "None" else waiting_on,
        "brief_url": trim_or_none(brief_url),
        "brief_status_text": trim_or_none(brief_status_text),
        "recap_date_with_client": recap_date_with_client,
        "recap_date_text": trim_or_none(recap_date_text),
        "delivered": delivered,
        "review_required": review_required,
        "review_complete": review_complete,
        "approval_required": approval_required,
        "approved": approved,
        "questions_requested": trim_or_none(questions_requested),
        "special_requests": trim_or_none(special_requests),
    }
    try:
        if request:
            service.update_reporting_request(actor, request.id, **payload)
            st.success("Request updated.")
        else:
            created = service.create_reporting_request(actor, **payload)
            st.session_state["campaign_ops_selected_request_id"] = created.id
            st.success("Request created.")
    except CampaignOpsError as exc:
        st.error(f"Request was not saved: {exc}")
        return
    st.rerun()


def render_detail_text_blocks(request: ReportingRequestListRow | None) -> None:
    for title, value in (
        ("Questions You'd Like Included", request.questions_requested if request else None),
        ("Special Requests", request.special_requests if request else None),
    ):
        st.markdown(f"<div class='campaign-ops-sheet-title'>{title}</div>", unsafe_allow_html=True)
        st.caption(safe_text(value).replace("\n", " / ") if value else "Blank")


def render_request_state_actions(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    request: ReportingRequestListRow,
) -> None:
    cols = st.columns(3)
    if request.brief_url:
        cols[0].link_button("Open brief", sanitize_link(request.brief_url), key=f"campaign_ops_request_open_brief_{request.id}")
    if request.is_active and cols[1].button("Deactivate Request", key=f"campaign_ops_request_deactivate_{request.id}"):
        try:
            service.deactivate_reporting_request(actor, request.id)
        except CampaignOpsError as exc:
            st.error(f"Request was not deactivated: {exc}")
            return
        st.success("Request deactivated.")
        st.rerun()
    if not request.is_active and cols[2].button("Reactivate Request", key=f"campaign_ops_request_reactivate_{request.id}"):
        try:
            service.reactivate_reporting_request(actor, request.id)
        except CampaignOpsError as exc:
            st.error(f"Request was not reactivated: {exc}")
            return
        st.success("Request reactivated.")
        st.rerun()


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
