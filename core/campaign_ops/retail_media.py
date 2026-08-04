from __future__ import annotations

from core.campaign_ops.exceptions import CampaignOpsValidationError

RETAIL_MEDIA_STATUS_NOT_STARTED = "not_started"
RETAIL_MEDIA_STATUS_PLANNING = "planning"
RETAIL_MEDIA_STATUS_CREATIVE_DEVELOPMENT = "creative_development"
RETAIL_MEDIA_STATUS_INTERNAL_REVIEW = "internal_review"
RETAIL_MEDIA_STATUS_CLIENT_REVIEW = "client_review"
RETAIL_MEDIA_STATUS_PLATFORM_SUBMISSION = "platform_submission"
RETAIL_MEDIA_STATUS_READY_TO_LAUNCH = "ready_to_launch"
RETAIL_MEDIA_STATUS_LIVE = "live"
RETAIL_MEDIA_STATUS_OPTIMIZING = "optimizing"
RETAIL_MEDIA_STATUS_PAUSED = "paused"
RETAIL_MEDIA_STATUS_WRAPPING = "wrapping"
RETAIL_MEDIA_STATUS_REPORTING = "reporting"
RETAIL_MEDIA_STATUS_COMPLETE = "complete"
RETAIL_MEDIA_STATUS_CANCELLED = "cancelled"

RETAIL_MEDIA_STATUSES = (
    RETAIL_MEDIA_STATUS_NOT_STARTED,
    RETAIL_MEDIA_STATUS_PLANNING,
    RETAIL_MEDIA_STATUS_CREATIVE_DEVELOPMENT,
    RETAIL_MEDIA_STATUS_INTERNAL_REVIEW,
    RETAIL_MEDIA_STATUS_CLIENT_REVIEW,
    RETAIL_MEDIA_STATUS_PLATFORM_SUBMISSION,
    RETAIL_MEDIA_STATUS_READY_TO_LAUNCH,
    RETAIL_MEDIA_STATUS_LIVE,
    RETAIL_MEDIA_STATUS_OPTIMIZING,
    RETAIL_MEDIA_STATUS_PAUSED,
    RETAIL_MEDIA_STATUS_WRAPPING,
    RETAIL_MEDIA_STATUS_REPORTING,
    RETAIL_MEDIA_STATUS_COMPLETE,
    RETAIL_MEDIA_STATUS_CANCELLED,
)

RETAIL_MEDIA_CHANNEL_TYPES = (
    "Onsite Display",
    "Offsite Display",
    "Sponsored Search",
    "Onsite",
    "Offsite",
    "Display",
    "Search",
    "CA TTO",
    "Other",
)

RETAIL_MEDIA_RESOURCE_TYPES = (
    "Tracksheet",
    "Program Tracksheet",
    "Budget Tracker",
    "Optimization Log",
    "Media Plan / Budget",
    "RM Strategy",
    "WPSR Weekly Update",
    "Creative Folder",
    "Reporting Folder",
    "Custom",
)

RETAIL_MEDIA_APPROVAL_STATUSES = (
    "not_started",
    "internal_review",
    "client_review",
    "changes_requested",
    "approved",
    "rejected",
    "not_required",
)

RETAIL_MEDIA_SUBMISSION_STATUSES = (
    "not_submitted",
    "ready_to_submit",
    "submitted",
    "accepted",
    "rejected",
    "live",
)


def normalize_retail_media_status(value: str | None) -> str:
    cleaned = (value or RETAIL_MEDIA_STATUS_NOT_STARTED).strip().lower().replace(" ", "_")
    if cleaned not in RETAIL_MEDIA_STATUSES:
        raise CampaignOpsValidationError("Retail Media status is invalid.")
    return cleaned


def normalize_approval_status(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip().lower().replace(" ", "_")
    if cleaned not in RETAIL_MEDIA_APPROVAL_STATUSES:
        raise CampaignOpsValidationError("Creative approval status is invalid.")
    return cleaned


def normalize_submission_status(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip().lower().replace(" ", "_")
    if cleaned not in RETAIL_MEDIA_SUBMISSION_STATUSES:
        raise CampaignOpsValidationError("Creative submission status is invalid.")
    return cleaned
