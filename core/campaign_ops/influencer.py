from __future__ import annotations

from core.campaign_ops.exceptions import CampaignOpsValidationError

INFLUENCER_STAGE_PLANNING = "planning"
INFLUENCER_STAGE_LIVE = "live"
INFLUENCER_STAGE_RECAPPING = "recapping"
INFLUENCER_STAGE_COMPLETE = "complete"
INFLUENCER_STAGE_CANCELLED = "cancelled"

INFLUENCER_STAGES = (
    INFLUENCER_STAGE_PLANNING,
    INFLUENCER_STAGE_LIVE,
    INFLUENCER_STAGE_RECAPPING,
    INFLUENCER_STAGE_COMPLETE,
    INFLUENCER_STAGE_CANCELLED,
)

PLANNING_STATUS_NOT_STARTED = "not_started"
PLANNING_STATUS_APPLICATION_OPEN = "application_open"
PLANNING_STATUS_BRIEF_DEVELOPMENT = "brief_development"
PLANNING_STATUS_INFLUENCER_LIST_REVIEW = "influencer_list_review"
PLANNING_STATUS_AWAITING_INFLUENCER_APPROVAL = "awaiting_influencer_approval"
PLANNING_STATUS_HIRING_AND_CONTRACTING = "hiring_and_contracting"
PLANNING_STATUS_SCRIPTS_AND_CAPTIONS = "scripts_and_captions"
PLANNING_STATUS_INTERNAL_CONTENT_REVIEW = "internal_content_review"
PLANNING_STATUS_CLIENT_CONTENT_REVIEW = "client_content_review"
PLANNING_STATUS_REVISIONS = "revisions"
PLANNING_STATUS_CREATIVE_APPROVAL = "creative_approval"
PLANNING_STATUS_READY_TO_LAUNCH = "ready_to_launch"
PLANNING_STATUS_ON_HOLD = "on_hold"
PLANNING_STATUS_COMPLETE = "complete"
PLANNING_STATUS_CANCELLED = "cancelled"

PLANNING_STATUSES = (
    PLANNING_STATUS_NOT_STARTED,
    PLANNING_STATUS_APPLICATION_OPEN,
    PLANNING_STATUS_BRIEF_DEVELOPMENT,
    PLANNING_STATUS_INFLUENCER_LIST_REVIEW,
    PLANNING_STATUS_AWAITING_INFLUENCER_APPROVAL,
    PLANNING_STATUS_HIRING_AND_CONTRACTING,
    PLANNING_STATUS_SCRIPTS_AND_CAPTIONS,
    PLANNING_STATUS_INTERNAL_CONTENT_REVIEW,
    PLANNING_STATUS_CLIENT_CONTENT_REVIEW,
    PLANNING_STATUS_REVISIONS,
    PLANNING_STATUS_CREATIVE_APPROVAL,
    PLANNING_STATUS_READY_TO_LAUNCH,
    PLANNING_STATUS_ON_HOLD,
    PLANNING_STATUS_COMPLETE,
    PLANNING_STATUS_CANCELLED,
)

PLANNING_STEP_STATUSES = ("not_started", "in_progress", "waiting", "complete", "cancelled")
APPROVAL_STATUSES = ("not_sent", "sent", "feedback_received", "approved", "reopened", "cancelled")
CONTENT_ROUND_STATUSES = ("not_started", "internal_review", "sent_for_client_review", "feedback_received", "resubmission_due", "approved", "reopened", "cancelled")

RESPONSIBLE_PARTIES = ("Internal Team", "Client", "Influencer / Creator", "Vendor", "Platform", "Other")
APPROVAL_TYPES = ("Influencer List", "Brief", "Scripts and Captions", "Influencer Content", "Display Creative", "Final Content and Ads", "Other")
CONTENT_ROUND_TYPES = ("Scripts and Captions", "Draft Content", "First Round Content", "Second Round Content", "Final Content", "Display Creative", "Other")
INFLUENCER_RESOURCE_TYPES = (
    "Track Sheet",
    "Influencer Brief",
    "Bitly Link",
    "Invoice",
    "EOP Survey",
    "Influencer Education",
    "Campaign Brief",
    "Click2Cart Link",
    "Content Folder",
    "Application Link",
    "Custom",
)

