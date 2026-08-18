from __future__ import annotations

from datetime import date, timedelta

from app.campaign_ops.formatting import RISK_LABELS, WORKFLOW_LABELS, format_date, safe_text, title_label
from core.campaign_ops.models import ReportingRequestListRow
from core.campaign_ops.reporting_requests import (
    REQUEST_CATEGORY_REPORT,
    REQUEST_CATEGORY_SURVEY,
    REQUEST_STATUS_CANCELLED,
    REQUEST_STATUS_COMPLETED,
)

SURVEY_COLUMNS = [
    "Type of Survey",
    "AM",
    "Program",
    "Due Date",
    "Link to Brief",
    "Delivered",
    "Review",
    "Questions / Notes",
]

REPORTING_COLUMNS = [
    "Type of Report",
    "AM",
    "Program",
    "Due Date",
    "Recap Date with Client",
    "Delivered",
    "Approval",
    "Special Requests",
]

ALL_REQUEST_COLUMNS = [
    "Category",
    "Request Type",
    "AM",
    "Program",
    "Due Date",
    "Status",
    "Next Gate",
    "Attention",
    "Risk",
]


def category_label(value: str) -> str:
    if value == REQUEST_CATEGORY_SURVEY:
        return "Survey Request"
    if value == REQUEST_CATEGORY_REPORT:
        return "Reporting Request"
    return title_label(value)


def status_label(value: str) -> str:
    return title_label(value)


def optional_text(value: str | None) -> str:
    return str(value) if value else ""


def delivered_label(value: bool) -> str:
    return "Delivered" if value else "Not Delivered"


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
        return "Open Brief"
    return optional_text(request.brief_status_text)


def recap_label(request: ReportingRequestListRow) -> str:
    return format_date(request.recap_date_with_client) if request.recap_date_with_client else optional_text(request.recap_date_text)


def attention_label(request: ReportingRequestListRow, today: date | None = None) -> str:
    today = today or date.today()
    if request.status == REQUEST_STATUS_COMPLETED or request.completed_at is not None:
        return "DONE"
    if request.status == REQUEST_STATUS_CANCELLED:
        return "CANCELLED"
    if request.due_date is None:
        return ""
    if request.due_date < today:
        return "OVERDUE"
    if request.due_date == today:
        return "DUE TODAY"
    if request.due_date <= today + timedelta(days=7):
        return "DUE THIS WEEK"
    return "UPCOMING"


def next_gate_label(request: ReportingRequestListRow) -> str:
    if request.status == REQUEST_STATUS_COMPLETED or request.completed_at is not None:
        return "Complete"
    if request.status == REQUEST_STATUS_CANCELLED:
        return "Cancelled"
    if request.request_category == REQUEST_CATEGORY_SURVEY:
        if not request.delivered:
            return "Deliver Survey"
        if request.review_required and not request.review_complete:
            return "Review Required"
        if request.review_required and request.review_complete:
            return "Review Complete"
        return status_label(request.status)
    if request.request_category == REQUEST_CATEGORY_REPORT:
        if not request.delivered:
            return "Deliver Report"
        if request.approval_required and not request.approved:
            return "Approval Required"
        if request.recap_date_with_client and (not request.approval_required or request.approved):
            return f"Client Recap {format_date(request.recap_date_with_client)}"
        if request.approval_required and request.approved:
            return "Approved"
        return status_label(request.status)
    return status_label(request.status)


def survey_request_rows(requests: list[ReportingRequestListRow]) -> list[dict[str, str]]:
    return [
        {
            "Type of Survey": request.request_type,
            "AM": request.am_display_name,
            "Program": request.program_name,
            "Due Date": format_date(request.due_date),
            "Link to Brief": brief_label(request),
            "Delivered": delivered_label(request.delivered),
            "Review": review_label(request),
            "Questions / Notes": optional_text(request.questions_requested),
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
            "Delivered": delivered_label(request.delivered),
            "Approval": approval_label(request),
            "Special Requests": optional_text(request.special_requests),
        }
        for request in requests
        if request.request_category == REQUEST_CATEGORY_REPORT
    ]


def all_request_rows(requests: list[ReportingRequestListRow]) -> list[dict[str, str]]:
    return [
        {
            "Category": category_label(request.request_category),
            "Request Type": request.request_type,
            "AM": request.am_display_name,
            "Program": request.program_name,
            "Due Date": format_date(request.due_date),
            "Status": status_label(request.status),
            "Next Gate": next_gate_label(request),
            "Attention": attention_label(request),
            "Risk": RISK_LABELS.get(request.risk, title_label(request.risk)),
        }
        for request in requests
    ]


def program_context_label(request: ReportingRequestListRow) -> str:
    return (
        f"{request.program_name} | Client: {safe_text(request.client_name)} | "
        f"Primary workflow: {WORKFLOW_LABELS.get(request.primary_workstream_type or '', '-')}"
    )
