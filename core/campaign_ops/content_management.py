from __future__ import annotations

from core.campaign_ops.exceptions import CampaignOpsValidationError

CONTENT_STATUS_NOT_STARTED = "not_started"
CONTENT_STATUS_PLANNING = "planning"
CONTENT_STATUS_AWAITING_ASSETS = "awaiting_assets"
CONTENT_STATUS_COPY_DEVELOPMENT = "copy_development"
CONTENT_STATUS_ATTRIBUTE_OPTIMIZATION = "attribute_optimization"
CONTENT_STATUS_GRAPHICS_DEVELOPMENT = "graphics_development"
CONTENT_STATUS_INTERNAL_REVIEW = "internal_review"
CONTENT_STATUS_CLIENT_REVIEW = "client_review"
CONTENT_STATUS_READY_TO_SUBMIT = "ready_to_submit"
CONTENT_STATUS_SUBMITTED = "submitted"
CONTENT_STATUS_AWAITING_PUBLICATION = "awaiting_publication"
CONTENT_STATUS_PARTIALLY_LIVE = "partially_live"
CONTENT_STATUS_LIVE = "live"
CONTENT_STATUS_MONITORING = "monitoring"
CONTENT_STATUS_MAINTENANCE = "maintenance"
CONTENT_STATUS_REPORTING = "reporting"
CONTENT_STATUS_COMPLETE = "complete"
CONTENT_STATUS_ON_HOLD = "on_hold"
CONTENT_STATUS_CANCELLED = "cancelled"

CONTENT_STATUSES = (
    CONTENT_STATUS_NOT_STARTED,
    CONTENT_STATUS_PLANNING,
    CONTENT_STATUS_AWAITING_ASSETS,
    CONTENT_STATUS_COPY_DEVELOPMENT,
    CONTENT_STATUS_ATTRIBUTE_OPTIMIZATION,
    CONTENT_STATUS_GRAPHICS_DEVELOPMENT,
    CONTENT_STATUS_INTERNAL_REVIEW,
    CONTENT_STATUS_CLIENT_REVIEW,
    CONTENT_STATUS_READY_TO_SUBMIT,
    CONTENT_STATUS_SUBMITTED,
    CONTENT_STATUS_AWAITING_PUBLICATION,
    CONTENT_STATUS_PARTIALLY_LIVE,
    CONTENT_STATUS_LIVE,
    CONTENT_STATUS_MONITORING,
    CONTENT_STATUS_MAINTENANCE,
    CONTENT_STATUS_REPORTING,
    CONTENT_STATUS_COMPLETE,
    CONTENT_STATUS_ON_HOLD,
    CONTENT_STATUS_CANCELLED,
)

COPY_STATUSES = ("not_started", "drafting", "internal_review", "client_review", "approved", "delivered", "not_required")
GRAPHICS_STATUSES = ("not_started", "in_progress", "internal_review", "client_review", "approved", "delivered", "not_required")
SUBMISSION_STATUSES = ("not_submitted", "ready_to_submit", "submitted", "accepted", "rejected", "resubmission_required")
PUBLICATION_STATUSES = ("not_live", "partially_live", "live", "removed", "monitoring", "issue_found")
DELIVERABLE_TYPES = (
    "Product copy",
    "PDP copy",
    "Optimized attributes",
    "Product graphics",
    "Lifestyle image",
    "Card art",
    "Creative request deck",
    "PDP request deck",
    "Keyword insights",
    "Photography",
    "Reporting",
    "Custom",
)
CONTENT_RESOURCE_TYPES = (
    "SKU List",
    "Tracksheet",
    "Creative Request Deck",
    "PDP Request Deck",
    "Keyword Insights",
    "Photography Folder",
    "Resources Folder",
    "Reporting Folder",
    "Invoice Schedule",
    "Custom",
)


def normalize_content_status(value: str | None) -> str:
    cleaned = (value or CONTENT_STATUS_NOT_STARTED).strip().lower().replace(" ", "_")
    if cleaned not in CONTENT_STATUSES:
        raise CampaignOpsValidationError("Content status is invalid.")
    return cleaned


def normalize_optional_status(value: str | None, allowed: tuple[str, ...], label: str) -> str | None:
    if value in (None, ""):
        return None
    cleaned = str(value).strip().lower().replace(" ", "_")
    if cleaned not in allowed:
        raise CampaignOpsValidationError(f"{label} is invalid.")
    return cleaned
