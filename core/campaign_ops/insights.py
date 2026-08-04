from __future__ import annotations

from core.campaign_ops.exceptions import CampaignOpsValidationError

INSIGHTS_STATUS_NOT_STARTED = "not_started"
INSIGHTS_STATUS_DRAFTING_SURVEY = "drafting_survey"
INSIGHTS_STATUS_CLIENT_REVIEW = "client_review"
INSIGHTS_STATUS_AWAITING_FEEDBACK = "awaiting_feedback"
INSIGHTS_STATUS_SURVEY_PROGRAMMING = "survey_programming"
INSIGHTS_STATUS_SURVEY_IN_FIELD = "survey_in_field"
INSIGHTS_STATUS_ANALYSIS = "analysis"
INSIGHTS_STATUS_RESULTS_DRAFTING = "results_drafting"
INSIGHTS_STATUS_RESULTS_REVIEW = "results_review"
INSIGHTS_STATUS_COMPLETE = "complete"
INSIGHTS_STATUS_ON_HOLD = "on_hold"

INSIGHTS_STATUSES = (
    INSIGHTS_STATUS_NOT_STARTED,
    INSIGHTS_STATUS_DRAFTING_SURVEY,
    INSIGHTS_STATUS_CLIENT_REVIEW,
    INSIGHTS_STATUS_AWAITING_FEEDBACK,
    INSIGHTS_STATUS_SURVEY_PROGRAMMING,
    INSIGHTS_STATUS_SURVEY_IN_FIELD,
    INSIGHTS_STATUS_ANALYSIS,
    INSIGHTS_STATUS_RESULTS_DRAFTING,
    INSIGHTS_STATUS_RESULTS_REVIEW,
    INSIGHTS_STATUS_COMPLETE,
    INSIGHTS_STATUS_ON_HOLD,
)

INSIGHTS_RESOURCE_TYPES = (
    "Tracksheet",
    "Results Deck",
    "Raw Data",
    "Raw Data Key",
    "Survey Draft",
    "Test Link",
    "Custom",
)


def validate_insights_status(value: str | None) -> str:
    cleaned = (value or INSIGHTS_STATUS_NOT_STARTED).strip().lower()
    if cleaned not in INSIGHTS_STATUSES:
        raise CampaignOpsValidationError("Insights status is invalid.")
    return cleaned
