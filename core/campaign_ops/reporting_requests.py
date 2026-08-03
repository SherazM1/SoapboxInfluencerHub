from __future__ import annotations

from core.campaign_ops.exceptions import CampaignOpsValidationError

REQUEST_CATEGORY_SURVEY = "survey"
REQUEST_CATEGORY_REPORT = "report"
REQUEST_CATEGORIES = {REQUEST_CATEGORY_SURVEY, REQUEST_CATEGORY_REPORT}

REQUEST_STATUS_REQUESTED = "requested"
REQUEST_STATUS_IN_PROGRESS = "in_progress"
REQUEST_STATUS_READY_FOR_REVIEW = "ready_for_review"
REQUEST_STATUS_WAITING_FOR_APPROVAL = "waiting_for_approval"
REQUEST_STATUS_DELIVERED = "delivered"
REQUEST_STATUS_COMPLETED = "completed"
REQUEST_STATUS_CANCELLED = "cancelled"

REQUEST_STATUSES = {
    REQUEST_STATUS_REQUESTED,
    REQUEST_STATUS_IN_PROGRESS,
    REQUEST_STATUS_READY_FOR_REVIEW,
    REQUEST_STATUS_WAITING_FOR_APPROVAL,
    REQUEST_STATUS_DELIVERED,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_CANCELLED,
}

AM_NAME_ALIASES = {
    "bailey": "Bailey",
    "taylor": "T",
    "t": "T",
    "lauren": "L",
    "l": "L",
}


def normalize_am_name(value: str | None) -> str:
    cleaned = " ".join((value or "").strip().split()).casefold()
    if not cleaned:
        raise CampaignOpsValidationError("AM is required.")
    display_name = AM_NAME_ALIASES.get(cleaned)
    if display_name is None:
        raise CampaignOpsValidationError("AM must resolve to Bailey, T, or L.")
    return display_name


def validate_request_category(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    if cleaned not in REQUEST_CATEGORIES:
        raise CampaignOpsValidationError("Request category must be survey or report.")
    return cleaned


def validate_request_status(value: str | None) -> str:
    cleaned = (value or REQUEST_STATUS_REQUESTED).strip().lower()
    if cleaned not in REQUEST_STATUSES:
        raise CampaignOpsValidationError("Request status is invalid.")
    return cleaned
