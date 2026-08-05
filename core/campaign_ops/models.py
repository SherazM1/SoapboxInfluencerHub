from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from core.campaign_ops.enums import (
    AssignmentRole,
    CrossStage,
    ProgramStatus,
    RiskLevel,
    TaskStatus,
    UserRole,
    WaitingOn,
    WorkstreamType,
)
from core.campaign_ops.exceptions import CampaignOpsValidationError


def require_text(value: str | None, field_name: str) -> str:
    """Validate a required text field."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise CampaignOpsValidationError(f"{field_name} is required.")
    return cleaned


def enum_value(enum_type: type, value: Any, field_name: str) -> str:
    """Normalize and validate a stored enum value."""
    raw_value = getattr(value, "value", value)
    try:
        return enum_type(raw_value).value
    except ValueError as exc:
        raise CampaignOpsValidationError(
            f"{field_name} must be one of: "
            + ", ".join(item.value for item in enum_type)
        ) from exc


@dataclass(slots=True)
class CampaignOpsUser:
    id: str
    display_name: str
    role: str
    email: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.display_name = require_text(self.display_name, "display_name")
        self.role = enum_value(UserRole, self.role, "role")


@dataclass(slots=True)
class Client:
    id: str
    name: str
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        self.name = require_text(self.name, "name")


@dataclass(slots=True)
class Program:
    id: str
    program_name: str
    status: str = ProgramStatus.DRAFT.value
    cross_stage: str = CrossStage.DRAFT.value
    risk_level: str = RiskLevel.UNRATED.value
    client_id: str | None = None
    primary_workstream_type: str | None = None
    priority: str | None = None
    description: str | None = None
    latest_update: str | None = None
    start_date: date | None = None
    target_end_date: date | None = None
    archived_at: datetime | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        self.program_name = require_text(self.program_name, "program_name")
        self.status = enum_value(ProgramStatus, self.status, "status")
        self.cross_stage = enum_value(CrossStage, self.cross_stage, "cross_stage")
        self.risk_level = enum_value(RiskLevel, self.risk_level, "risk_level")
        if self.primary_workstream_type is not None:
            self.primary_workstream_type = enum_value(
                WorkstreamType,
                self.primary_workstream_type,
                "primary_workstream_type",
            )


@dataclass(slots=True)
class Workstream:
    id: str
    program_id: str
    workstream_type: str
    status: str = ProgramStatus.ACTIVE.value
    cross_stage: str = CrossStage.PLANNING.value
    risk_level: str = RiskLevel.UNRATED.value
    owner_user_id: str | None = None
    next_action: str | None = None
    next_due_date: date | None = None
    waiting_on: str = WaitingOn.NONE.value
    latest_update: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        self.workstream_type = enum_value(WorkstreamType, self.workstream_type, "workstream_type")
        self.status = enum_value(ProgramStatus, self.status, "status")
        self.cross_stage = enum_value(CrossStage, self.cross_stage, "cross_stage")
        self.risk_level = enum_value(RiskLevel, self.risk_level, "risk_level")
        self.waiting_on = enum_value(WaitingOn, self.waiting_on, "waiting_on")


@dataclass(slots=True)
class ProgramAssignment:
    id: str
    program_id: str
    user_id: str
    assignment_role: str
    workstream_id: str | None = None
    is_primary: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        self.assignment_role = enum_value(AssignmentRole, self.assignment_role, "assignment_role")


@dataclass(slots=True)
class Task:
    id: str
    program_id: str
    title: str
    workstream_id: str | None = None
    description: str | None = None
    assigned_user_id: str | None = None
    responsible_party: str | None = None
    status: str = TaskStatus.NOT_STARTED.value
    risk_level: str = RiskLevel.UNRATED.value
    waiting_on: str = WaitingOn.NONE.value
    due_date: date | None = None
    start_date: date | None = None
    completed_at: datetime | None = None
    hard_deadline: bool = False
    priority: str | None = None
    sort_order: int = 0
    metadata_json: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        self.title = require_text(self.title, "title")
        self.status = enum_value(TaskStatus, self.status, "status")
        self.risk_level = enum_value(RiskLevel, self.risk_level, "risk_level")
        self.waiting_on = enum_value(WaitingOn, self.waiting_on, "waiting_on")


@dataclass(slots=True)
class Milestone:
    id: str
    program_id: str
    title: str
    status: str
    workstream_id: str | None = None
    milestone_type: str | None = None
    target_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    owner_user_id: str | None = None
    hard_deadline: bool = False
    completed_at: datetime | None = None
    is_highlighted: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        self.title = require_text(self.title, "title")
        self.status = enum_value(TaskStatus, self.status, "status")


@dataclass(slots=True)
class Resource:
    id: str
    program_id: str
    resource_type: str
    title: str
    workstream_id: str | None = None
    url: str | None = None
    notes: str | None = None
    is_required: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None
    updated_by: str | None = None

    def __post_init__(self) -> None:
        self.resource_type = require_text(self.resource_type, "resource_type")
        self.title = require_text(self.title, "title")


@dataclass(slots=True)
class ProgramNote:
    id: str
    program_id: str
    note_text: str
    workstream_id: str | None = None
    task_id: str | None = None
    author_user_id: str | None = None
    note_type: str | None = None
    is_internal: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.note_text = require_text(self.note_text, "note_text")


@dataclass(slots=True)
class TaskDependency:
    id: str
    task_id: str
    depends_on_task_id: str
    dependency_type: str | None = None
    created_at: datetime | None = None
    created_by: str | None = None

    def __post_init__(self) -> None:
        if self.task_id == self.depends_on_task_id:
            raise CampaignOpsValidationError("A task cannot depend on itself.")


@dataclass(slots=True)
class ActivityEvent:
    id: str
    event_type: str
    entity_type: str
    program_id: str | None = None
    workstream_id: str | None = None
    task_id: str | None = None
    actor_user_id: str | None = None
    entity_id: str | None = None
    old_value_json: dict[str, Any] | None = None
    new_value_json: dict[str, Any] | None = None
    message: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        self.event_type = require_text(self.event_type, "event_type")
        self.entity_type = require_text(self.entity_type, "entity_type")


@dataclass(slots=True)
class ProgramPortfolioRow:
    id: str
    program_name: str
    client_name: str | None
    primary_workstream_type: str | None
    workstream_types: list[str] = field(default_factory=list)
    status: str = ProgramStatus.DRAFT.value
    cross_stage: str = CrossStage.DRAFT.value
    risk_level: str = RiskLevel.UNRATED.value
    priority: str | None = None
    primary_owner_user_id: str | None = None
    primary_owner_name: str | None = None
    assigned_user_ids: list[str] = field(default_factory=list)
    assigned_user_names: list[str] = field(default_factory=list)
    latest_update: str | None = None
    start_date: date | None = None
    target_end_date: date | None = None
    updated_at: datetime | None = None
    is_active: bool = True
    assignment_role: str | None = None
    assigned_workstream_type: str | None = None
    open_task_count: int = 0
    overdue_task_count: int = 0
    nearest_task_due_date: date | None = None


@dataclass(slots=True)
class ProgramWorkspaceSummary:
    program: Program
    client: Client | None
    workstreams: list[Workstream]
    assignments: list[ProgramAssignment]
    users: list[CampaignOpsUser]
    activity: list[ActivityEvent]


@dataclass(slots=True)
class TaskListRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    title: str
    description: str | None
    workstream_id: str | None
    workstream_type: str | None
    assigned_user_id: str | None
    assigned_user_name: str | None
    responsible_party: str | None
    status: str
    risk_level: str
    waiting_on: str
    due_date: date | None
    start_date: date | None
    completed_at: datetime | None
    hard_deadline: bool
    priority: str | None
    sort_order: int
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class MilestoneListRow:
    id: str
    program_id: str
    title: str
    status: str
    workstream_id: str | None
    workstream_type: str | None
    milestone_type: str | None
    target_date: date | None
    start_date: date | None
    end_date: date | None
    owner_user_id: str | None
    owner_user_name: str | None
    hard_deadline: bool
    completed_at: datetime | None
    is_highlighted: bool
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class ResourceListRow:
    id: str
    program_id: str
    title: str
    resource_type: str
    workstream_id: str | None
    workstream_type: str | None
    url: str | None
    notes: str | None
    is_required: bool
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class NoteListRow:
    id: str
    program_id: str
    workstream_id: str | None
    workstream_type: str | None
    task_id: str | None
    task_title: str | None
    author_user_id: str | None
    author_display_name: str | None
    note_text: str
    note_type: str | None
    is_internal: bool
    created_at: datetime | None


@dataclass(slots=True)
class ReportingRequestRecord:
    id: str
    program_id: str
    request_category: str
    request_type: str
    am_user_id: str
    workstream_id: str | None = None
    assigned_user_id: str | None = None
    due_date: date | None = None
    recap_date_with_client: date | None = None
    recap_date_text: str | None = None
    brief_url: str | None = None
    brief_status_text: str | None = None
    delivered: bool = False
    review_required: bool = False
    review_complete: bool = False
    approval_required: bool = False
    approved: bool = False
    questions_requested: str | None = None
    special_requests: str | None = None
    status: str = "requested"
    risk: str = RiskLevel.UNRATED.value
    waiting_on: str | None = None
    completed_at: datetime | None = None
    is_active: bool = True
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.request_type = require_text(self.request_type, "request_type")


@dataclass(slots=True)
class ReportingRequestListRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    primary_workstream_type: str | None
    request_category: str
    request_type: str
    am_user_id: str
    am_display_name: str
    assigned_user_id: str | None
    assigned_display_name: str | None
    workstream_id: str | None
    workstream_type: str | None
    due_date: date | None
    recap_date_with_client: date | None
    recap_date_text: str | None
    brief_url: str | None
    brief_status_text: str | None
    delivered: bool
    review_required: bool
    review_complete: bool
    approval_required: bool
    approved: bool
    questions_requested: str | None
    special_requests: str | None
    status: str
    risk: str
    waiting_on: str | None
    completed_at: datetime | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


ReportingRequestDetail = ReportingRequestListRow


@dataclass(slots=True)
class DashboardMetricSet:
    active_programs: int = 0
    needs_attention: int = 0
    high_risk: int = 0
    overdue_tasks: int = 0
    due_this_week: int = 0
    upcoming_milestones: int = 0
    waiting_on_client: int = 0
    waiting_on_internal_team: int = 0
    paused_on_hold: int = 0
    ready_for_recap: int = 0
    ready_to_close: int = 0
    completed_recently: int = 0


@dataclass(slots=True)
class NeedsAttentionRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workflow: str
    stage: str | None
    owner_user_id: str | None
    owner_name: str | None
    assigned_user_id: str | None
    assigned_name: str | None
    attention_reason: str
    severity: str
    risk: str | None
    waiting_on: str | None
    due_date: date | None
    days_overdue: int | None
    latest_update: str | None
    target_section: str = "Program Workspace"
    target_record_id: str | None = None


@dataclass(slots=True)
class WaitingOnRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workflow: str
    record_type: str
    item: str
    owner_user_id: str | None
    owner_name: str | None
    waiting_on: str | None
    waiting_category: str
    due_date: date | None
    age: int | None
    latest_update: str | None
    target_section: str = "Program Workspace"
    target_record_id: str | None = None


@dataclass(slots=True)
class DashboardTaskRow:
    id: str
    program_id: str
    task: str
    program_name: str
    client_name: str | None
    workstream: str | None
    assigned_user_id: str | None
    assigned_user_name: str | None
    responsible_party: str | None
    status: str
    risk: str
    due_date: date | None
    days_overdue: int
    waiting_on: str | None
    hard_deadline: bool


@dataclass(slots=True)
class UpcomingMilestoneRow:
    id: str
    program_id: str
    milestone: str
    program_name: str
    client_name: str | None
    workstream: str | None
    owner_user_id: str | None
    owner_name: str | None
    status: str
    best_available_date: date | None
    days_until: int | None
    hard_deadline: bool
    highlighted: bool


@dataclass(slots=True)
class WorkloadByPersonRow:
    user_id: str
    display_name: str
    owned_active_programs: int = 0
    assigned_active_programs: int = 0
    open_tasks: int = 0
    overdue_tasks: int = 0
    due_this_week: int = 0
    active_milestones_owned: int = 0
    needs_attention_programs: int = 0
    waiting_items: int = 0
    influencer_planning: int = 0
    influencer_live: int = 0
    influencer_recapping: int = 0
    reporting_requests: int = 0
    insights_projects: int = 0
    retail_media_campaigns: int = 0
    content_programs: int = 0


@dataclass(slots=True)
class DashboardWorkflowCard:
    id: str
    program_id: str
    title: str
    client_name: str | None
    workflow: str
    owner_user_id: str | None
    owner_name: str | None
    stage: str | None
    status: str | None
    latest_update: str | None
    waiting_on: str | None
    next_item: str | None
    next_date: date | None
    risk: str | None
    needs_attention: bool
    details: str | None = None
    target_section: str = "Program Workspace"


InfluencerDashboardCard = DashboardWorkflowCard
RetailMediaDashboardCard = DashboardWorkflowCard
ContentDashboardCard = DashboardWorkflowCard
InsightsDashboardCard = DashboardWorkflowCard
RequestDashboardCard = DashboardWorkflowCard


@dataclass(slots=True)
class DashboardProgramRow:
    id: str
    program_name: str
    client_name: str | None
    primary_workflow: str | None
    connected_workstreams: list[str]
    program_status: str
    cross_stage: str
    specialized_stage: str | None
    risk: str
    priority: str | None
    primary_owner_user_id: str | None
    primary_owner_name: str | None
    assigned_people: list[str]
    latest_update: str | None
    waiting_on: str | None
    open_tasks: int
    overdue_tasks: int
    next_task_due: date | None
    next_milestone: str | None
    needs_attention_reasons: list[str]
    start_date: date | None
    target_end_date: date | None
    updated_at: datetime | None
    active_state: str


@dataclass(slots=True)
class CrossTeamDashboardSummary:
    metrics: DashboardMetricSet
    needs_attention: list[NeedsAttentionRow]
    waiting_on: list[WaitingOnRow]
    overdue_tasks: list[DashboardTaskRow]
    upcoming_milestones: list[UpcomingMilestoneRow]
    workload: list[WorkloadByPersonRow]
    influencer_cards: list[DashboardWorkflowCard]
    retail_media_cards: list[DashboardWorkflowCard]
    content_cards: list[DashboardWorkflowCard]
    insights_cards: list[DashboardWorkflowCard]
    request_cards: list[DashboardWorkflowCard]
    programs: list[DashboardProgramRow]


@dataclass(slots=True)
class InsightsProjectRecord:
    id: str
    program_id: str
    project_title: str
    workstream_id: str | None = None
    job_number: str | None = None
    insights_status: str | None = None
    latest_update: str | None = None
    total_program_cost: float | None = None
    sample_size: int | None = None
    budget: float | None = None
    owner_user_id: str | None = None
    is_active: bool = True
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.project_title = require_text(self.project_title, "project_title")


@dataclass(slots=True)
class InsightsPortfolioRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workstream_id: str | None
    project_title: str
    job_number: str | None
    insights_status: str | None
    latest_update: str | None
    owner_user_id: str | None
    owner_display_name: str | None
    total_program_cost: float | None
    sample_size: int | None
    budget: float | None
    program_status: str
    program_risk: str
    next_milestone: str | None
    next_milestone_date: date | None
    tracksheet_url: str | None
    results_deck_url: str | None
    raw_data_url: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


InsightsProjectDetail = InsightsPortfolioRow


@dataclass(slots=True)
class InsightsObjectiveRecord:
    id: str
    insights_project_id: str
    objective_text: str
    sort_order: int = 0
    is_active: bool = True
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.objective_text = require_text(self.objective_text, "objective_text")


@dataclass(slots=True)
class RetailMediaCampaignRecord:
    id: str
    program_id: str
    campaign_title: str
    workstream_id: str | None = None
    retail_media_status: str | None = None
    latest_update: str | None = None
    waiting_on: str | None = None
    owner_user_id: str | None = None
    launch_date: date | None = None
    wrap_date: date | None = None
    reporting_cadence: str | None = None
    overall_budget: float | None = None
    total_spend: float | None = None
    is_paused: bool = False
    pause_reason: str | None = None
    is_active: bool = True
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.campaign_title = require_text(self.campaign_title, "campaign_title")


@dataclass(slots=True)
class RetailMediaPortfolioRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workstream_id: str | None
    campaign_title: str
    retail_media_status: str | None
    latest_update: str | None
    waiting_on: str | None
    owner_user_id: str | None
    owner_display_name: str | None
    launch_date: date | None
    wrap_date: date | None
    reporting_cadence: str | None
    overall_budget: float | None
    total_spend: float | None
    channel_budget_total: float | None
    channel_spend_total: float | None
    channel_mix: list[str]
    program_status: str
    program_risk: str
    next_milestone: str | None
    next_milestone_date: date | None
    tracksheet_url: str | None
    budget_tracker_url: str | None
    optimization_log_url: str | None
    is_paused: bool
    pause_reason: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


RetailMediaCampaignDetail = RetailMediaPortfolioRow


@dataclass(slots=True)
class RetailMediaChannelRecord:
    id: str
    retail_media_campaign_id: str
    channel_type: str
    platform_name: str | None = None
    status: str | None = None
    budget: float | None = None
    spend_to_date: float | None = None
    launch_date: date | None = None
    end_date: date | None = None
    reporting_requirement: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.channel_type = require_text(self.channel_type, "channel_type")


@dataclass(slots=True)
class RetailMediaActivationRecord:
    id: str
    retail_media_campaign_id: str
    activation_name: str
    channel_id: str | None = None
    activation_type: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    hard_deadline: bool = False
    waiting_on: str | None = None
    latest_update: str | None = None
    completed_at: datetime | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.activation_name = require_text(self.activation_name, "activation_name")


@dataclass(slots=True)
class RetailMediaCreativeRecord:
    id: str
    retail_media_campaign_id: str
    creative_name: str
    channel_id: str | None = None
    creative_type: str | None = None
    approval_status: str | None = None
    submission_status: str | None = None
    platform_status: str | None = None
    due_date: date | None = None
    submitted_date: date | None = None
    approved_date: date | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.creative_name = require_text(self.creative_name, "creative_name")


@dataclass(slots=True)
class RetailMediaOptimizationRecord:
    id: str
    retail_media_campaign_id: str
    update_date: date
    update_text: str
    channel_id: str | None = None
    optimization_type: str | None = None
    created_by_user_id: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.update_text = require_text(self.update_text, "update_text")


@dataclass(slots=True)
class ContentProgramRecord:
    id: str
    program_id: str
    content_program_title: str
    workstream_id: str | None = None
    content_status: str | None = None
    latest_update: str | None = None
    waiting_on: str | None = None
    owner_user_id: str | None = None
    total_sku_count: int | None = None
    default_graphics_per_sku: int | None = None
    monitoring_start_date: date | None = None
    maintenance_end_date: date | None = None
    reporting_cadence: str | None = None
    is_invoiced: bool = False
    invoice_status: str | None = None
    is_active: bool = True
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.content_program_title = require_text(self.content_program_title, "content_program_title")


@dataclass(slots=True)
class ContentPortfolioRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workstream_id: str | None
    content_program_title: str
    content_status: str | None
    latest_update: str | None
    waiting_on: str | None
    owner_user_id: str | None
    owner_display_name: str | None
    total_sku_count: int | None
    default_graphics_per_sku: int | None
    monitoring_start_date: date | None
    maintenance_end_date: date | None
    reporting_cadence: str | None
    is_invoiced: bool
    invoice_status: str | None
    group_names: list[str]
    group_expected_sku_total: int | None
    active_sku_count: int
    delivered_count: int
    live_count: int
    issue_count: int
    program_status: str
    program_risk: str
    next_milestone: str | None
    next_milestone_date: date | None
    sku_list_url: str | None
    tracksheet_url: str | None
    creative_request_deck_url: str | None
    pdp_request_deck_url: str | None
    keyword_insights_url: str | None
    photography_url: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


ContentProgramDetail = ContentPortfolioRow


@dataclass(slots=True)
class ContentSkuGroupRecord:
    id: str
    content_program_id: str
    group_name: str
    brand_name: str | None = None
    expected_sku_count: int | None = None
    graphics_per_sku: int | None = None
    status: str | None = None
    latest_update: str | None = None
    waiting_on: str | None = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.group_name = require_text(self.group_name, "group_name")


@dataclass(slots=True)
class ContentSkuRecord:
    id: str
    content_program_id: str
    product_name: str
    sku_group_id: str | None = None
    sku_code: str | None = None
    retailer_sku: str | None = None
    upc: str | None = None
    variant: str | None = None
    content_status: str | None = None
    copy_status: str | None = None
    attribute_status: str | None = None
    graphics_status: str | None = None
    submission_status: str | None = None
    publication_status: str | None = None
    live_url: str | None = None
    last_checked_at: datetime | None = None
    issue_status: str | None = None
    waiting_on: str | None = None
    maintenance_required: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.product_name = require_text(self.product_name, "product_name")


@dataclass(slots=True)
class ContentDeliverableRecord:
    id: str
    content_program_id: str
    deliverable_name: str
    sku_group_id: str | None = None
    sku_id: str | None = None
    deliverable_type: str | None = None
    status: str | None = None
    approval_status: str | None = None
    due_date: date | None = None
    delivered_date: date | None = None
    approved_date: date | None = None
    required_quantity: int | None = None
    completed_quantity: int | None = None
    waiting_on: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.deliverable_name = require_text(self.deliverable_name, "deliverable_name")


@dataclass(slots=True)
class ContentSubmissionRecord:
    id: str
    content_program_id: str
    sku_group_id: str | None = None
    sku_id: str | None = None
    retailer_or_platform: str | None = None
    submission_type: str | None = None
    status: str | None = None
    submitted_date: date | None = None
    approved_date: date | None = None
    published_date: date | None = None
    expected_live_date: date | None = None
    live_url: str | None = None
    issue_text: str | None = None
    waiting_on: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class ContentMonitoringUpdateRecord:
    id: str
    content_program_id: str
    update_date: date
    update_text: str
    sku_group_id: str | None = None
    sku_id: str | None = None
    update_type: str | None = None
    live_review_count: int | None = None
    publication_state: str | None = None
    created_by_user_id: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.update_text = require_text(self.update_text, "update_text")


@dataclass(slots=True)
class ContentInvoiceCheckpointRecord:
    id: str
    content_program_id: str
    checkpoint_name: str
    invoice_date: date | None = None
    due_date: date | None = None
    status: str | None = None
    amount: float | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.checkpoint_name = require_text(self.checkpoint_name, "checkpoint_name")


@dataclass(slots=True)
class InfluencerCampaignRecord:
    id: str
    program_id: str
    campaign_title: str
    workstream_id: str | None = None
    manager_user_id: str | None = None
    influencer_stage: str = "planning"
    planning_status: str | None = None
    latest_update: str | None = None
    waiting_on: str | None = None
    is_on_hold: bool = False
    hold_reason: str | None = None
    application_open_date: date | None = None
    application_close_date: date | None = None
    influencer_approval_due_date: date | None = None
    scripts_due_date: date | None = None
    first_content_due_date: date | None = None
    launch_date: date | None = None
    wrap_date: date | None = None
    invoice_date: date | None = None
    invoice_status: str | None = None
    invoice_amount: float | None = None
    target_creator_count: int | None = None
    approved_creator_count: int | None = None
    contracted_creator_count: int | None = None
    is_active: bool = True
    created_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.campaign_title = require_text(self.campaign_title, "campaign_title")


@dataclass(slots=True)
class InfluencerPlanningPortfolioRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workstream_id: str | None
    campaign_title: str
    manager_user_id: str | None
    manager_display_name: str | None
    influencer_stage: str
    planning_status: str | None
    latest_update: str | None
    waiting_on: str | None
    is_on_hold: bool
    hold_reason: str | None
    application_open_date: date | None
    application_close_date: date | None
    influencer_approval_due_date: date | None
    scripts_due_date: date | None
    first_content_due_date: date | None
    launch_date: date | None
    wrap_date: date | None
    invoice_date: date | None
    invoice_status: str | None
    invoice_amount: float | None
    target_creator_count: int | None
    approved_creator_count: int | None
    contracted_creator_count: int | None
    applicants_count: int | None
    vetted_count: int | None
    submitted_for_approval_count: int | None
    content_submitted_count: int | None
    content_approved_count: int | None
    creator_summary_notes: str | None
    program_status: str
    program_risk: str
    next_planning_step: str | None
    next_planning_step_due_date: date | None
    track_sheet_url: str | None
    influencer_brief_url: str | None
    bitly_link_url: str | None
    invoice_url: str | None
    eop_survey_url: str | None
    influencer_education_url: str | None
    campaign_brief_url: str | None
    click2cart_link_url: str | None
    content_folder_url: str | None
    application_link_url: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


InfluencerCampaignDetail = InfluencerPlanningPortfolioRow


@dataclass(slots=True)
class InfluencerPlanningStepRecord:
    id: str
    influencer_campaign_id: str
    step_title: str
    step_type: str | None = None
    step_description: str | None = None
    sequence_order: int = 0
    responsible_party: str | None = None
    assigned_user_id: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    completed_date: date | None = None
    status: str | None = None
    hard_deadline: bool = False
    waiting_on: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.step_title = require_text(self.step_title, "step_title")


@dataclass(slots=True)
class InfluencerApprovalRoundRecord:
    id: str
    influencer_campaign_id: str
    approval_type: str
    round_number: int = 1
    approval_scope: str | None = None
    requested_date: date | None = None
    feedback_due_date: date | None = None
    feedback_received_date: date | None = None
    approved_date: date | None = None
    status: str | None = None
    waiting_on: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.approval_type = require_text(self.approval_type, "approval_type")


@dataclass(slots=True)
class InfluencerContentRoundRecord:
    id: str
    influencer_campaign_id: str
    round_number: int
    content_type: str | None = None
    internal_review_due_date: date | None = None
    client_review_sent_date: date | None = None
    client_feedback_due_date: date | None = None
    feedback_received_date: date | None = None
    resubmission_due_date: date | None = None
    approved_date: date | None = None
    status: str | None = None
    waiting_on: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class InfluencerCreatorSummaryRecord:
    id: str
    influencer_campaign_id: str
    target_creator_count: int | None = None
    applicants_count: int | None = None
    vetted_count: int | None = None
    submitted_for_approval_count: int | None = None
    approved_count: int | None = None
    contracted_count: int | None = None
    content_submitted_count: int | None = None
    content_approved_count: int | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class InfluencerLivePortfolioRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workstream_id: str | None
    campaign_title: str
    manager_user_id: str | None
    manager_display_name: str | None
    influencer_stage: str
    live_status: str | None
    planning_status: str | None
    latest_update: str | None
    waiting_on: str | None
    is_on_hold: bool
    hold_reason: str | None
    planned_creator_count: int | None
    live_creator_count: int
    completed_creator_count: int
    active_wave_count: int
    next_go_live_date: date | None
    paid_live_end_date: date | None
    open_exception_count: int
    highlighted_exception_count: int
    launch_date: date | None
    wrap_date: date | None
    invoice_date: date | None
    invoice_status: str | None
    invoice_amount: float | None
    program_status: str
    program_risk: str
    next_checkpoint: str | None
    next_checkpoint_due_date: date | None
    track_sheet_url: str | None
    influencer_brief_url: str | None
    eop_survey_url: str | None
    invoice_url: str | None
    bitly_link_url: str | None
    click2cart_link_url: str | None
    client_facing_live_doc_url: str | None
    daily_impressions_url: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class InfluencerLiveCheckpointRecord:
    id: str
    influencer_campaign_id: str
    checkpoint_title: str
    checkpoint_type: str | None = None
    checkpoint_description: str | None = None
    sequence_order: int = 0
    responsible_party: str | None = None
    assigned_user_id: str | None = None
    start_date: date | None = None
    due_date: date | None = None
    completed_date: date | None = None
    status: str | None = None
    hard_deadline: bool = False
    waiting_on: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.checkpoint_title = require_text(self.checkpoint_title, "checkpoint_title")


@dataclass(slots=True)
class InfluencerCreatorWaveRecord:
    id: str
    influencer_campaign_id: str
    wave_number: int
    wave_name: str | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    planned_creator_count: int | None = None
    live_creator_count: int | None = None
    completed_creator_count: int | None = None
    status: str | None = None
    waiting_on: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class InfluencerLiveCreatorRecord:
    id: str
    influencer_campaign_id: str
    creator_name: str
    wave_id: str | None = None
    creator_handle: str | None = None
    platform: str | None = None
    live_status: str | None = None
    draft_status: str | None = None
    approval_status: str | None = None
    scheduled_live_date: date | None = None
    actual_live_date: date | None = None
    paid_live_end_date: date | None = None
    content_url: str | None = None
    click2cart_url: str | None = None
    retailer_url: str | None = None
    impressions_reporting_required: bool = False
    latest_impressions: int | None = None
    last_impressions_update_date: date | None = None
    waiting_on: str | None = None
    exception_status: str | None = None
    exception_notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.creator_name = require_text(self.creator_name, "creator_name")


@dataclass(slots=True)
class InfluencerLiveExceptionRecord:
    id: str
    influencer_campaign_id: str
    exception_title: str
    live_creator_id: str | None = None
    exception_type: str | None = None
    description: str | None = None
    status: str | None = None
    owner_user_id: str | None = None
    opened_date: date | None = None
    due_date: date | None = None
    resolved_date: date | None = None
    resolution_notes: str | None = None
    is_highlighted: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.exception_title = require_text(self.exception_title, "exception_title")


@dataclass(slots=True)
class InfluencerLiveWorkspaceSummary:
    campaign: InfluencerLivePortfolioRow
    planning_steps: list[InfluencerPlanningStepRecord]
    approval_rounds: list[InfluencerApprovalRoundRecord]
    content_rounds: list[InfluencerContentRoundRecord]
    creator_summary: InfluencerCreatorSummaryRecord | None
    checkpoints: list[InfluencerLiveCheckpointRecord]
    waves: list[InfluencerCreatorWaveRecord]
    creators: list[InfluencerLiveCreatorRecord]
    exceptions: list[InfluencerLiveExceptionRecord]
    wrap_readiness: str


@dataclass(slots=True)
class InfluencerRecapRecord:
    id: str
    influencer_campaign_id: str
    recap_status: str | None = None
    latest_update: str | None = None
    waiting_on: str | None = None
    reporting_due_date: date | None = None
    draft_recap_due_date: date | None = None
    internal_review_date: date | None = None
    client_review_date: date | None = None
    client_recap_date: date | None = None
    recap_delivered_date: date | None = None
    final_close_date: date | None = None
    final_invoice_sent_date: date | None = None
    sales_lift_analysis_required: bool = False
    sales_lift_analysis_status: str | None = None
    final_performance_data_status: str | None = None
    creator_closeout_status: str | None = None
    eop_survey_status: str | None = None
    invoice_status: str | None = None
    financial_close_status: str | None = None
    lessons_learned: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class InfluencerRecapPortfolioRow:
    id: str
    program_id: str
    program_name: str
    client_name: str | None
    workstream_id: str | None
    campaign_title: str
    manager_user_id: str | None
    manager_display_name: str | None
    influencer_stage: str
    recap_record_id: str | None
    recap_status: str | None
    latest_update: str | None
    waiting_on: str | None
    all_creators_live: bool
    creator_closeout_status: str | None
    eop_survey_status: str | None
    final_performance_data_status: str | None
    sales_lift_analysis_required: bool
    sales_lift_analysis_status: str | None
    recap_deck_status: str | None
    client_recap_date: date | None
    invoice_status: str | None
    financial_close_status: str | None
    open_requirement_count: int
    launch_item_count: int
    open_exception_count: int
    total_creator_count: int
    live_creator_count: int
    completed_creator_count: int
    missing_final_links_count: int
    missing_final_impressions_count: int
    paid_live_incomplete_count: int
    program_status: str
    program_risk: str
    reporting_due_date: date | None
    next_checkpoint: str | None
    next_checkpoint_due_date: date | None
    track_sheet_url: str | None
    influencer_brief_url: str | None
    click2cart_link_url: str | None
    bitly_link_url: str | None
    invoice_url: str | None
    eop_survey_url: str | None
    live_content_tracker_url: str | None
    recap_deck_url: str | None
    final_performance_data_url: str | None
    sales_lift_analysis_url: str | None
    ready_to_close_state: str
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class InfluencerRecapCheckpointRecord:
    id: str
    influencer_campaign_id: str
    checkpoint_title: str
    checkpoint_type: str | None = None
    sequence_order: int = 0
    responsible_party: str | None = None
    assigned_user_id: str | None = None
    due_date: date | None = None
    completed_date: date | None = None
    status: str | None = None
    waiting_on: str | None = None
    notes: str | None = None
    hard_deadline: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.checkpoint_title = require_text(self.checkpoint_title, "checkpoint_title")


@dataclass(slots=True)
class InfluencerRecapRequirementRecord:
    id: str
    influencer_campaign_id: str
    requirement_type: str
    requirement_title: str
    status: str | None = None
    required: bool = True
    due_date: date | None = None
    received_date: date | None = None
    completed_date: date | None = None
    waiting_on: str | None = None
    resource_id: str | None = None
    reporting_request_id: str | None = None
    notes: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.requirement_type = require_text(self.requirement_type, "requirement_type")
        self.requirement_title = require_text(self.requirement_title, "requirement_title")


@dataclass(slots=True)
class InfluencerRecapLaunchItemRecord:
    id: str
    influencer_campaign_id: str
    product_name: str
    group_name: str | None = None
    retailer_name: str | None = None
    online_launch_date: date | None = None
    in_store_launch_date: date | None = None
    launch_status: str | None = None
    product_url: str | None = None
    retailer_url: str | None = None
    notes: str | None = None
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.product_name = require_text(self.product_name, "product_name")


@dataclass(slots=True)
class InfluencerCreatorCloseoutSummary:
    total_creators: int
    live_creators: int
    completed_creators: int
    missing_final_links: int
    missing_final_impressions: int
    open_creator_exceptions: int
    paid_live_incomplete: int
    creator_closeout_status: str | None = None


@dataclass(slots=True)
class InfluencerRecapWorkspaceSummary:
    campaign: InfluencerRecapPortfolioRow
    recap_record: InfluencerRecapRecord | None
    planning_steps: list[InfluencerPlanningStepRecord]
    approval_rounds: list[InfluencerApprovalRoundRecord]
    content_rounds: list[InfluencerContentRoundRecord]
    live_checkpoints: list[InfluencerLiveCheckpointRecord]
    waves: list[InfluencerCreatorWaveRecord]
    creators: list[InfluencerLiveCreatorRecord]
    exceptions: list[InfluencerLiveExceptionRecord]
    checkpoints: list[InfluencerRecapCheckpointRecord]
    requirements: list[InfluencerRecapRequirementRecord]
    launch_items: list[InfluencerRecapLaunchItemRecord]
    creator_closeout: InfluencerCreatorCloseoutSummary
    ready_to_close_state: str
