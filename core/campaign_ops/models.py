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
