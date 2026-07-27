from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    ADMINISTRATOR = "administrator"
    TEAM_MEMBER = "team_member"
    VIEWER = "viewer"


class ProgramStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETE = "complete"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class CrossStage(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    READY_TO_LAUNCH = "ready_to_launch"
    LIVE = "live"
    RECAPPING = "recapping"
    COMPLETE = "complete"
    ON_HOLD = "on_hold"


class WorkstreamType(StrEnum):
    INFLUENCER = "influencer"
    RETAIL_MEDIA = "retail_media"
    ECOMMERCE = "ecommerce"
    SMM = "smm"
    PAID_SOCIAL = "paid_social"
    REPORTING = "reporting"
    INSIGHTS = "insights"
    SEO = "seo"


class TaskStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY_FOR_INTERNAL_REVIEW = "ready_for_internal_review"
    READY_FOR_CLIENT_REVIEW = "ready_for_client_review"
    WAITING_ON_CLIENT = "waiting_on_client"
    WAITING_ON_CREATOR = "waiting_on_creator"
    WAITING_ON_INTERNAL_TEAM = "waiting_on_internal_team"
    BLOCKED = "blocked"
    APPROVED = "approved"
    COMPLETED = "completed"
    NOT_APPLICABLE = "not_applicable"


class RiskLevel(StrEnum):
    UNRATED = "unrated"
    ON_TRACK = "on_track"
    NEEDS_ATTENTION = "needs_attention"
    AT_RISK = "at_risk"
    ON_HOLD = "on_hold"


class AssignmentRole(StrEnum):
    PROGRAM_OWNER = "program_owner"
    WORKSTREAM_LEAD = "workstream_lead"
    CONTRIBUTOR = "contributor"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    VIEWER = "viewer"
    ADMIN_OVERSIGHT = "admin_oversight"


class WaitingOn(StrEnum):
    NONE = "none"
    CLIENT = "client"
    INTERNAL_TEAM = "internal_team"
    CREATOR = "creator"
    RETAILER = "retailer"
    VENDOR = "vendor"
    PLATFORM = "platform"
    ASSETS = "assets"
    APPROVAL = "approval"
    INFORMATION = "information"
    OTHER = "other"
