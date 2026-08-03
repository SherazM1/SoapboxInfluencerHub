from __future__ import annotations

from app.campaign_ops.formatting import RISK_LABELS, WORKFLOW_LABELS, format_date, format_datetime, safe_text, title_label
from core.campaign_ops.models import ReportingRequestListRow
from core.campaign_ops.reporting_requests import REQUEST_CATEGORY_REPORT, REQUEST_CATEGORY_SURVEY

SURVEY_COLUMNS = [
    "Type of Survey",
    "AM",
    "Program",
    "Due Date",
    "Link to Brief",
    "Delivered",
    "Reviews?",
]

REPORTING_COLUMNS = [
    "Type of Report",
    "AM",
    "Program",
    "Due Date",
    "Recap Date with Client",
    "Delivered",
    "Approval",
]

ALL_REQUEST_COLUMNS = [
    "Request category",
    "Request type",
    "AM",
    "Program",
    "Client",
    "Due date",
    "Recap date",
    "Status",
    "Delivered",
    "Review",
    "Approval",
    "Risk",
    "Waiting on",
    "Updated date",
    "Active state",
]


def category_label(value: str) -> str:
    if value == REQUEST_CATEGORY_SURVEY:
        return "Survey Request"
    if value == REQUEST_CATEGORY_REPORT:
        return "Reporting Request"
    return title_label(value)


def status_label(value: str) -> str:
    return title_label(value)


def boolean_cell(value: bool) -> str:
    return "[x]" if value else "[ ]"


def review_label(request: ReportingRequestListRow) -> str:
    if not request.review_required:
        return "-"
    return "Complete" if request.review_complete else "Required"


def approval_label(request: ReportingRequestListRow) -> str:
    if not request.approval_required:
        return "-"
    return "Approved" if request.approved else "Required"


def brief_label(request: ReportingRequestListRow) -> str:
    if request.brief_url:
        return "Open brief"
    return safe_text(request.brief_status_text)


def recap_label(request: ReportingRequestListRow) -> str:
    return format_date(request.recap_date_with_client) if request.recap_date_with_client else safe_text(request.recap_date_text)


def survey_request_rows(requests: list[ReportingRequestListRow]) -> list[dict[str, str]]:
    return [
        {
            "Type of Survey": request.request_type,
            "AM": request.am_display_name,
            "Program": request.program_name,
            "Due Date": format_date(request.due_date),
            "Link to Brief": brief_label(request),
            "Delivered": boolean_cell(request.delivered),
            "Reviews?": review_label(request),
        }
        for request in requests
        if request.request_category == REQUEST_CATEGORY_SURVEY
    ]


def reporting_request_rows(requests: list[ReportingRequestListRow]) -> list[dict[str, str]]:
    return [
        {
            "Type of Report": request.request_type,
            "AM": request.am_display_name,
            "Program": request.program_name,
            "Due Date": format_date(request.due_date),
            "Recap Date with Client": recap_label(request),
            "Delivered": boolean_cell(request.delivered),
            "Approval": approval_label(request),
        }
        for request in requests
        if request.request_category == REQUEST_CATEGORY_REPORT
    ]


def all_request_rows(requests: list[ReportingRequestListRow]) -> list[dict[str, str]]:
    return [
        {
            "Request category": category_label(request.request_category),
            "Request type": request.request_type,
            "AM": request.am_display_name,
            "Program": request.program_name,
            "Client": safe_text(request.client_name),
            "Due date": format_date(request.due_date),
            "Recap date": recap_label(request),
            "Status": status_label(request.status),
            "Delivered": boolean_cell(request.delivered),
            "Review": review_label(request),
            "Approval": approval_label(request),
            "Risk": RISK_LABELS.get(request.risk, title_label(request.risk)),
            "Waiting on": title_label(request.waiting_on),
            "Updated date": format_datetime(request.updated_at),
            "Active state": "Active" if request.is_active else "Inactive",
        }
        for request in requests
    ]


def program_context_label(request: ReportingRequestListRow) -> str:
    return (
        f"{request.program_name} | Client: {safe_text(request.client_name)} | "
        f"Primary workflow: {WORKFLOW_LABELS.get(request.primary_workstream_type or '', '-')}"
    )