LIVE_STATUS_READY_TO_LAUNCH = "ready_to_launch"
LIVE_STATUS_LAUNCHING = "launching"
LIVE_STATUS_LIVE = "live"
LIVE_STATUS_LIVE_IN_WAVES = "live_in_waves"
LIVE_STATUS_WAITING_ON_CREATOR = "waiting_on_creator"
LIVE_STATUS_WAITING_ON_CLIENT = "waiting_on_client"
LIVE_STATUS_RESUBMISSION = "resubmission"
LIVE_STATUS_PARTIALLY_LIVE = "partially_live"
LIVE_STATUS_PAID_LIVE = "paid_live"
LIVE_STATUS_ON_HOLD = "on_hold"
LIVE_STATUS_WRAPPING = "wrapping"
LIVE_STATUS_READY_FOR_RECAP = "ready_for_recap"
LIVE_STATUS_COMPLETE = "complete"
LIVE_STATUS_CANCELLED = "cancelled"

LIVE_STATUSES = (
    LIVE_STATUS_READY_TO_LAUNCH,
    LIVE_STATUS_LAUNCHING,
    LIVE_STATUS_LIVE,
    LIVE_STATUS_LIVE_IN_WAVES,
    LIVE_STATUS_WAITING_ON_CREATOR,
    LIVE_STATUS_WAITING_ON_CLIENT,
    LIVE_STATUS_RESUBMISSION,
    LIVE_STATUS_PARTIALLY_LIVE,
    LIVE_STATUS_PAID_LIVE,
    LIVE_STATUS_ON_HOLD,
    LIVE_STATUS_WRAPPING,
    LIVE_STATUS_READY_FOR_RECAP,
    LIVE_STATUS_COMPLETE,
    LIVE_STATUS_CANCELLED,
)

LIVE_CHECKPOINT_STATUSES = ("not_started", "in_progress", "waiting", "complete", "cancelled")
WAVE_STATUSES = ("not_started", "in_progress", "live", "complete", "reopened", "cancelled")
CREATOR_LIVE_STATUSES = ("not_started", "approved", "scheduled", "live", "paid_live_complete", "complete", "cancelled")
CREATOR_DRAFT_STATUSES = ("not_started", "submitted", "resubmission", "approved", "cancelled")
CREATOR_APPROVAL_STATUSES = ("pending", "approved", "rejected", "needs_revision")
LIVE_EXCEPTION_STATUSES = ("open", "waiting_on_client", "waiting_on_creator", "in_progress", "resolved", "reopened", "cancelled")
LIVE_EXCEPTION_TYPES = ("Client Feedback", "Creator Resubmission", "Product Availability", "Launch Delay", "Missing Link", "Approval Pending", "Other")

LIVE_RESOURCE_TYPES = (
    "Track Sheet",
    "Influencer Brief",
    "EOP Survey",
    "Invoice",
    "Bitly Link",
    "Click2Cart Link",
    "Walmart Link",
    "Retailer Link",
    "Client-Facing Live Doc",
    "Daily Impressions",
    "Influencer Education",
    "Client Guidelines",
    "Content Folder",
    "Custom",
)

STANDARD_LIVE_CHECKPOINT_TEMPLATE = (
    "Final content approved",
    "Final display creative approved",
    "Creator schedules confirmed",
    "Click2Cart links confirmed",
    "Client-facing live document ready",
    "First creator wave begins",
    "Daily impressions reporting starts",
    "Additional creator waves begin",
    "Paid-live monitoring",
    "Final creators go live",
    "All creator links verified",
    "Campaign wrap",
    "Ready for recap",
)

STANDARD_PLANNING_TEMPLATE = (
    "Application out to influencers",
    "Send brief and influencer list for client review",
    "Vet influencer list",
    "Client influencer approvals due",
    "Hire and secure scripts and captions",
    "Scripts and captions due from influencers",
    "Send scripts and captions to client",
    "Client script/caption feedback due",
    "Influencer drafts due for internal review",
    "Draft resubmissions due",
    "First round of content sent for client review",
    "Client content feedback due",
    "Second round of content sent",
    "Second-round feedback due",
    "Display creative sent for approval",
    "Final influencer content and ads approved",
    "Content and ads go live",
    "Campaign wraps",
)


def _normalize(value: str | None, default: str, allowed: tuple[str, ...], label: str) -> str:
    cleaned = (value or default).strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned not in allowed:
        raise CampaignOpsValidationError(f"{label} is invalid.")
    return cleaned


def normalize_influencer_stage(value: str | None) -> str:
    return _normalize(value, INFLUENCER_STAGE_PLANNING, INFLUENCER_STAGES, "Influencer stage")


def normalize_planning_status(value: str | None) -> str:
    return _normalize(value, PLANNING_STATUS_NOT_STARTED, PLANNING_STATUSES, "Planning status")


def normalize_live_status(value: str | None) -> str:
    return _normalize(value, LIVE_STATUS_READY_TO_LAUNCH, LIVE_STATUSES, "Live status")


def normalize_optional_status(value: str | None, allowed: tuple[str, ...], label: str) -> str | None:
    if value in (None, ""):
        return None
    return _normalize(str(value), allowed[0], allowed, label)
