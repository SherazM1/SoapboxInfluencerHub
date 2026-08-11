from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.campaign_ops.state import SESSION_KEYS, update_viewer_state
from app.pages import campaigns
from app.pages.campaigns import (
    format_initialization_result,
    render_initialization_control,
    viewer_can_initialize_in_setup,
)
from core.campaign_ops.db import (
    CampaignOpsSetupStatus,
    get_campaign_ops_database_url,
    get_campaign_ops_setup_status,
)
from core.campaign_ops.enums import (
    AssignmentRole,
    ProgramStatus,
    RiskLevel,
    TaskStatus,
    UserRole,
    WaitingOn,
    WorkstreamType,
)
from core.campaign_ops.exceptions import (
    CampaignOpsDatabaseError,
    CampaignOpsError,
    CampaignOpsNotFoundError,
    CampaignOpsPermissionError,
    CampaignOpsSetupRequiredError,
    CampaignOpsValidationError,
)
from core.campaign_ops.migrations import (
    CampaignOpsInitializationResult,
    MigrationResult,
    SeedResult,
    get_migration_names,
    initialize_campaign_ops_database,
    run_campaign_ops_migrations,
    verify_campaign_ops_seed_users,
)
from core.campaign_ops.models import (
    CampaignOpsUser,
    Client,
    ContentDeliverableRecord,
    ContentInvoiceCheckpointRecord,
    ContentMonitoringUpdateRecord,
    ContentPortfolioRow,
    ContentProgramRecord,
    ContentSkuGroupRecord,
    ContentSkuRecord,
    ContentSubmissionRecord,
    InfluencerApprovalRoundRecord,
    InfluencerCampaignRecord,
    InfluencerContentRoundRecord,
    InfluencerCreatorSummaryRecord,
    InfluencerCreatorWaveRecord,
    InfluencerLiveCheckpointRecord,
    InfluencerLiveCreatorRecord,
    InfluencerLiveExceptionRecord,
    InfluencerLivePortfolioRow,
    InfluencerPlanningPortfolioRow,
    InfluencerPlanningStepRecord,
    InfluencerRecapCheckpointRecord,
    InfluencerRecapLaunchItemRecord,
    InfluencerRecapPortfolioRow,
    InfluencerRecapRecord,
    InfluencerRecapRequirementRecord,
    InsightsObjectiveRecord,
    InsightsPortfolioRow,
    InsightsProjectRecord,
    Milestone,
    MilestoneListRow,
    NoteListRow,
    Program,
    ProgramAssignment,
    ProgramPortfolioRow,
    ProgramNote,
    ReportingRequestListRow,
    ReportingRequestRecord,
    RetailMediaActivationRecord,
    RetailMediaCampaignRecord,
    RetailMediaChannelRecord,
    RetailMediaCreativeRecord,
    RetailMediaOptimizationRecord,
    RetailMediaPortfolioRow,
    Resource,
    ResourceListRow,
    Workstream,
    Task,
    TaskListRow,
    TaskDependency,
)
from core.campaign_ops.permissions import (
    can_access_admin,
    can_archive_program,
    can_edit_program,
    can_view_program,
)
from core.campaign_ops.seed_data import get_seed_users
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.content_management import (
    CONTENT_STATUS_CLIENT_REVIEW,
    CONTENT_STATUS_LIVE,
    CONTENT_STATUS_READY_TO_SUBMIT,
)
from core.campaign_ops.influencer import (
    INFLUENCER_STAGE_PLANNING,
    INFLUENCER_STAGE_LIVE,
    INFLUENCER_STAGE_RECAPPING,
    LIVE_STATUS_LIVE,
    LIVE_STATUS_READY_TO_LAUNCH,
    PLANNING_STATUS_BRIEF_DEVELOPMENT,
    PLANNING_STATUS_INFLUENCER_LIST_REVIEW,
    PLANNING_STATUS_ON_HOLD,
    STANDARD_PLANNING_TEMPLATE,
    STANDARD_LIVE_CHECKPOINT_TEMPLATE,
    RECAP_STATUS_READY_TO_RECAP,
    RECAP_STATUS_COLLECTING_DATA,
    RECAP_STATUS_READY_TO_CLOSE,
    RECAP_STATUS_COMPLETE,
    STANDARD_RECAP_CHECKLIST_TEMPLATE,
)
from core.campaign_ops.insights import INSIGHTS_STATUS_DRAFTING_SURVEY, INSIGHTS_STATUS_NOT_STARTED
from core.campaign_ops.retail_media import RETAIL_MEDIA_STATUS_LIVE, RETAIL_MEDIA_STATUS_PLANNING
from core.campaign_ops.reporting_requests import REQUEST_CATEGORY_REPORT, REQUEST_CATEGORY_SURVEY, normalize_am_name


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.rows: list[dict[str, str]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[str, ...] | None = None) -> None:
        normalized = " ".join(query.lower().split())
        if "raise failure" in normalized:
            raise RuntimeError("migration failed")
        if normalized.startswith("select version from schema_migrations"):
            self.rows = [{"version": version} for version in self.connection.applied_versions]
            return
        if normalized.startswith("select display_name, role from campaign_ops_users"):
            requested = set(params[0]) if params else set()
            self.rows = [
                {"display_name": user["display_name"], "role": user["role"]}
                for user in self.connection.users
                if user["display_name"] in requested and user.get("is_active", True)
            ]
            return
        if normalized.startswith("insert into schema_migrations") and params:
            self.connection.applied_versions.add(params[0])
            return
        if normalized.startswith("create table if not exists schema_migrations"):
            self.connection.bookkeeping_created = True
            return
        self.connection.executed_sql.append(query)

    def fetchall(self) -> list[dict[str, str]]:
        return self.rows

    def fetchone(self) -> dict[str, str] | None:
        return self.rows[0] if self.rows else None


class FakeTransaction:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "FakeTransaction":
        self.connection.transaction_count += 1
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.applied_versions: set[str] = set()
        self.executed_sql: list[str] = []
        self.bookkeeping_created = False
        self.commit_count = 0
        self.closed = False
        self.transaction_count = 0
        self.users: list[dict[str, str | bool]] = [
            {"display_name": "Bailey", "role": "administrator", "is_active": True},
            {"display_name": "T", "role": "team_member", "is_active": True},
            {"display_name": "L", "role": "team_member", "is_active": True},
        ]

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def commit(self) -> None:
        self.commit_count += 1

    def close(self) -> None:
        self.closed = True


class MissingTableCursor:
    def __enter__(self) -> "MissingTableCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _query: str, _params: tuple[str, ...] | None = None) -> None:
        raise RuntimeError("undefined table")


class MissingTableConnection:
    def cursor(self) -> MissingTableCursor:
        return MissingTableCursor()

    def close(self) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def create_program(self, program_name: str, actor_user_id: str | None = None, **_kwargs: object) -> Program:
        return Program(
            id="program-1",
            program_name=program_name,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )

    def append_event(self, **kwargs: str) -> None:
        self.events.append(kwargs)


class FakePrompt4ARepository:
    def __init__(self) -> None:
        self.users = [
            CampaignOpsUser(id="11111111-1111-4111-8111-111111111111", display_name="Bailey", role="administrator"),
            CampaignOpsUser(id="22222222-2222-4222-8222-222222222222", display_name="T", role="team_member"),
            CampaignOpsUser(id="33333333-3333-4333-8333-333333333333", display_name="L", role="team_member"),
            CampaignOpsUser(id="44444444-4444-4444-8444-444444444444", display_name="Inactive", role="team_member", is_active=False),
        ]
        self.clients: list[Client] = []
        self.programs: list[Program] = []
        self.workstreams: list[Workstream] = []
        self.assignments: list[ProgramAssignment] = []
        self.tasks: list[Task] = []
        self.milestones: list[Milestone] = []
        self.resources: list[Resource] = []
        self.notes: list[ProgramNote] = []
        self.reporting_requests: list[ReportingRequestRecord] = []
        self.insights_projects: list[InsightsProjectRecord] = []
        self.insights_objectives: list[InsightsObjectiveRecord] = []
        self.retail_media_campaigns: list[RetailMediaCampaignRecord] = []
        self.retail_media_channels: list[RetailMediaChannelRecord] = []
        self.retail_media_activations: list[RetailMediaActivationRecord] = []
        self.retail_media_creative: list[RetailMediaCreativeRecord] = []
        self.retail_media_optimizations: list[RetailMediaOptimizationRecord] = []
        self.content_programs: list[ContentProgramRecord] = []
        self.content_sku_groups: list[ContentSkuGroupRecord] = []
        self.content_skus: list[ContentSkuRecord] = []
        self.content_deliverables: list[ContentDeliverableRecord] = []
        self.content_submissions: list[ContentSubmissionRecord] = []
        self.content_monitoring_updates: list[ContentMonitoringUpdateRecord] = []
        self.content_invoice_checkpoints: list[ContentInvoiceCheckpointRecord] = []
        self.influencer_campaigns: list[InfluencerCampaignRecord] = []
        self.influencer_planning_steps: list[InfluencerPlanningStepRecord] = []
        self.influencer_approval_rounds: list[InfluencerApprovalRoundRecord] = []
        self.influencer_content_rounds: list[InfluencerContentRoundRecord] = []
        self.influencer_creator_summaries: list[InfluencerCreatorSummaryRecord] = []
        self.influencer_live_checkpoints: list[InfluencerLiveCheckpointRecord] = []
        self.influencer_creator_waves: list[InfluencerCreatorWaveRecord] = []
        self.influencer_live_creators: list[InfluencerLiveCreatorRecord] = []
        self.influencer_live_exceptions: list[InfluencerLiveExceptionRecord] = []
        self.influencer_recap_records: list[InfluencerRecapRecord] = []
        self.influencer_recap_checkpoints: list[InfluencerRecapCheckpointRecord] = []
        self.influencer_recap_requirements: list[InfluencerRecapRequirementRecord] = []
        self.influencer_recap_launch_items: list[InfluencerRecapLaunchItemRecord] = []
        self.events: list[dict[str, str | None]] = []
        self.last_portfolio_filters: dict[str, object] = {}

    def list_active_users(self) -> list[CampaignOpsUser]:
        return [user for user in self.users if user.is_active]

    def list_active_clients(self) -> list[Client]:
        return [client for client in self.clients if client.is_active]

    def get_user_by_id(self, user_id: str) -> CampaignOpsUser | None:
        return next((user for user in self.users if user.id == user_id), None)

    def get_user_by_display_name(self, display_name: str) -> CampaignOpsUser | None:
        return next((user for user in self.users if user.is_active and user.display_name.lower() == display_name.lower()), None)

    def get_client(self, client_id: str) -> Client | None:
        return next((client for client in self.clients if client.id == client_id), None)

    def get_client_by_normalized_name(self, name: str) -> Client | None:
        return next((client for client in self.clients if client.is_active and client.name.lower() == name.lower()), None)

    def create_client(self, name: str, actor_user_id: str | None = None) -> Client:
        client = Client(id=f"aaaaaaaa-aaaa-4aaa-8aaa-{len(self.clients) + 1:012d}", name=name, created_by=actor_user_id, updated_by=actor_user_id)
        self.clients.append(client)
        return client

    def create_program(self, program_name: str, actor_user_id: str | None = None, **kwargs: object) -> Program:
        program = Program(id=f"bbbbbbbb-bbbb-4bbb-8bbb-{len(self.programs) + 1:012d}", program_name=program_name, created_by=actor_user_id, updated_by=actor_user_id, **kwargs)
        self.programs.append(program)
        return program

    def update_program(self, program_id: str, actor_user_id: str | None = None, **kwargs: object) -> Program:
        program = self.get_program(program_id)
        if program is None:
            raise CampaignOpsNotFoundError("Program was not found.")
        for key, value in kwargs.items():
            setattr(program, key, value)
        program.updated_by = actor_user_id
        return program

    def archive_program(self, program_id: str, actor_user_id: str | None = None) -> Program:
        program = self.get_program(program_id)
        if program is None:
            raise CampaignOpsNotFoundError("Program was not found.")
        program.is_active = False
        program.status = ProgramStatus.ARCHIVED.value
        program.updated_by = actor_user_id
        return program

    def reactivate_program(self, program_id: str, actor_user_id: str | None = None) -> Program:
        program = self.get_program(program_id)
        if program is None:
            raise CampaignOpsNotFoundError("Program was not found.")
        program.is_active = True
        program.status = ProgramStatus.ACTIVE.value
        program.updated_by = actor_user_id
        return program

    def create_workstream(self, program_id: str, workstream_type: str, actor_user_id: str | None = None, **kwargs: object) -> Workstream:
        if any(workstream.program_id == program_id and workstream.workstream_type == workstream_type and workstream.is_active for workstream in self.workstreams):
            raise CampaignOpsValidationError("Duplicate active workstreams are not allowed.")
        workstream = Workstream(id=f"cccccccc-cccc-4ccc-8ccc-{len(self.workstreams) + 1:012d}", program_id=program_id, workstream_type=workstream_type, created_by=actor_user_id, updated_by=actor_user_id, **kwargs)
        self.workstreams.append(workstream)
        return workstream

    def get_workstream(self, workstream_id: str) -> Workstream | None:
        return next((workstream for workstream in self.workstreams if workstream.id == workstream_id), None)

    def update_workstream(self, workstream_id: str, actor_user_id: str | None = None, **kwargs: object) -> Workstream:
        workstream = self.get_workstream(workstream_id)
        if workstream is None:
            raise CampaignOpsNotFoundError("Workstream was not found.")
        for key, value in kwargs.items():
            setattr(workstream, key, value)
        workstream.updated_by = actor_user_id
        return workstream

    def deactivate_workstream(self, workstream_id: str, actor_user_id: str | None = None) -> None:
        workstream = self.get_workstream(workstream_id)
        if workstream is None:
            raise CampaignOpsNotFoundError("Workstream was not found.")
        workstream.is_active = False
        workstream.updated_by = actor_user_id

    def reactivate_workstream(self, workstream_id: str, actor_user_id: str | None = None) -> Workstream:
        workstream = self.get_workstream(workstream_id)
        if workstream is None:
            raise CampaignOpsNotFoundError("Workstream was not found.")
        workstream.is_active = True
        workstream.updated_by = actor_user_id
        return workstream

    def create_assignment(self, program_id: str, user_id: str, assignment_role: str, actor_user_id: str | None = None, workstream_id: str | None = None, is_primary: bool = False) -> ProgramAssignment:
        if any(assignment.program_id == program_id and assignment.workstream_id == workstream_id and assignment.user_id == user_id and assignment.assignment_role == assignment_role and assignment.is_active for assignment in self.assignments):
            raise CampaignOpsValidationError("Duplicate assignment is not allowed.")
        assignment = ProgramAssignment(id=f"dddddddd-dddd-4ddd-8ddd-{len(self.assignments) + 1:012d}", program_id=program_id, workstream_id=workstream_id, user_id=user_id, assignment_role=assignment_role, is_primary=is_primary, created_by=actor_user_id, updated_by=actor_user_id)
        self.assignments.append(assignment)
        return assignment

    def get_assignment(self, assignment_id: str) -> ProgramAssignment | None:
        return next((assignment for assignment in self.assignments if assignment.id == assignment_id), None)

    def update_assignment(self, assignment_id: str, actor_user_id: str | None = None, **kwargs: object) -> ProgramAssignment:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            raise CampaignOpsNotFoundError("Assignment was not found.")
        for key, value in kwargs.items():
            setattr(assignment, key, value)
        assignment.updated_by = actor_user_id
        return assignment

    def deactivate_assignment(self, assignment_id: str, actor_user_id: str | None = None) -> None:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            raise CampaignOpsNotFoundError("Assignment was not found.")
        assignment.is_active = False
        assignment.updated_by = actor_user_id

    def reactivate_assignment(self, assignment_id: str, actor_user_id: str | None = None) -> ProgramAssignment:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            raise CampaignOpsNotFoundError("Assignment was not found.")
        assignment.is_active = True
        assignment.updated_by = actor_user_id
        return assignment

    def create_task(self, program_id: str, title: str, actor_user_id: str | None = None, **kwargs: object) -> Task:
        task = Task(
            id=f"eeeeeeee-eeee-4eee-8eee-{len(self.tasks) + 1:012d}",
            program_id=program_id,
            title=title,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            **kwargs,
        )
        self.tasks.append(task)
        return task

    def get_task(self, task_id: str) -> Task | None:
        return next((task for task in self.tasks if task.id == task_id), None)

    def update_task_details(self, task_id: str, actor_user_id: str | None = None, **kwargs: object) -> Task:
        task = self.get_task(task_id)
        if task is None or not task.is_active:
            raise CampaignOpsNotFoundError("Task was not found.")
        for key, value in kwargs.items():
            setattr(task, key, value)
        task.updated_by = actor_user_id
        return task

    def deactivate_task(self, task_id: str, actor_user_id: str | None = None) -> None:
        task = self.get_task(task_id)
        if task is None or not task.is_active:
            raise CampaignOpsNotFoundError("Task was not found.")
        task.is_active = False
        task.updated_by = actor_user_id

    def reactivate_task(self, task_id: str, actor_user_id: str | None = None) -> Task:
        task = self.get_task(task_id)
        if task is None or task.is_active:
            raise CampaignOpsNotFoundError("Task was not found.")
        task.is_active = True
        task.updated_by = actor_user_id
        return task

    def create_milestone(self, program_id: str, title: str, actor_user_id: str | None = None, **kwargs: object) -> Milestone:
        milestone = Milestone(
            id=f"ffffffff-ffff-4fff-8fff-{len(self.milestones) + 1:012d}",
            program_id=program_id,
            title=title,
            status=str(kwargs.pop("status", TaskStatus.NOT_STARTED.value)),
            created_by=actor_user_id,
            updated_by=actor_user_id,
            **kwargs,
        )
        self.milestones.append(milestone)
        return milestone

    def get_milestone(self, milestone_id: str) -> Milestone | None:
        return next((milestone for milestone in self.milestones if milestone.id == milestone_id), None)

    def update_milestone(self, milestone_id: str, actor_user_id: str | None = None, **kwargs: object) -> Milestone:
        milestone = self.get_milestone(milestone_id)
        if milestone is None:
            raise CampaignOpsNotFoundError("Milestone was not found.")
        for key, value in kwargs.items():
            setattr(milestone, key, value)
        milestone.updated_by = actor_user_id
        return milestone

    def deactivate_milestone(self, milestone_id: str, actor_user_id: str | None = None) -> None:
        milestone = self.get_milestone(milestone_id)
        if milestone is None or not milestone.is_active:
            raise CampaignOpsNotFoundError("Milestone was not found.")
        milestone.is_active = False
        milestone.updated_by = actor_user_id

    def reactivate_milestone(self, milestone_id: str, actor_user_id: str | None = None) -> Milestone:
        milestone = self.get_milestone(milestone_id)
        if milestone is None or milestone.is_active:
            raise CampaignOpsNotFoundError("Milestone was not found.")
        milestone.is_active = True
        milestone.updated_by = actor_user_id
        return milestone

    def list_milestone_rows_by_program(self, program_id: str, include_inactive: bool = False) -> list[MilestoneListRow]:
        rows: list[MilestoneListRow] = []
        for milestone in self.milestones:
            if milestone.program_id != program_id or (not include_inactive and not milestone.is_active):
                continue
            workstream = self.get_workstream(milestone.workstream_id) if milestone.workstream_id else None
            owner = self.get_user_by_id(milestone.owner_user_id) if milestone.owner_user_id else None
            rows.append(MilestoneListRow(
                id=milestone.id,
                program_id=milestone.program_id,
                title=milestone.title,
                status=milestone.status,
                workstream_id=milestone.workstream_id,
                workstream_type=workstream.workstream_type if workstream else None,
                milestone_type=milestone.milestone_type,
                target_date=milestone.target_date,
                start_date=milestone.start_date,
                end_date=milestone.end_date,
                owner_user_id=milestone.owner_user_id,
                owner_user_name=owner.display_name if owner else None,
                hard_deadline=milestone.hard_deadline,
                completed_at=milestone.completed_at,
                is_highlighted=milestone.is_highlighted,
                is_active=milestone.is_active,
                created_at=milestone.created_at,
                updated_at=milestone.updated_at,
            ))
        return rows

    def create_resource(self, program_id: str, resource_type: str, title: str, actor_user_id: str | None = None, **kwargs: object) -> Resource:
        resource = Resource(
            id=f"99999999-9999-4999-8999-{len(self.resources) + 1:012d}",
            program_id=program_id,
            resource_type=resource_type,
            title=title,
            created_by=actor_user_id,
            updated_by=actor_user_id,
            **kwargs,
        )
        self.resources.append(resource)
        return resource

    def get_resource(self, resource_id: str) -> Resource | None:
        return next((resource for resource in self.resources if resource.id == resource_id), None)

    def update_resource(self, resource_id: str, actor_user_id: str | None = None, **kwargs: object) -> Resource:
        resource = self.get_resource(resource_id)
        if resource is None:
            raise CampaignOpsNotFoundError("Resource was not found.")
        for key, value in kwargs.items():
            setattr(resource, key, value)
        resource.updated_by = actor_user_id
        return resource

    def deactivate_resource(self, resource_id: str, actor_user_id: str | None = None) -> None:
        resource = self.get_resource(resource_id)
        if resource is None or not resource.is_active:
            raise CampaignOpsNotFoundError("Resource was not found.")
        resource.is_active = False
        resource.updated_by = actor_user_id

    def reactivate_resource(self, resource_id: str, actor_user_id: str | None = None) -> Resource:
        resource = self.get_resource(resource_id)
        if resource is None or resource.is_active:
            raise CampaignOpsNotFoundError("Resource was not found.")
        resource.is_active = True
        resource.updated_by = actor_user_id
        return resource

    def list_resource_rows_by_program(self, program_id: str, include_inactive: bool = False) -> list[ResourceListRow]:
        rows: list[ResourceListRow] = []
        for resource in self.resources:
            if resource.program_id != program_id or (not include_inactive and not resource.is_active):
                continue
            workstream = self.get_workstream(resource.workstream_id) if resource.workstream_id else None
            rows.append(ResourceListRow(
                id=resource.id,
                program_id=resource.program_id,
                title=resource.title,
                resource_type=resource.resource_type,
                workstream_id=resource.workstream_id,
                workstream_type=workstream.workstream_type if workstream else None,
                url=resource.url,
                notes=resource.notes,
                is_required=resource.is_required,
                is_active=resource.is_active,
                created_at=resource.created_at,
                updated_at=resource.updated_at,
            ))
        return rows

    def list_resources_for_programs(self, program_ids: list[str], include_inactive: bool = False) -> dict[str, list[Resource]]:
        return {
            program_id: [resource for resource in self.resources if resource.program_id == program_id and (include_inactive or resource.is_active)]
            for program_id in program_ids
        }

    def append_note(self, program_id: str, note_text: str, author_user_id: str | None = None, **kwargs: object) -> ProgramNote:
        note = ProgramNote(
            id=f"88888888-8888-4888-8888-{len(self.notes) + 1:012d}",
            program_id=program_id,
            note_text=note_text,
            author_user_id=author_user_id,
            **kwargs,
        )
        self.notes.append(note)
        return note

    def list_note_rows_by_program(self, program_id: str, include_internal: bool = True, newest_first: bool = True, limit: int = 100) -> list[NoteListRow]:
        rows: list[NoteListRow] = []
        for note in self.notes:
            if note.program_id != program_id or (note.is_internal and not include_internal):
                continue
            workstream = self.get_workstream(note.workstream_id) if note.workstream_id else None
            task = self.get_task(note.task_id) if note.task_id else None
            author = self.get_user_by_id(note.author_user_id) if note.author_user_id else None
            rows.append(NoteListRow(
                id=note.id,
                program_id=note.program_id,
                workstream_id=note.workstream_id,
                workstream_type=workstream.workstream_type if workstream else None,
                task_id=note.task_id,
                task_title=task.title if task else None,
                author_user_id=note.author_user_id,
                author_display_name=author.display_name if author else None,
                note_text=note.note_text,
                note_type=note.note_type,
                is_internal=note.is_internal,
                created_at=note.created_at,
            ))
        ordered = list(reversed(rows)) if newest_first else rows
        return ordered[:limit]

    def create_reporting_request(self, actor_user_id: str | None = None, **kwargs: object) -> ReportingRequestRecord:
        request = ReportingRequestRecord(
            id=f"77777777-7777-4777-8777-{len(self.reporting_requests) + 1:012d}",
            created_by_user_id=actor_user_id,
            **kwargs,
        )
        self.reporting_requests.append(request)
        return request

    def get_reporting_request(self, request_id: str) -> ReportingRequestRecord | None:
        return next((request for request in self.reporting_requests if request.id == request_id), None)

    def update_reporting_request(self, request_id: str, actor_user_id: str | None = None, **kwargs: object) -> ReportingRequestRecord:
        request = self.get_reporting_request(request_id)
        if request is None:
            raise CampaignOpsNotFoundError("Reporting request was not found.")
        for key, value in kwargs.items():
            setattr(request, key, value)
        return request

    def deactivate_reporting_request(self, request_id: str) -> None:
        request = self.get_reporting_request(request_id)
        if request is None or not request.is_active:
            raise CampaignOpsNotFoundError("Reporting request was not found.")
        request.is_active = False

    def reactivate_reporting_request(self, request_id: str) -> ReportingRequestRecord:
        request = self.get_reporting_request(request_id)
        if request is None or request.is_active:
            raise CampaignOpsNotFoundError("Reporting request was not found.")
        request.is_active = True
        return request

    def _reporting_request_row(self, request: ReportingRequestRecord) -> ReportingRequestListRow:
        program = self.get_program(request.program_id)
        client = self.get_program_client(request.program_id)
        workstream = self.get_workstream(request.workstream_id) if request.workstream_id else None
        am = self.get_user_by_id(request.am_user_id)
        assigned = self.get_user_by_id(request.assigned_user_id) if request.assigned_user_id else None
        return ReportingRequestListRow(
            id=request.id,
            program_id=request.program_id,
            program_name=program.program_name if program else "",
            client_name=client.name if client else None,
            primary_workstream_type=program.primary_workstream_type if program else None,
            request_category=request.request_category,
            request_type=request.request_type,
            am_user_id=request.am_user_id,
            am_display_name=am.display_name if am else "",
            assigned_user_id=request.assigned_user_id,
            assigned_display_name=assigned.display_name if assigned else None,
            workstream_id=request.workstream_id,
            workstream_type=workstream.workstream_type if workstream else None,
            due_date=request.due_date,
            recap_date_with_client=request.recap_date_with_client,
            recap_date_text=request.recap_date_text,
            brief_url=request.brief_url,
            brief_status_text=request.brief_status_text,
            delivered=request.delivered,
            review_required=request.review_required,
            review_complete=request.review_complete,
            approval_required=request.approval_required,
            approved=request.approved,
            questions_requested=request.questions_requested,
            special_requests=request.special_requests,
            status=request.status,
            risk=request.risk,
            waiting_on=request.waiting_on,
            completed_at=request.completed_at,
            is_active=request.is_active,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

    def list_reporting_requests(self, include_inactive: bool = False, program_id: str | None = None) -> list[ReportingRequestListRow]:
        rows = [
            self._reporting_request_row(request)
            for request in self.reporting_requests
            if (include_inactive or request.is_active) and (program_id is None or request.program_id == program_id)
        ]
        return rows

    def get_reporting_request_detail(self, request_id: str) -> ReportingRequestListRow | None:
        request = self.get_reporting_request(request_id)
        return self._reporting_request_row(request) if request else None

    def list_requests_by_program(self, program_id: str, include_inactive: bool = False) -> list[ReportingRequestListRow]:
        return self.list_reporting_requests(include_inactive=include_inactive, program_id=program_id)

    def create_insights_project(self, actor_user_id: str | None = None, **kwargs: object) -> InsightsProjectRecord:
        project = InsightsProjectRecord(
            id=f"66666666-6666-4666-8666-{len(self.insights_projects) + 1:012d}",
            created_by_user_id=actor_user_id,
            **kwargs,
        )
        self.insights_projects.append(project)
        return project

    def get_insights_project(self, project_id: str) -> InsightsProjectRecord | None:
        return next((project for project in self.insights_projects if project.id == project_id), None)

    def get_insights_project_by_program(self, program_id: str) -> InsightsProjectRecord | None:
        return next((project for project in self.insights_projects if project.program_id == program_id), None)

    def update_insights_project(self, project_id: str, **kwargs: object) -> InsightsProjectRecord:
        project = self.get_insights_project(project_id)
        if project is None:
            raise CampaignOpsNotFoundError("Insights project was not found.")
        for key, value in kwargs.items():
            setattr(project, key, value)
        return project

    def deactivate_insights_project(self, project_id: str) -> None:
        project = self.get_insights_project(project_id)
        if project is None or not project.is_active:
            raise CampaignOpsNotFoundError("Insights project was not found.")
        project.is_active = False

    def reactivate_insights_project(self, project_id: str) -> InsightsProjectRecord:
        project = self.get_insights_project(project_id)
        if project is None or project.is_active:
            raise CampaignOpsNotFoundError("Insights project was not found.")
        project.is_active = True
        return project

    def _insights_portfolio_row(self, project: InsightsProjectRecord) -> InsightsPortfolioRow:
        program = self.get_program(project.program_id)
        client = self.get_program_client(project.program_id)
        owner = self.get_user_by_id(project.owner_user_id) if project.owner_user_id else None
        active_milestones = [
            milestone
            for milestone in self.milestones
            if milestone.program_id == project.program_id
            and milestone.is_active
            and milestone.status != TaskStatus.COMPLETED.value
            and (milestone.workstream_id == project.workstream_id or milestone.milestone_type == "Insights")
        ]
        active_milestones.sort(key=lambda milestone: ((milestone.target_date or milestone.start_date or milestone.end_date) is None, milestone.target_date or milestone.start_date or milestone.end_date or date.max, milestone.title))
        next_milestone = active_milestones[0] if active_milestones else None
        resources = [resource for resource in self.resources if resource.program_id == project.program_id and resource.is_active]
        tracksheet = next((resource.url for resource in resources if resource.resource_type == "Tracksheet" and resource.url), None)
        results_deck = next((resource.url for resource in resources if resource.resource_type == "Results Deck" and resource.url), None)
        raw_data = next((resource.url for resource in resources if resource.resource_type in {"Raw Data", "Raw Data Key"} and resource.url), None)
        return InsightsPortfolioRow(
            id=project.id,
            program_id=project.program_id,
            program_name=program.program_name if program else "",
            client_name=client.name if client else None,
            workstream_id=project.workstream_id,
            project_title=project.project_title,
            job_number=project.job_number,
            insights_status=project.insights_status,
            latest_update=project.latest_update,
            owner_user_id=project.owner_user_id,
            owner_display_name=owner.display_name if owner else None,
            total_program_cost=project.total_program_cost,
            sample_size=project.sample_size,
            budget=project.budget,
            program_status=program.status if program else ProgramStatus.ACTIVE.value,
            program_risk=program.risk_level if program else RiskLevel.UNRATED.value,
            next_milestone=next_milestone.title if next_milestone else None,
            next_milestone_date=next_milestone.target_date if next_milestone else None,
            tracksheet_url=tracksheet,
            results_deck_url=results_deck,
            raw_data_url=raw_data,
            is_active=project.is_active,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )

    def list_insights_projects(self, include_inactive: bool = False) -> list[InsightsPortfolioRow]:
        return [
            self._insights_portfolio_row(project)
            for project in self.insights_projects
            if include_inactive or project.is_active
        ]

    def get_insights_project_detail(self, project_id: str) -> InsightsPortfolioRow | None:
        project = self.get_insights_project(project_id)
        return self._insights_portfolio_row(project) if project else None

    def create_insights_objective(self, insights_project_id: str, objective_text: str, actor_user_id: str | None = None, sort_order: int = 0) -> InsightsObjectiveRecord:
        objective = InsightsObjectiveRecord(
            id=f"55555555-5555-4555-8555-{len(self.insights_objectives) + 1:012d}",
            insights_project_id=insights_project_id,
            objective_text=objective_text,
            sort_order=sort_order,
            created_by_user_id=actor_user_id,
        )
        self.insights_objectives.append(objective)
        return objective

    def list_insights_objectives(self, insights_project_id: str, include_inactive: bool = False) -> list[InsightsObjectiveRecord]:
        rows = [
            objective
            for objective in self.insights_objectives
            if objective.insights_project_id == insights_project_id and (include_inactive or objective.is_active)
        ]
        return sorted(rows, key=lambda objective: (objective.sort_order, objective.created_at or datetime.min))

    def update_insights_objective(self, objective_id: str, objective_text: str, sort_order: int) -> InsightsObjectiveRecord:
        objective = next((item for item in self.insights_objectives if item.id == objective_id), None)
        if objective is None:
            raise CampaignOpsNotFoundError("Insights objective was not found.")
        objective.objective_text = objective_text
        objective.sort_order = sort_order
        return objective

    def deactivate_insights_objective(self, objective_id: str) -> None:
        objective = next((item for item in self.insights_objectives if item.id == objective_id), None)
        if objective is None or not objective.is_active:
            raise CampaignOpsNotFoundError("Insights objective was not found.")
        objective.is_active = False

    def reactivate_insights_objective(self, objective_id: str) -> InsightsObjectiveRecord:
        objective = next((item for item in self.insights_objectives if item.id == objective_id), None)
        if objective is None or objective.is_active:
            raise CampaignOpsNotFoundError("Insights objective was not found.")
        objective.is_active = True
        return objective

    def create_retail_media_campaign(self, actor_user_id: str | None = None, **kwargs: object) -> RetailMediaCampaignRecord:
        campaign = RetailMediaCampaignRecord(id=f"44444444-4444-4444-8444-{len(self.retail_media_campaigns) + 1:012d}", created_by_user_id=actor_user_id, **kwargs)
        self.retail_media_campaigns.append(campaign)
        return campaign

    def get_retail_media_campaign(self, campaign_id: str) -> RetailMediaCampaignRecord | None:
        return next((campaign for campaign in self.retail_media_campaigns if campaign.id == campaign_id), None)

    def get_active_retail_media_campaign_by_title(self, program_id: str, campaign_title: str) -> RetailMediaCampaignRecord | None:
        return next((campaign for campaign in self.retail_media_campaigns if campaign.program_id == program_id and campaign.is_active and campaign.campaign_title.lower() == campaign_title.lower()), None)

    def update_retail_media_campaign(self, campaign_id: str, **kwargs: object) -> RetailMediaCampaignRecord:
        campaign = self.get_retail_media_campaign(campaign_id)
        if campaign is None:
            raise CampaignOpsNotFoundError("Retail Media campaign was not found.")
        for key, value in kwargs.items():
            setattr(campaign, key, value)
        return campaign

    def deactivate_retail_media_campaign(self, campaign_id: str) -> None:
        campaign = self.get_retail_media_campaign(campaign_id)
        if campaign is None or not campaign.is_active:
            raise CampaignOpsNotFoundError("Retail Media campaign was not found.")
        campaign.is_active = False

    def reactivate_retail_media_campaign(self, campaign_id: str) -> RetailMediaCampaignRecord:
        campaign = self.get_retail_media_campaign(campaign_id)
        if campaign is None or campaign.is_active:
            raise CampaignOpsNotFoundError("Retail Media campaign was not found.")
        campaign.is_active = True
        return campaign

    def _retail_media_portfolio_row(self, campaign: RetailMediaCampaignRecord) -> RetailMediaPortfolioRow:
        program = self.get_program(campaign.program_id)
        client = self.get_program_client(campaign.program_id)
        owner = self.get_user_by_id(campaign.owner_user_id) if campaign.owner_user_id else None
        channels = [channel for channel in self.retail_media_channels if channel.retail_media_campaign_id == campaign.id and channel.is_active]
        milestones = [milestone for milestone in self.milestones if milestone.program_id == campaign.program_id and milestone.is_active and milestone.status != TaskStatus.COMPLETED.value and (milestone.workstream_id == campaign.workstream_id or milestone.milestone_type == "Retail Media")]
        milestones.sort(key=lambda milestone: ((milestone.target_date or milestone.start_date or milestone.end_date) is None, milestone.target_date or milestone.start_date or milestone.end_date or date.max, milestone.title))
        next_milestone = milestones[0] if milestones else None
        resources = [resource for resource in self.resources if resource.program_id == campaign.program_id and resource.is_active]
        return RetailMediaPortfolioRow(
            id=campaign.id,
            program_id=campaign.program_id,
            program_name=program.program_name if program else "",
            client_name=client.name if client else None,
            workstream_id=campaign.workstream_id,
            campaign_title=campaign.campaign_title,
            retail_media_status=campaign.retail_media_status,
            latest_update=campaign.latest_update,
            waiting_on=campaign.waiting_on,
            owner_user_id=campaign.owner_user_id,
            owner_display_name=owner.display_name if owner else None,
            launch_date=campaign.launch_date,
            wrap_date=campaign.wrap_date,
            reporting_cadence=campaign.reporting_cadence,
            overall_budget=campaign.overall_budget,
            total_spend=campaign.total_spend,
            channel_budget_total=sum(channel.budget or 0 for channel in channels),
            channel_spend_total=sum(channel.spend_to_date or 0 for channel in channels),
            channel_mix=[channel.channel_type for channel in sorted(channels, key=lambda item: item.channel_type)],
            program_status=program.status if program else ProgramStatus.ACTIVE.value,
            program_risk=program.risk_level if program else RiskLevel.UNRATED.value,
            next_milestone=next_milestone.title if next_milestone else None,
            next_milestone_date=next_milestone.target_date if next_milestone else None,
            tracksheet_url=next((resource.url for resource in resources if resource.resource_type in {"Tracksheet", "Program Tracksheet"} and resource.url), None),
            budget_tracker_url=next((resource.url for resource in resources if resource.resource_type == "Budget Tracker" and resource.url), None),
            optimization_log_url=next((resource.url for resource in resources if resource.resource_type == "Optimization Log" and resource.url), None),
            is_paused=campaign.is_paused,
            pause_reason=campaign.pause_reason,
            is_active=campaign.is_active,
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
        )

    def list_retail_media_campaigns(self, include_inactive: bool = False) -> list[RetailMediaPortfolioRow]:
        return [self._retail_media_portfolio_row(campaign) for campaign in self.retail_media_campaigns if include_inactive or campaign.is_active]

    def get_retail_media_campaign_detail(self, campaign_id: str) -> RetailMediaPortfolioRow | None:
        campaign = self.get_retail_media_campaign(campaign_id)
        return self._retail_media_portfolio_row(campaign) if campaign else None

    def create_retail_media_channel(self, retail_media_campaign_id: str, channel_type: str, **kwargs: object) -> RetailMediaChannelRecord:
        channel = RetailMediaChannelRecord(id=f"34343434-3434-4434-8434-{len(self.retail_media_channels) + 1:012d}", retail_media_campaign_id=retail_media_campaign_id, channel_type=channel_type, **kwargs)
        self.retail_media_channels.append(channel)
        return channel

    def list_retail_media_channels(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaChannelRecord]:
        return [channel for channel in self.retail_media_channels if channel.retail_media_campaign_id == retail_media_campaign_id and (include_inactive or channel.is_active)]

    def update_retail_media_channel(self, channel_id: str, **kwargs: object) -> RetailMediaChannelRecord:
        channel = next((item for item in self.retail_media_channels if item.id == channel_id), None)
        if channel is None:
            raise CampaignOpsNotFoundError("Retail Media channel was not found.")
        for key, value in kwargs.items():
            setattr(channel, key, value)
        return channel

    def deactivate_retail_media_channel(self, channel_id: str) -> None:
        self.update_retail_media_channel(channel_id, is_active=False)

    def reactivate_retail_media_channel(self, channel_id: str) -> RetailMediaChannelRecord:
        return self.update_retail_media_channel(channel_id, is_active=True)

    def create_retail_media_activation(self, retail_media_campaign_id: str, activation_name: str, **kwargs: object) -> RetailMediaActivationRecord:
        activation = RetailMediaActivationRecord(id=f"32323232-3232-4323-8323-{len(self.retail_media_activations) + 1:012d}", retail_media_campaign_id=retail_media_campaign_id, activation_name=activation_name, **kwargs)
        self.retail_media_activations.append(activation)
        return activation

    def list_retail_media_activations(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaActivationRecord]:
        return sorted([item for item in self.retail_media_activations if item.retail_media_campaign_id == retail_media_campaign_id and (include_inactive or item.is_active)], key=lambda item: (item.start_date or item.end_date or date.max, item.created_at or datetime.min))

    def update_retail_media_activation(self, activation_id: str, **kwargs: object) -> RetailMediaActivationRecord:
        activation = next((item for item in self.retail_media_activations if item.id == activation_id), None)
        if activation is None:
            raise CampaignOpsNotFoundError("Retail Media activation was not found.")
        for key, value in kwargs.items():
            setattr(activation, key, value)
        return activation

    def deactivate_retail_media_activation(self, activation_id: str) -> None:
        self.update_retail_media_activation(activation_id, is_active=False)

    def reactivate_retail_media_activation(self, activation_id: str) -> RetailMediaActivationRecord:
        return self.update_retail_media_activation(activation_id, is_active=True)

    def create_retail_media_creative(self, retail_media_campaign_id: str, creative_name: str, **kwargs: object) -> RetailMediaCreativeRecord:
        creative = RetailMediaCreativeRecord(id=f"31313131-3131-4313-8313-{len(self.retail_media_creative) + 1:012d}", retail_media_campaign_id=retail_media_campaign_id, creative_name=creative_name, **kwargs)
        self.retail_media_creative.append(creative)
        return creative

    def list_retail_media_creative(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaCreativeRecord]:
        return [item for item in self.retail_media_creative if item.retail_media_campaign_id == retail_media_campaign_id and (include_inactive or item.is_active)]

    def update_retail_media_creative(self, creative_id: str, **kwargs: object) -> RetailMediaCreativeRecord:
        creative = next((item for item in self.retail_media_creative if item.id == creative_id), None)
        if creative is None:
            raise CampaignOpsNotFoundError("Retail Media creative item was not found.")
        for key, value in kwargs.items():
            setattr(creative, key, value)
        return creative

    def deactivate_retail_media_creative(self, creative_id: str) -> None:
        self.update_retail_media_creative(creative_id, is_active=False)

    def reactivate_retail_media_creative(self, creative_id: str) -> RetailMediaCreativeRecord:
        return self.update_retail_media_creative(creative_id, is_active=True)

    def create_retail_media_optimization(self, retail_media_campaign_id: str, update_date: date, update_text: str, actor_user_id: str | None = None, **kwargs: object) -> RetailMediaOptimizationRecord:
        optimization = RetailMediaOptimizationRecord(id=f"30303030-3030-4303-8303-{len(self.retail_media_optimizations) + 1:012d}", retail_media_campaign_id=retail_media_campaign_id, update_date=update_date, update_text=update_text, created_by_user_id=actor_user_id, **kwargs)
        self.retail_media_optimizations.append(optimization)
        return optimization

    def list_retail_media_optimizations(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaOptimizationRecord]:
        return sorted([item for item in self.retail_media_optimizations if item.retail_media_campaign_id == retail_media_campaign_id and (include_inactive or item.is_active)], key=lambda item: (item.update_date, item.created_at or datetime.min), reverse=True)

    def update_retail_media_optimization(self, optimization_id: str, **kwargs: object) -> RetailMediaOptimizationRecord:
        optimization = next((item for item in self.retail_media_optimizations if item.id == optimization_id), None)
        if optimization is None:
            raise CampaignOpsNotFoundError("Retail Media optimization update was not found.")
        for key, value in kwargs.items():
            setattr(optimization, key, value)
        return optimization

    def deactivate_retail_media_optimization(self, optimization_id: str) -> None:
        self.update_retail_media_optimization(optimization_id, is_active=False)

    def reactivate_retail_media_optimization(self, optimization_id: str) -> RetailMediaOptimizationRecord:
        return self.update_retail_media_optimization(optimization_id, is_active=True)

    def create_content_program(self, actor_user_id: str | None = None, **kwargs: object) -> ContentProgramRecord:
        content = ContentProgramRecord(id=f"29292929-2929-4929-8929-{len(self.content_programs) + 1:012d}", created_by_user_id=actor_user_id, **kwargs)
        self.content_programs.append(content)
        return content

    def get_content_program(self, content_program_id: str) -> ContentProgramRecord | None:
        return next((item for item in self.content_programs if item.id == content_program_id), None)

    def get_active_content_program_by_title(self, program_id: str, content_program_title: str) -> ContentProgramRecord | None:
        return next((item for item in self.content_programs if item.program_id == program_id and item.is_active and item.content_program_title.lower() == content_program_title.lower()), None)

    def update_content_program(self, content_program_id: str, **kwargs: object) -> ContentProgramRecord:
        content = self.get_content_program(content_program_id)
        if content is None:
            raise CampaignOpsNotFoundError("Content Program was not found.")
        for key, value in kwargs.items():
            setattr(content, key, value)
        content.updated_at = datetime.now(UTC)
        return content

    def deactivate_content_program(self, content_program_id: str) -> None:
        self.update_content_program(content_program_id, is_active=False)

    def reactivate_content_program(self, content_program_id: str) -> ContentProgramRecord:
        return self.update_content_program(content_program_id, is_active=True)

    def _content_portfolio_row(self, content: ContentProgramRecord) -> ContentPortfolioRow:
        program = self.get_program(content.program_id)
        client = self.get_client(program.client_id) if program and program.client_id else None
        owner = self.get_user_by_id(content.owner_user_id) if content.owner_user_id else None
        groups = [group for group in self.content_sku_groups if group.content_program_id == content.id and group.is_active]
        skus = [sku for sku in self.content_skus if sku.content_program_id == content.id and sku.is_active]
        deliverables = [item for item in self.content_deliverables if item.content_program_id == content.id and item.is_active]
        milestones = [
            milestone
            for milestone in self.milestones
            if milestone.program_id == content.program_id
            and milestone.is_active
            and milestone.status != TaskStatus.COMPLETED.value
            and (milestone.workstream_id == content.workstream_id or milestone.milestone_type == "Content Management")
        ]
        milestones.sort(key=lambda item: item.target_date or item.start_date or date.max)
        resources = [resource for resource in self.resources if resource.program_id == content.program_id and resource.is_active]

        def resource_url(*types: str) -> str | None:
            wanted = {item.lower() for item in types}
            return next((resource.url for resource in resources if resource.url and resource.resource_type.lower() in wanted), None)

        return ContentPortfolioRow(
            id=content.id,
            program_id=content.program_id,
            program_name=program.program_name if program else "",
            client_name=client.name if client else None,
            workstream_id=content.workstream_id,
            content_program_title=content.content_program_title,
            content_status=content.content_status,
            latest_update=content.latest_update,
            waiting_on=content.waiting_on,
            owner_user_id=content.owner_user_id,
            owner_display_name=owner.display_name if owner else None,
            total_sku_count=content.total_sku_count,
            default_graphics_per_sku=content.default_graphics_per_sku,
            monitoring_start_date=content.monitoring_start_date,
            maintenance_end_date=content.maintenance_end_date,
            reporting_cadence=content.reporting_cadence,
            is_invoiced=content.is_invoiced,
            invoice_status=content.invoice_status,
            group_names=[group.group_name for group in groups],
            group_expected_sku_total=sum(group.expected_sku_count or 0 for group in groups) or None,
            active_sku_count=len(skus),
            delivered_count=len([item for item in deliverables if item.status in {"delivered", "approved", "complete"}]),
            live_count=len([sku for sku in skus if sku.publication_status == "live"]),
            issue_count=len([sku for sku in skus if sku.issue_status]),
            program_status=program.status if program else ProgramStatus.ACTIVE.value,
            program_risk=program.risk_level if program else RiskLevel.UNRATED.value,
            next_milestone=milestones[0].title if milestones else None,
            next_milestone_date=(milestones[0].target_date or milestones[0].start_date) if milestones else None,
            sku_list_url=resource_url("SKU List"),
            tracksheet_url=resource_url("Tracksheet"),
            creative_request_deck_url=resource_url("Creative Request Deck"),
            pdp_request_deck_url=resource_url("PDP Request Deck"),
            keyword_insights_url=resource_url("Keyword Insights"),
            photography_url=resource_url("Photography Folder", "Photography"),
            is_active=content.is_active,
            created_at=content.created_at,
            updated_at=content.updated_at,
        )

    def list_content_programs(self, include_inactive: bool = False) -> list[ContentPortfolioRow]:
        return [self._content_portfolio_row(item) for item in self.content_programs if include_inactive or item.is_active]

    def get_content_program_detail(self, content_program_id: str) -> ContentPortfolioRow | None:
        content = self.get_content_program(content_program_id)
        return self._content_portfolio_row(content) if content else None

    def create_content_sku_group(self, content_program_id: str, group_name: str, **kwargs: object) -> ContentSkuGroupRecord:
        group = ContentSkuGroupRecord(id=f"28282828-2828-4828-8828-{len(self.content_sku_groups) + 1:012d}", content_program_id=content_program_id, group_name=group_name, **kwargs)
        self.content_sku_groups.append(group)
        return group

    def list_content_sku_groups(self, content_program_id: str, include_inactive: bool = False) -> list[ContentSkuGroupRecord]:
        return sorted([item for item in self.content_sku_groups if item.content_program_id == content_program_id and (include_inactive or item.is_active)], key=lambda item: (item.sort_order, item.group_name))

    def update_content_sku_group(self, group_id: str, **kwargs: object) -> ContentSkuGroupRecord:
        group = next((item for item in self.content_sku_groups if item.id == group_id), None)
        if group is None:
            raise CampaignOpsNotFoundError("SKU Group was not found.")
        for key, value in kwargs.items():
            setattr(group, key, value)
        return group

    def deactivate_content_sku_group(self, group_id: str) -> None:
        self.update_content_sku_group(group_id, is_active=False)

    def reactivate_content_sku_group(self, group_id: str) -> ContentSkuGroupRecord:
        return self.update_content_sku_group(group_id, is_active=True)

    def create_content_sku(self, content_program_id: str, product_name: str, **kwargs: object) -> ContentSkuRecord:
        sku = ContentSkuRecord(id=f"27272727-2727-4727-8727-{len(self.content_skus) + 1:012d}", content_program_id=content_program_id, product_name=product_name, **kwargs)
        self.content_skus.append(sku)
        return sku

    def get_content_sku(self, sku_id: str) -> ContentSkuRecord | None:
        return next((item for item in self.content_skus if item.id == sku_id), None)

    def list_content_skus(self, content_program_id: str, include_inactive: bool = False) -> list[ContentSkuRecord]:
        return [item for item in self.content_skus if item.content_program_id == content_program_id and (include_inactive or item.is_active)]

    def update_content_sku(self, sku_id: str, **kwargs: object) -> ContentSkuRecord:
        sku = self.get_content_sku(sku_id)
        if sku is None:
            raise CampaignOpsNotFoundError("SKU was not found.")
        for key, value in kwargs.items():
            setattr(sku, key, value)
        return sku

    def deactivate_content_sku(self, sku_id: str) -> None:
        self.update_content_sku(sku_id, is_active=False)

    def reactivate_content_sku(self, sku_id: str) -> ContentSkuRecord:
        return self.update_content_sku(sku_id, is_active=True)

    def create_content_deliverable(self, content_program_id: str, deliverable_name: str, **kwargs: object) -> ContentDeliverableRecord:
        deliverable = ContentDeliverableRecord(id=f"26262626-2626-4626-8626-{len(self.content_deliverables) + 1:012d}", content_program_id=content_program_id, deliverable_name=deliverable_name, **kwargs)
        self.content_deliverables.append(deliverable)
        return deliverable

    def list_content_deliverables(self, content_program_id: str, include_inactive: bool = False) -> list[ContentDeliverableRecord]:
        return [item for item in self.content_deliverables if item.content_program_id == content_program_id and (include_inactive or item.is_active)]

    def update_content_deliverable(self, deliverable_id: str, **kwargs: object) -> ContentDeliverableRecord:
        deliverable = next((item for item in self.content_deliverables if item.id == deliverable_id), None)
        if deliverable is None:
            raise CampaignOpsNotFoundError("Deliverable was not found.")
        for key, value in kwargs.items():
            setattr(deliverable, key, value)
        return deliverable

    def deactivate_content_deliverable(self, deliverable_id: str) -> None:
        self.update_content_deliverable(deliverable_id, is_active=False)

    def reactivate_content_deliverable(self, deliverable_id: str) -> ContentDeliverableRecord:
        return self.update_content_deliverable(deliverable_id, is_active=True)

    def create_content_submission(self, content_program_id: str, **kwargs: object) -> ContentSubmissionRecord:
        submission = ContentSubmissionRecord(id=f"25252525-2525-4525-8525-{len(self.content_submissions) + 1:012d}", content_program_id=content_program_id, **kwargs)
        self.content_submissions.append(submission)
        return submission

    def list_content_submissions(self, content_program_id: str, include_inactive: bool = False) -> list[ContentSubmissionRecord]:
        return [item for item in self.content_submissions if item.content_program_id == content_program_id and (include_inactive or item.is_active)]

    def update_content_submission(self, submission_id: str, **kwargs: object) -> ContentSubmissionRecord:
        submission = next((item for item in self.content_submissions if item.id == submission_id), None)
        if submission is None:
            raise CampaignOpsNotFoundError("Submission was not found.")
        for key, value in kwargs.items():
            setattr(submission, key, value)
        return submission

    def deactivate_content_submission(self, submission_id: str) -> None:
        self.update_content_submission(submission_id, is_active=False)

    def reactivate_content_submission(self, submission_id: str) -> ContentSubmissionRecord:
        return self.update_content_submission(submission_id, is_active=True)

    def create_content_monitoring_update(self, content_program_id: str, update_date: date, update_text: str, actor_user_id: str | None = None, **kwargs: object) -> ContentMonitoringUpdateRecord:
        update = ContentMonitoringUpdateRecord(id=f"24242424-2424-4424-8424-{len(self.content_monitoring_updates) + 1:012d}", content_program_id=content_program_id, update_date=update_date, update_text=update_text, created_by_user_id=actor_user_id, **kwargs)
        self.content_monitoring_updates.append(update)
        return update

    def list_content_monitoring_updates(self, content_program_id: str, include_inactive: bool = False) -> list[ContentMonitoringUpdateRecord]:
        return sorted([item for item in self.content_monitoring_updates if item.content_program_id == content_program_id and (include_inactive or item.is_active)], key=lambda item: item.update_date, reverse=True)

    def update_content_monitoring_update(self, update_id: str, **kwargs: object) -> ContentMonitoringUpdateRecord:
        update = next((item for item in self.content_monitoring_updates if item.id == update_id), None)
        if update is None:
            raise CampaignOpsNotFoundError("Monitoring update was not found.")
        for key, value in kwargs.items():
            setattr(update, key, value)
        return update

    def deactivate_content_monitoring_update(self, update_id: str) -> None:
        self.update_content_monitoring_update(update_id, is_active=False)

    def reactivate_content_monitoring_update(self, update_id: str) -> ContentMonitoringUpdateRecord:
        return self.update_content_monitoring_update(update_id, is_active=True)

    def create_content_invoice_checkpoint(self, content_program_id: str, checkpoint_name: str, **kwargs: object) -> ContentInvoiceCheckpointRecord:
        checkpoint = ContentInvoiceCheckpointRecord(id=f"23232323-2323-4323-8323-{len(self.content_invoice_checkpoints) + 1:012d}", content_program_id=content_program_id, checkpoint_name=checkpoint_name, **kwargs)
        self.content_invoice_checkpoints.append(checkpoint)
        return checkpoint

    def list_content_invoice_checkpoints(self, content_program_id: str, include_inactive: bool = False) -> list[ContentInvoiceCheckpointRecord]:
        return [item for item in self.content_invoice_checkpoints if item.content_program_id == content_program_id and (include_inactive or item.is_active)]

    def update_content_invoice_checkpoint(self, checkpoint_id: str, **kwargs: object) -> ContentInvoiceCheckpointRecord:
        checkpoint = next((item for item in self.content_invoice_checkpoints if item.id == checkpoint_id), None)
        if checkpoint is None:
            raise CampaignOpsNotFoundError("Invoice checkpoint was not found.")
        for key, value in kwargs.items():
            setattr(checkpoint, key, value)
        return checkpoint

    def deactivate_content_invoice_checkpoint(self, checkpoint_id: str) -> None:
        self.update_content_invoice_checkpoint(checkpoint_id, is_active=False)

    def reactivate_content_invoice_checkpoint(self, checkpoint_id: str) -> ContentInvoiceCheckpointRecord:
        return self.update_content_invoice_checkpoint(checkpoint_id, is_active=True)

    def create_influencer_campaign(self, actor_user_id: str | None = None, **kwargs: object) -> InfluencerCampaignRecord:
        campaign = InfluencerCampaignRecord(id=f"22292929-2929-4929-8929-{len(self.influencer_campaigns) + 1:012d}", created_by_user_id=actor_user_id, **kwargs)
        self.influencer_campaigns.append(campaign)
        return campaign

    def get_influencer_campaign(self, campaign_id: str) -> InfluencerCampaignRecord | None:
        return next((item for item in self.influencer_campaigns if item.id == campaign_id), None)

    def get_active_influencer_campaign_by_title(self, program_id: str, campaign_title: str) -> InfluencerCampaignRecord | None:
        return next((item for item in self.influencer_campaigns if item.program_id == program_id and item.is_active and item.campaign_title.lower() == campaign_title.lower()), None)

    def update_influencer_campaign(self, campaign_id: str, **kwargs: object) -> InfluencerCampaignRecord:
        campaign = self.get_influencer_campaign(campaign_id)
        if campaign is None:
            raise CampaignOpsNotFoundError("Influencer campaign was not found.")
        for key, value in kwargs.items():
            setattr(campaign, key, value)
        campaign.updated_at = datetime.now(UTC)
        return campaign

    def deactivate_influencer_campaign(self, campaign_id: str) -> None:
        self.update_influencer_campaign(campaign_id, is_active=False)

    def reactivate_influencer_campaign(self, campaign_id: str) -> InfluencerCampaignRecord:
        return self.update_influencer_campaign(campaign_id, is_active=True)

    def _influencer_portfolio_row(self, campaign: InfluencerCampaignRecord) -> InfluencerPlanningPortfolioRow:
        program = self.get_program(campaign.program_id)
        client = self.get_client(program.client_id) if program and program.client_id else None
        manager = self.get_user_by_id(campaign.manager_user_id) if campaign.manager_user_id else None
        summary = self.get_influencer_creator_summary(campaign.id)
        steps = [step for step in self.influencer_planning_steps if step.influencer_campaign_id == campaign.id and step.is_active and step.status != "complete" and step.completed_date is None]
        steps.sort(key=lambda item: (item.sequence_order, item.due_date or date.max, item.created_at or datetime.min))
        resources = [resource for resource in self.resources if resource.program_id == campaign.program_id and resource.is_active]

        def resource_url(resource_type: str) -> str | None:
            return next((resource.url for resource in resources if resource.resource_type == resource_type and resource.url), None)

        return InfluencerPlanningPortfolioRow(
            id=campaign.id,
            program_id=campaign.program_id,
            program_name=program.program_name if program else "",
            client_name=client.name if client else None,
            workstream_id=campaign.workstream_id,
            campaign_title=campaign.campaign_title,
            manager_user_id=campaign.manager_user_id,
            manager_display_name=manager.display_name if manager else None,
            influencer_stage=campaign.influencer_stage,
            planning_status=campaign.planning_status,
            latest_update=campaign.latest_update,
            waiting_on=campaign.waiting_on,
            is_on_hold=campaign.is_on_hold,
            hold_reason=campaign.hold_reason,
            application_open_date=campaign.application_open_date,
            application_close_date=campaign.application_close_date,
            influencer_approval_due_date=campaign.influencer_approval_due_date,
            scripts_due_date=campaign.scripts_due_date,
            first_content_due_date=campaign.first_content_due_date,
            launch_date=campaign.launch_date,
            wrap_date=campaign.wrap_date,
            invoice_date=campaign.invoice_date,
            invoice_status=campaign.invoice_status,
            invoice_amount=campaign.invoice_amount,
            target_creator_count=(summary.target_creator_count if summary else campaign.target_creator_count),
            approved_creator_count=(summary.approved_count if summary else campaign.approved_creator_count),
            contracted_creator_count=(summary.contracted_count if summary else campaign.contracted_creator_count),
            applicants_count=summary.applicants_count if summary else None,
            vetted_count=summary.vetted_count if summary else None,
            submitted_for_approval_count=summary.submitted_for_approval_count if summary else None,
            content_submitted_count=summary.content_submitted_count if summary else None,
            content_approved_count=summary.content_approved_count if summary else None,
            creator_summary_notes=summary.notes if summary else None,
            program_status=program.status if program else ProgramStatus.ACTIVE.value,
            program_risk=program.risk_level if program else RiskLevel.UNRATED.value,
            next_planning_step=steps[0].step_title if steps else None,
            next_planning_step_due_date=steps[0].due_date if steps else None,
            track_sheet_url=resource_url("Track Sheet"),
            influencer_brief_url=resource_url("Influencer Brief"),
            bitly_link_url=resource_url("Bitly Link"),
            invoice_url=resource_url("Invoice"),
            eop_survey_url=resource_url("EOP Survey"),
            influencer_education_url=resource_url("Influencer Education"),
            campaign_brief_url=resource_url("Campaign Brief"),
            click2cart_link_url=resource_url("Click2Cart Link"),
            content_folder_url=resource_url("Content Folder"),
            application_link_url=resource_url("Application Link"),
            is_active=campaign.is_active,
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
        )

    def list_influencer_campaigns(self, include_inactive: bool = False, manager_user_id: str | None = None, stage: str | None = None) -> list[InfluencerPlanningPortfolioRow]:
        rows = [self._influencer_portfolio_row(item) for item in self.influencer_campaigns if (include_inactive or item.is_active) and (not manager_user_id or item.manager_user_id == manager_user_id) and (not stage or item.influencer_stage == stage)]
        return rows

    def get_influencer_campaign_detail(self, campaign_id: str) -> InfluencerPlanningPortfolioRow | None:
        campaign = self.get_influencer_campaign(campaign_id)
        return self._influencer_portfolio_row(campaign) if campaign else None

    def create_influencer_planning_step(self, influencer_campaign_id: str, step_title: str, **kwargs: object) -> InfluencerPlanningStepRecord:
        step = InfluencerPlanningStepRecord(id=f"21212121-2121-4121-8121-{len(self.influencer_planning_steps) + 1:012d}", influencer_campaign_id=influencer_campaign_id, step_title=step_title, **kwargs)
        self.influencer_planning_steps.append(step)
        return step

    def list_influencer_planning_steps(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerPlanningStepRecord]:
        return sorted([item for item in self.influencer_planning_steps if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)], key=lambda item: (item.sequence_order, item.due_date or date.max))

    def list_influencer_planning_steps_for_campaigns(self, influencer_campaign_ids: list[str], include_inactive: bool = False) -> dict[str, list[InfluencerPlanningStepRecord]]:
        return {campaign_id: self.list_influencer_planning_steps(campaign_id, include_inactive=include_inactive) for campaign_id in influencer_campaign_ids}

    def update_influencer_planning_step(self, step_id: str, **kwargs: object) -> InfluencerPlanningStepRecord:
        step = next((item for item in self.influencer_planning_steps if item.id == step_id), None)
        if step is None:
            raise CampaignOpsNotFoundError("Planning step was not found.")
        for key, value in kwargs.items():
            setattr(step, key, value)
        return step

    def deactivate_influencer_planning_step(self, step_id: str) -> None:
        self.update_influencer_planning_step(step_id, is_active=False)

    def reactivate_influencer_planning_step(self, step_id: str) -> InfluencerPlanningStepRecord:
        return self.update_influencer_planning_step(step_id, is_active=True)

    def create_influencer_approval_round(self, influencer_campaign_id: str, approval_type: str, **kwargs: object) -> InfluencerApprovalRoundRecord:
        approval = InfluencerApprovalRoundRecord(id=f"20202020-2020-4020-8020-{len(self.influencer_approval_rounds) + 1:012d}", influencer_campaign_id=influencer_campaign_id, approval_type=approval_type, **kwargs)
        self.influencer_approval_rounds.append(approval)
        return approval

    def list_influencer_approval_rounds(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerApprovalRoundRecord]:
        return [item for item in self.influencer_approval_rounds if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)]

    def update_influencer_approval_round(self, approval_id: str, **kwargs: object) -> InfluencerApprovalRoundRecord:
        approval = next((item for item in self.influencer_approval_rounds if item.id == approval_id), None)
        if approval is None:
            raise CampaignOpsNotFoundError("Approval round was not found.")
        for key, value in kwargs.items():
            setattr(approval, key, value)
        return approval

    def deactivate_influencer_approval_round(self, approval_id: str) -> None:
        self.update_influencer_approval_round(approval_id, is_active=False)

    def reactivate_influencer_approval_round(self, approval_id: str) -> InfluencerApprovalRoundRecord:
        return self.update_influencer_approval_round(approval_id, is_active=True)

    def create_influencer_content_round(self, influencer_campaign_id: str, round_number: int, **kwargs: object) -> InfluencerContentRoundRecord:
        content_round = InfluencerContentRoundRecord(id=f"19191919-1919-4919-8919-{len(self.influencer_content_rounds) + 1:012d}", influencer_campaign_id=influencer_campaign_id, round_number=round_number, **kwargs)
        self.influencer_content_rounds.append(content_round)
        return content_round

    def list_influencer_content_rounds(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerContentRoundRecord]:
        return [item for item in self.influencer_content_rounds if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)]

    def update_influencer_content_round(self, content_round_id: str, **kwargs: object) -> InfluencerContentRoundRecord:
        content_round = next((item for item in self.influencer_content_rounds if item.id == content_round_id), None)
        if content_round is None:
            raise CampaignOpsNotFoundError("Content round was not found.")
        for key, value in kwargs.items():
            setattr(content_round, key, value)
        return content_round

    def deactivate_influencer_content_round(self, content_round_id: str) -> None:
        self.update_influencer_content_round(content_round_id, is_active=False)

    def reactivate_influencer_content_round(self, content_round_id: str) -> InfluencerContentRoundRecord:
        return self.update_influencer_content_round(content_round_id, is_active=True)

    def get_influencer_creator_summary(self, influencer_campaign_id: str) -> InfluencerCreatorSummaryRecord | None:
        return next((item for item in self.influencer_creator_summaries if item.influencer_campaign_id == influencer_campaign_id), None)

    def create_or_update_influencer_creator_summary(self, influencer_campaign_id: str, **kwargs: object) -> InfluencerCreatorSummaryRecord:
        summary = self.get_influencer_creator_summary(influencer_campaign_id)
        if summary is None:
            summary = InfluencerCreatorSummaryRecord(id=f"18181818-1818-4818-8818-{len(self.influencer_creator_summaries) + 1:012d}", influencer_campaign_id=influencer_campaign_id)
            self.influencer_creator_summaries.append(summary)
        for key, value in kwargs.items():
            setattr(summary, key, value)
        return summary

    def _influencer_live_portfolio_row(self, campaign: InfluencerCampaignRecord) -> InfluencerLivePortfolioRow:
        program = self.get_program(campaign.program_id)
        client = self.get_client(program.client_id) if program and program.client_id else None
        manager = self.get_user_by_id(campaign.manager_user_id) if campaign.manager_user_id else None
        checkpoints = [c for c in self.influencer_live_checkpoints if c.influencer_campaign_id == campaign.id and c.is_active and c.status != "complete" and c.completed_date is None]
        checkpoints.sort(key=lambda item: (item.due_date or date.max, item.sequence_order, item.created_at or datetime.min))
        waves = [w for w in self.influencer_creator_waves if w.influencer_campaign_id == campaign.id and w.is_active]
        creators = [c for c in self.influencer_live_creators if c.influencer_campaign_id == campaign.id and c.is_active]
        exceptions = [e for e in self.influencer_live_exceptions if e.influencer_campaign_id == campaign.id and e.is_active and e.status not in ("resolved", "cancelled")]
        resources = [r for r in self.resources if r.program_id == campaign.program_id and r.is_active]

        def resource_url(resource_type: str) -> str | None:
            return next((resource.url for resource in resources if resource.resource_type == resource_type and resource.url), None)

        return InfluencerLivePortfolioRow(
            id=campaign.id,
            program_id=campaign.program_id,
            program_name=program.program_name if program else "",
            client_name=client.name if client else None,
            workstream_id=campaign.workstream_id,
            campaign_title=campaign.campaign_title,
            manager_user_id=campaign.manager_user_id,
            manager_display_name=manager.display_name if manager else None,
            influencer_stage=campaign.influencer_stage,
            live_status=campaign.planning_status,
            planning_status=campaign.planning_status,
            latest_update=campaign.latest_update,
            waiting_on=campaign.waiting_on,
            is_on_hold=campaign.is_on_hold,
            hold_reason=campaign.hold_reason,
            planned_creator_count=sum(w.planned_creator_count or 0 for w in waves) or campaign.target_creator_count,
            live_creator_count=len([c for c in creators if c.live_status in ("live", "paid_live_complete", "complete")]),
            completed_creator_count=len([c for c in creators if c.live_status in ("paid_live_complete", "complete")]),
            active_wave_count=len(waves),
            next_go_live_date=min([c.scheduled_live_date for c in creators if c.scheduled_live_date and c.live_status not in ("live", "paid_live_complete", "complete")] or [None]),
            paid_live_end_date=max([c.paid_live_end_date for c in creators if c.paid_live_end_date] or [None]),
            open_exception_count=len(exceptions),
            highlighted_exception_count=len([e for e in exceptions if e.is_highlighted]),
            launch_date=campaign.launch_date,
            wrap_date=campaign.wrap_date,
            invoice_date=campaign.invoice_date,
            invoice_status=campaign.invoice_status,
            invoice_amount=campaign.invoice_amount,
            program_status=program.status if program else ProgramStatus.ACTIVE.value,
            program_risk=program.risk_level if program else RiskLevel.UNRATED.value,
            next_checkpoint=checkpoints[0].checkpoint_title if checkpoints else None,
            next_checkpoint_due_date=checkpoints[0].due_date if checkpoints else None,
            track_sheet_url=resource_url("Track Sheet"),
            influencer_brief_url=resource_url("Influencer Brief"),
            eop_survey_url=resource_url("EOP Survey"),
            invoice_url=resource_url("Invoice"),
            bitly_link_url=resource_url("Bitly Link"),
            click2cart_link_url=resource_url("Click2Cart Link"),
            client_facing_live_doc_url=resource_url("Client-Facing Live Doc"),
            daily_impressions_url=resource_url("Daily Impressions"),
            is_active=campaign.is_active,
            created_at=campaign.created_at,
            updated_at=campaign.updated_at,
        )

    def list_influencer_live_campaigns(self, include_inactive: bool = False, manager_user_id: str | None = None) -> list[InfluencerLivePortfolioRow]:
        return [self._influencer_live_portfolio_row(item) for item in self.influencer_campaigns if item.influencer_stage == INFLUENCER_STAGE_LIVE and (include_inactive or item.is_active) and (not manager_user_id or item.manager_user_id == manager_user_id)]

    def get_influencer_live_campaign_detail(self, campaign_id: str) -> InfluencerLivePortfolioRow | None:
        campaign = self.get_influencer_campaign(campaign_id)
        return self._influencer_live_portfolio_row(campaign) if campaign and campaign.influencer_stage == INFLUENCER_STAGE_LIVE else None

    def create_influencer_live_checkpoint(self, influencer_campaign_id: str, checkpoint_title: str, **kwargs: object) -> InfluencerLiveCheckpointRecord:
        checkpoint = InfluencerLiveCheckpointRecord(id=f"17171717-1717-4717-8717-{len(self.influencer_live_checkpoints) + 1:012d}", influencer_campaign_id=influencer_campaign_id, checkpoint_title=checkpoint_title, **kwargs)
        self.influencer_live_checkpoints.append(checkpoint)
        return checkpoint

    def list_influencer_live_checkpoints(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveCheckpointRecord]:
        return sorted([item for item in self.influencer_live_checkpoints if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)], key=lambda item: (item.sequence_order, item.due_date or date.max))

    def list_influencer_live_checkpoints_for_campaigns(self, influencer_campaign_ids: list[str], include_inactive: bool = False) -> dict[str, list[InfluencerLiveCheckpointRecord]]:
        return {campaign_id: self.list_influencer_live_checkpoints(campaign_id, include_inactive=include_inactive) for campaign_id in influencer_campaign_ids}

    def update_influencer_live_checkpoint(self, checkpoint_id: str, **kwargs: object) -> InfluencerLiveCheckpointRecord:
        checkpoint = next((item for item in self.influencer_live_checkpoints if item.id == checkpoint_id), None)
        if checkpoint is None:
            raise CampaignOpsNotFoundError("Live checkpoint was not found.")
        for key, value in kwargs.items():
            setattr(checkpoint, key, value)
        return checkpoint

    def deactivate_influencer_live_checkpoint(self, checkpoint_id: str) -> None:
        self.update_influencer_live_checkpoint(checkpoint_id, is_active=False)

    def reactivate_influencer_live_checkpoint(self, checkpoint_id: str) -> InfluencerLiveCheckpointRecord:
        return self.update_influencer_live_checkpoint(checkpoint_id, is_active=True)

    def create_influencer_creator_wave(self, influencer_campaign_id: str, wave_number: int, **kwargs: object) -> InfluencerCreatorWaveRecord:
        wave = InfluencerCreatorWaveRecord(id=f"16161616-1616-4616-8616-{len(self.influencer_creator_waves) + 1:012d}", influencer_campaign_id=influencer_campaign_id, wave_number=wave_number, **kwargs)
        self.influencer_creator_waves.append(wave)
        return wave

    def list_influencer_creator_waves(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerCreatorWaveRecord]:
        return sorted([item for item in self.influencer_creator_waves if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)], key=lambda item: (item.wave_number, item.created_at or datetime.min))

    def list_influencer_creator_waves_for_campaigns(self, influencer_campaign_ids: list[str], include_inactive: bool = False) -> dict[str, list[InfluencerCreatorWaveRecord]]:
        return {campaign_id: self.list_influencer_creator_waves(campaign_id, include_inactive=include_inactive) for campaign_id in influencer_campaign_ids}

    def update_influencer_creator_wave(self, wave_id: str, **kwargs: object) -> InfluencerCreatorWaveRecord:
        wave = next((item for item in self.influencer_creator_waves if item.id == wave_id), None)
        if wave is None:
            raise CampaignOpsNotFoundError("Creator wave was not found.")
        for key, value in kwargs.items():
            setattr(wave, key, value)
        return wave

    def deactivate_influencer_creator_wave(self, wave_id: str) -> None:
        self.update_influencer_creator_wave(wave_id, is_active=False)

    def reactivate_influencer_creator_wave(self, wave_id: str) -> InfluencerCreatorWaveRecord:
        return self.update_influencer_creator_wave(wave_id, is_active=True)

    def create_influencer_live_creator(self, influencer_campaign_id: str, creator_name: str, **kwargs: object) -> InfluencerLiveCreatorRecord:
        creator = InfluencerLiveCreatorRecord(id=f"15151515-1515-4515-8515-{len(self.influencer_live_creators) + 1:012d}", influencer_campaign_id=influencer_campaign_id, creator_name=creator_name, **kwargs)
        self.influencer_live_creators.append(creator)
        return creator

    def list_influencer_live_creators(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveCreatorRecord]:
        return [item for item in self.influencer_live_creators if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)]

    def update_influencer_live_creator(self, creator_id: str, **kwargs: object) -> InfluencerLiveCreatorRecord:
        creator = next((item for item in self.influencer_live_creators if item.id == creator_id), None)
        if creator is None:
            raise CampaignOpsNotFoundError("Live creator was not found.")
        for key, value in kwargs.items():
            setattr(creator, key, value)
        return creator

    def deactivate_influencer_live_creator(self, creator_id: str) -> None:
        self.update_influencer_live_creator(creator_id, is_active=False)

    def reactivate_influencer_live_creator(self, creator_id: str) -> InfluencerLiveCreatorRecord:
        return self.update_influencer_live_creator(creator_id, is_active=True)

    def create_influencer_live_exception(self, influencer_campaign_id: str, exception_title: str, **kwargs: object) -> InfluencerLiveExceptionRecord:
        exception = InfluencerLiveExceptionRecord(id=f"14141414-1414-4414-8414-{len(self.influencer_live_exceptions) + 1:012d}", influencer_campaign_id=influencer_campaign_id, exception_title=exception_title, **kwargs)
        self.influencer_live_exceptions.append(exception)
        return exception

    def list_influencer_live_exceptions(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveExceptionRecord]:
        return [item for item in self.influencer_live_exceptions if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)]

    def update_influencer_live_exception(self, exception_id: str, **kwargs: object) -> InfluencerLiveExceptionRecord:
        exception = next((item for item in self.influencer_live_exceptions if item.id == exception_id), None)
        if exception is None:
            raise CampaignOpsNotFoundError("Live exception was not found.")
        for key, value in kwargs.items():
            setattr(exception, key, value)
        return exception

    def deactivate_influencer_live_exception(self, exception_id: str) -> None:
        self.update_influencer_live_exception(exception_id, is_active=False)

    def reactivate_influencer_live_exception(self, exception_id: str) -> InfluencerLiveExceptionRecord:
        return self.update_influencer_live_exception(exception_id, is_active=True)

    def create_or_update_influencer_recap_record(self, influencer_campaign_id: str, **kwargs: object) -> InfluencerRecapRecord:
        record = self.get_influencer_recap_record(influencer_campaign_id)
        if record is None:
            record = InfluencerRecapRecord(id=f"13131313-1313-4313-8313-{len(self.influencer_recap_records) + 1:012d}", influencer_campaign_id=influencer_campaign_id)
            self.influencer_recap_records.append(record)
        for key, value in kwargs.items():
            setattr(record, key, value)
        return record

    def get_influencer_recap_record(self, influencer_campaign_id: str) -> InfluencerRecapRecord | None:
        return next((item for item in self.influencer_recap_records if item.influencer_campaign_id == influencer_campaign_id), None)

    def update_influencer_recap_record(self, recap_record_id: str, **kwargs: object) -> InfluencerRecapRecord:
        record = next((item for item in self.influencer_recap_records if item.id == recap_record_id), None)
        if record is None:
            raise CampaignOpsNotFoundError("Recap record was not found.")
        for key, value in kwargs.items():
            setattr(record, key, value)
        return record

    def _influencer_recap_portfolio_row(self, campaign: InfluencerCampaignRecord) -> InfluencerRecapPortfolioRow:
        program = self.get_program(campaign.program_id)
        client = self.get_client(program.client_id) if program and program.client_id else None
        manager = self.get_user_by_id(campaign.manager_user_id) if campaign.manager_user_id else None
        record = self.get_influencer_recap_record(campaign.id)
        checkpoints = [c for c in self.influencer_recap_checkpoints if c.influencer_campaign_id == campaign.id and c.is_active and c.status != "complete" and c.completed_date is None]
        checkpoints.sort(key=lambda item: (item.due_date or date.max, item.sequence_order, item.created_at or datetime.min))
        reqs = [r for r in self.influencer_recap_requirements if r.influencer_campaign_id == campaign.id and r.is_active]
        launches = [i for i in self.influencer_recap_launch_items if i.influencer_campaign_id == campaign.id and i.is_active]
        creators = [c for c in self.influencer_live_creators if c.influencer_campaign_id == campaign.id and c.is_active]
        exceptions = [e for e in self.influencer_live_exceptions if e.influencer_campaign_id == campaign.id and e.is_active and e.status not in ("resolved", "cancelled")]
        resources = [r for r in self.resources if r.program_id == campaign.program_id and r.is_active]

        def resource_url(resource_type: str) -> str | None:
            return next((resource.url for resource in resources if resource.resource_type == resource_type and resource.url), None)

        open_req_count = len([r for r in reqs if r.required and r.status not in ("complete", "not_required", "cancelled")])
        paid_incomplete = len([c for c in creators if c.live_status not in ("paid_live_complete", "complete", "cancelled")])
        missing_links = len([c for c in creators if not c.content_url])
        missing_impressions = len([c for c in creators if c.impressions_reporting_required and c.latest_impressions is None])
        ready = "Needs Attention" if exceptions else "Not Ready" if open_req_count or paid_incomplete or missing_links or missing_impressions or checkpoints else "Ready to Close"
        if campaign.influencer_stage == "complete" or (record and record.recap_status == "complete"):
            ready = "Complete"
        recap_deck = next((r.status for r in reqs if r.requirement_type == "Recap Deck"), None)
        return InfluencerRecapPortfolioRow(
            id=campaign.id, program_id=campaign.program_id, program_name=program.program_name if program else "", client_name=client.name if client else None,
            workstream_id=campaign.workstream_id, campaign_title=campaign.campaign_title, manager_user_id=campaign.manager_user_id,
            manager_display_name=manager.display_name if manager else None, influencer_stage=campaign.influencer_stage,
            recap_record_id=record.id if record else None, recap_status=(record.recap_status if record else campaign.planning_status),
            latest_update=(record.latest_update if record else campaign.latest_update), waiting_on=(record.waiting_on if record else campaign.waiting_on),
            all_creators_live=bool(creators) and all(c.live_status in ("live", "paid_live_complete", "complete") for c in creators),
            creator_closeout_status=record.creator_closeout_status if record else None, eop_survey_status=record.eop_survey_status if record else None,
            final_performance_data_status=record.final_performance_data_status if record else None,
            sales_lift_analysis_required=bool(record.sales_lift_analysis_required if record else False),
            sales_lift_analysis_status=record.sales_lift_analysis_status if record else None, recap_deck_status=recap_deck,
            client_recap_date=record.client_recap_date if record else None, invoice_status=(record.invoice_status if record and record.invoice_status else campaign.invoice_status),
            financial_close_status=record.financial_close_status if record else None, open_requirement_count=open_req_count, launch_item_count=len(launches),
            open_exception_count=len(exceptions), total_creator_count=len(creators),
            live_creator_count=len([c for c in creators if c.live_status in ("live", "paid_live_complete", "complete")]),
            completed_creator_count=len([c for c in creators if c.live_status in ("paid_live_complete", "complete")]),
            missing_final_links_count=missing_links, missing_final_impressions_count=missing_impressions, paid_live_incomplete_count=paid_incomplete,
            program_status=program.status if program else ProgramStatus.ACTIVE.value, program_risk=program.risk_level if program else RiskLevel.UNRATED.value,
            reporting_due_date=record.reporting_due_date if record else None, next_checkpoint=checkpoints[0].checkpoint_title if checkpoints else None,
            next_checkpoint_due_date=checkpoints[0].due_date if checkpoints else None, track_sheet_url=resource_url("Track Sheet"),
            influencer_brief_url=resource_url("Influencer Brief"), click2cart_link_url=resource_url("Click2Cart Link"),
            bitly_link_url=resource_url("Bitly Link"), invoice_url=resource_url("Invoice"), eop_survey_url=resource_url("EOP Survey"),
            live_content_tracker_url=resource_url("Live Content Tracker"), recap_deck_url=resource_url("Recap Deck"),
            final_performance_data_url=resource_url("Final Performance Data"), sales_lift_analysis_url=resource_url("Sales Lift Analysis"),
            ready_to_close_state=ready, is_active=campaign.is_active, created_at=campaign.created_at, updated_at=campaign.updated_at,
        )

    def list_influencer_recap_campaigns(self, include_inactive: bool = False, manager_user_id: str | None = None) -> list[InfluencerRecapPortfolioRow]:
        stages = {INFLUENCER_STAGE_RECAPPING, "complete"} if include_inactive else {INFLUENCER_STAGE_RECAPPING}
        return [self._influencer_recap_portfolio_row(item) for item in self.influencer_campaigns if item.influencer_stage in stages and (include_inactive or item.is_active) and (not manager_user_id or item.manager_user_id == manager_user_id)]

    def get_influencer_recap_campaign_detail(self, campaign_id: str) -> InfluencerRecapPortfolioRow | None:
        campaign = self.get_influencer_campaign(campaign_id)
        return self._influencer_recap_portfolio_row(campaign) if campaign and campaign.influencer_stage in {INFLUENCER_STAGE_RECAPPING, "complete"} else None

    def create_influencer_recap_checkpoint(self, influencer_campaign_id: str, checkpoint_title: str, **kwargs: object) -> InfluencerRecapCheckpointRecord:
        checkpoint = InfluencerRecapCheckpointRecord(id=f"12121212-1212-4212-8212-{len(self.influencer_recap_checkpoints) + 1:012d}", influencer_campaign_id=influencer_campaign_id, checkpoint_title=checkpoint_title, **kwargs)
        self.influencer_recap_checkpoints.append(checkpoint)
        return checkpoint

    def list_influencer_recap_checkpoints(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapCheckpointRecord]:
        return sorted([item for item in self.influencer_recap_checkpoints if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)], key=lambda item: (item.sequence_order, item.due_date or date.max))

    def update_influencer_recap_checkpoint(self, checkpoint_id: str, **kwargs: object) -> InfluencerRecapCheckpointRecord:
        checkpoint = next((item for item in self.influencer_recap_checkpoints if item.id == checkpoint_id), None)
        if checkpoint is None:
            raise CampaignOpsNotFoundError("Recap checkpoint was not found.")
        for key, value in kwargs.items():
            setattr(checkpoint, key, value)
        return checkpoint

    def deactivate_influencer_recap_checkpoint(self, checkpoint_id: str) -> None:
        self.update_influencer_recap_checkpoint(checkpoint_id, is_active=False)

    def reactivate_influencer_recap_checkpoint(self, checkpoint_id: str) -> InfluencerRecapCheckpointRecord:
        return self.update_influencer_recap_checkpoint(checkpoint_id, is_active=True)

    def create_influencer_recap_requirement(self, influencer_campaign_id: str, requirement_type: str, requirement_title: str, **kwargs: object) -> InfluencerRecapRequirementRecord:
        req = InfluencerRecapRequirementRecord(id=f"11121212-1212-4212-8212-{len(self.influencer_recap_requirements) + 1:012d}", influencer_campaign_id=influencer_campaign_id, requirement_type=requirement_type, requirement_title=requirement_title, **kwargs)
        self.influencer_recap_requirements.append(req)
        return req

    def list_influencer_recap_requirements(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapRequirementRecord]:
        return [item for item in self.influencer_recap_requirements if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)]

    def update_influencer_recap_requirement(self, requirement_id: str, **kwargs: object) -> InfluencerRecapRequirementRecord:
        req = next((item for item in self.influencer_recap_requirements if item.id == requirement_id), None)
        if req is None:
            raise CampaignOpsNotFoundError("Recap requirement was not found.")
        for key, value in kwargs.items():
            setattr(req, key, value)
        return req

    def deactivate_influencer_recap_requirement(self, requirement_id: str) -> None:
        self.update_influencer_recap_requirement(requirement_id, is_active=False)

    def reactivate_influencer_recap_requirement(self, requirement_id: str) -> InfluencerRecapRequirementRecord:
        return self.update_influencer_recap_requirement(requirement_id, is_active=True)

    def create_influencer_recap_launch_item(self, influencer_campaign_id: str, product_name: str, **kwargs: object) -> InfluencerRecapLaunchItemRecord:
        item = InfluencerRecapLaunchItemRecord(id=f"10121212-1212-4212-8212-{len(self.influencer_recap_launch_items) + 1:012d}", influencer_campaign_id=influencer_campaign_id, product_name=product_name, **kwargs)
        self.influencer_recap_launch_items.append(item)
        return item

    def list_influencer_recap_launch_items(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapLaunchItemRecord]:
        return sorted([item for item in self.influencer_recap_launch_items if item.influencer_campaign_id == influencer_campaign_id and (include_inactive or item.is_active)], key=lambda item: (item.sort_order, item.group_name or "", item.product_name))

    def update_influencer_recap_launch_item(self, launch_item_id: str, **kwargs: object) -> InfluencerRecapLaunchItemRecord:
        item = next((item for item in self.influencer_recap_launch_items if item.id == launch_item_id), None)
        if item is None:
            raise CampaignOpsNotFoundError("Recap launch item was not found.")
        for key, value in kwargs.items():
            setattr(item, key, value)
        return item

    def deactivate_influencer_recap_launch_item(self, launch_item_id: str) -> None:
        self.update_influencer_recap_launch_item(launch_item_id, is_active=False)

    def reactivate_influencer_recap_launch_item(self, launch_item_id: str) -> InfluencerRecapLaunchItemRecord:
        return self.update_influencer_recap_launch_item(launch_item_id, is_active=True)

    def _task_list_row(self, task: Task) -> TaskListRow:
        program = self.get_program(task.program_id)
        workstream = self.get_workstream(task.workstream_id) if task.workstream_id else None
        assignee = self.get_user_by_id(task.assigned_user_id) if task.assigned_user_id else None
        client = self.get_program_client(task.program_id)
        return TaskListRow(
            id=task.id,
            program_id=task.program_id,
            program_name=program.program_name if program else "",
            client_name=client.name if client else None,
            title=task.title,
            description=task.description,
            workstream_id=task.workstream_id,
            workstream_type=workstream.workstream_type if workstream else None,
            assigned_user_id=task.assigned_user_id,
            assigned_user_name=assignee.display_name if assignee else None,
            responsible_party=task.responsible_party,
            status=task.status,
            risk_level=task.risk_level,
            waiting_on=task.waiting_on,
            due_date=task.due_date,
            start_date=task.start_date,
            completed_at=task.completed_at,
            hard_deadline=task.hard_deadline,
            priority=task.priority,
            sort_order=task.sort_order,
            is_active=task.is_active,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def list_task_rows_by_program(self, program_id: str, include_inactive: bool = False) -> list[TaskListRow]:
        rows = [
            self._task_list_row(task)
            for task in self.tasks
            if task.program_id == program_id and (include_inactive or task.is_active)
        ]
        return sorted(rows, key=lambda task: (task.sort_order, task.due_date or date.max, task.title))

    def list_task_rows_by_assigned_user(self, user_id: str, include_inactive: bool = False) -> list[TaskListRow]:
        rows = [
            self._task_list_row(task)
            for task in self.tasks
            if task.assigned_user_id == user_id and (include_inactive or task.is_active)
        ]
        return sorted(rows, key=lambda task: (task.due_date or date.max, task.title))

    def list_dashboard_task_rows(self, include_inactive: bool = False, permitted_user_id: str | None = None) -> list[TaskListRow]:
        rows = [
            self._task_list_row(task)
            for task in self.tasks
            if include_inactive or task.is_active
        ]
        if permitted_user_id:
            permitted_programs = {assignment.program_id for assignment in self.assignments if assignment.user_id == permitted_user_id and assignment.is_active}
            rows = [row for row in rows if row.program_id in permitted_programs]
        return sorted(rows, key=lambda task: (task.due_date or date.max, task.title))

    def list_dashboard_milestone_rows(self, include_inactive: bool = False, permitted_user_id: str | None = None) -> list[dict[str, object]]:
        permitted_programs = None
        if permitted_user_id:
            permitted_programs = {assignment.program_id for assignment in self.assignments if assignment.user_id == permitted_user_id and assignment.is_active}
        rows = []
        for milestone in self.milestones:
            if not include_inactive and not milestone.is_active:
                continue
            if permitted_programs is not None and milestone.program_id not in permitted_programs:
                continue
            program = self.get_program(milestone.program_id)
            client = self.get_program_client(milestone.program_id)
            workstream = self.get_workstream(milestone.workstream_id) if milestone.workstream_id else None
            owner = self.get_user_by_id(milestone.owner_user_id) if milestone.owner_user_id else None
            rows.append({
                **asdict(milestone),
                "program_name": program.program_name if program else "-",
                "client_name": client.name if client else None,
                "workstream_type": workstream.workstream_type if workstream else None,
                "owner_user_name": owner.display_name if owner else None,
            })
        return rows

    def list_dashboard_resource_rows(self, include_inactive: bool = False, permitted_user_id: str | None = None) -> list[ResourceListRow]:
        permitted_programs = None
        if permitted_user_id:
            permitted_programs = {assignment.program_id for assignment in self.assignments if assignment.user_id == permitted_user_id and assignment.is_active}
        rows = []
        for resource in self.resources:
            if not include_inactive and not resource.is_active:
                continue
            if permitted_programs is not None and resource.program_id not in permitted_programs:
                continue
            workstream = self.get_workstream(resource.workstream_id) if resource.workstream_id else None
            rows.append(ResourceListRow(
                id=resource.id,
                program_id=resource.program_id,
                title=resource.title,
                resource_type=resource.resource_type,
                workstream_id=resource.workstream_id,
                workstream_type=workstream.workstream_type if workstream else None,
                url=resource.url,
                notes=resource.notes,
                is_required=resource.is_required,
                is_active=resource.is_active,
                created_at=resource.created_at,
                updated_at=resource.updated_at,
            ))
        return rows

    def append_event(self, **kwargs: str | None) -> object:
        self.events.append(kwargs)
        return SimpleNamespace(id=f"event-{len(self.events)}")

    def list_program_portfolio(self, **kwargs: object) -> list[object]:
        self.last_portfolio_filters = kwargs
        rows = []
        for program in self.programs:
            active_state = kwargs.get("active_state", "active")
            if active_state == "active" and not program.is_active:
                continue
            if active_state == "archived" and program.is_active:
                continue
            if kwargs.get("client_id") and program.client_id != kwargs["client_id"]:
                continue
            if kwargs.get("primary_workstream_type") and program.primary_workstream_type != kwargs["primary_workstream_type"]:
                continue
            if kwargs.get("cross_stage") and program.cross_stage != kwargs["cross_stage"]:
                continue
            if kwargs.get("status") and program.status != kwargs["status"]:
                continue
            if kwargs.get("risk_level") and program.risk_level != kwargs["risk_level"]:
                continue
            assignments = [assignment for assignment in self.assignments if assignment.program_id == program.id and assignment.is_active]
            if kwargs.get("assigned_user_id") and kwargs["assigned_user_id"] not in {assignment.user_id for assignment in assignments}:
                continue
            if kwargs.get("permitted_user_id") and kwargs["permitted_user_id"] not in {assignment.user_id for assignment in assignments}:
                continue
            if kwargs.get("primary_owner_user_id") and not any(assignment.user_id == kwargs["primary_owner_user_id"] and assignment.is_primary for assignment in assignments):
                continue
            client = self.get_program_client(program.id)
            workstreams = [workstream for workstream in self.workstreams if workstream.program_id == program.id and workstream.is_active]
            primary = next((assignment for assignment in assignments if assignment.is_primary and assignment.assignment_role == AssignmentRole.PROGRAM_OWNER.value), None)
            owner = self.get_user_by_id(primary.user_id) if primary else None
            tasks = [task for task in self.tasks if task.program_id == program.id and task.is_active]
            open_tasks = [task for task in tasks if task.status not in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value}]
            overdue_tasks = [task for task in open_tasks if task.due_date and task.due_date < date.today()]
            rows.append(ProgramPortfolioRow(
                id=program.id,
                program_name=program.program_name,
                client_name=client.name if client else None,
                primary_workstream_type=program.primary_workstream_type,
                workstream_types=[workstream.workstream_type for workstream in workstreams],
                status=program.status,
                cross_stage=program.cross_stage,
                risk_level=program.risk_level,
                priority=program.priority,
                primary_owner_user_id=primary.user_id if primary else None,
                primary_owner_name=owner.display_name if owner else None,
                assigned_user_ids=[assignment.user_id for assignment in assignments],
                assigned_user_names=[self.get_user_by_id(assignment.user_id).display_name for assignment in assignments if self.get_user_by_id(assignment.user_id)],
                latest_update=program.latest_update,
                start_date=program.start_date,
                target_end_date=program.target_end_date,
                updated_at=program.updated_at,
                is_active=program.is_active,
                open_task_count=len(open_tasks),
                overdue_task_count=len(overdue_tasks),
                nearest_task_due_date=min((task.due_date for task in open_tasks if task.due_date), default=None),
            ))
        return rows

    def list_programs_assigned_to_user(self, user_id: str, **kwargs: object) -> list[object]:
        self.last_portfolio_filters = {"user_id": user_id, **kwargs}
        return []

    def get_program(self, program_id: str) -> Program | None:
        return next((program for program in self.programs if program.id == program_id), None)

    def get_program_client(self, program_id: str) -> Client | None:
        program = self.get_program(program_id)
        return self.get_client(program.client_id) if program and program.client_id else None

    def list_workstreams_by_program(self, program_id: str) -> list[Workstream]:
        return [workstream for workstream in self.workstreams if workstream.program_id == program_id and workstream.is_active]

    def list_all_workstreams_by_program(self, program_id: str) -> list[Workstream]:
        return [workstream for workstream in self.workstreams if workstream.program_id == program_id]

    def list_assignments_by_program(self, program_id: str) -> list[ProgramAssignment]:
        return [assignment for assignment in self.assignments if assignment.program_id == program_id and assignment.is_active]

    def list_all_assignments_by_program(self, program_id: str) -> list[ProgramAssignment]:
        return [assignment for assignment in self.assignments if assignment.program_id == program_id]

    def list_program_activity(self, program_id: str) -> list[object]:
        return []


class CampaignOpsFoundationTests(unittest.TestCase):
    def _prompt4c_fixture(self) -> tuple[
        FakePrompt4ARepository,
        CampaignOpsService,
        CampaignOpsUser,
        CampaignOpsUser,
        CampaignOpsUser,
        str,
        Workstream,
        Workstream,
    ]:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user, l_user = repository.users[:3]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=bailey.id,
            workstream_types=[WorkstreamType.INFLUENCER.value, WorkstreamType.RETAIL_MEDIA.value],
            workstream_lead_user_ids={
                WorkstreamType.INFLUENCER.value: t_user.id,
                WorkstreamType.RETAIL_MEDIA.value: l_user.id,
            },
        )
        influencer = next(
            workstream
            for workstream in repository.workstreams
            if workstream.program_id == program_id and workstream.workstream_type == WorkstreamType.INFLUENCER.value
        )
        retail = next(
            workstream
            for workstream in repository.workstreams
            if workstream.program_id == program_id and workstream.workstream_type == WorkstreamType.RETAIL_MEDIA.value
        )
        return repository, service, bailey, t_user, l_user, program_id, influencer, retail

    def test_enum_values_are_stable_storage_values(self) -> None:
        self.assertEqual(UserRole.ADMINISTRATOR.value, "administrator")
        self.assertEqual(ProgramStatus.ACTIVE.value, "active")
        self.assertEqual(WorkstreamType.RETAIL_MEDIA.value, "retail_media")
        self.assertEqual(TaskStatus.WAITING_ON_CLIENT.value, "waiting_on_client")

    def test_seed_users_are_exact_and_idempotent_definitions(self) -> None:
        users = get_seed_users()
        self.assertEqual([user.display_name for user in users], ["Bailey", "T", "L"])
        self.assertEqual([user.email for user in users], [None, None, None])
        self.assertEqual([user.role.value for user in users], ["administrator", "team_member", "team_member"])
        self.assertEqual(len({user.id for user in users}), 3)

    def test_seed_sql_uses_authoritative_enum_values_and_display_names(self) -> None:
        seed_sql = Path("db/migrations/002_campaign_ops_seed_users.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("'Bailey'", seed_sql)
        self.assertIn("'T'", seed_sql)
        self.assertIn("'L'", seed_sql)
        self.assertIn(f"'{UserRole.ADMINISTRATOR.value}'", seed_sql)
        self.assertIn(f"'{UserRole.TEAM_MEMBER.value}'", seed_sql)
        self.assertIn("lower(existing.display_name) = lower(seed_users.display_name)", seed_sql)

    def test_campaign_ops_database_url_is_isolated_from_database_url(self) -> None:
        with patch("core.campaign_ops.db.load_local_env", return_value=True):
            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": "postgresql://historical",
                    "CAMPAIGN_OPS_DATABASE_URL": "postgresql://campaign-ops",
                },
                clear=True,
            ):
                self.assertEqual(
                    get_campaign_ops_database_url(),
                    "postgresql://campaign-ops",
                )

            with patch.dict(
                "os.environ",
                {"DATABASE_URL": "postgresql://historical"},
                clear=True,
            ):
                self.assertIsNone(get_campaign_ops_database_url())

    def test_reachable_database_missing_users_table_is_uninitialized(self) -> None:
        fake_connection = FakeConnection()
        with patch("core.campaign_ops.db.get_campaign_ops_database_url", return_value="postgresql://ops"):
            with patch("core.campaign_ops.db.psycopg", object()):
                with patch("core.campaign_ops.db.dict_row", object()):
                    with patch("core.campaign_ops.db.connect_to_campaign_ops_database", return_value=fake_connection):
                        with patch(
                            "core.campaign_ops.db.table_exists",
                            side_effect=lambda _conn, table_name: table_name == "schema_migrations",
                        ):
                            status = get_campaign_ops_setup_status()

        self.assertEqual(status.state, "uninitialized")
        self.assertTrue(status.connection_succeeded)
        self.assertFalse(status.schema_initialized)

    def test_initialized_status_requires_metadata_tables(self) -> None:
        fake_connection = FakeConnection()
        with patch("core.campaign_ops.db.get_campaign_ops_database_url", return_value="postgresql://ops"):
            with patch("core.campaign_ops.db.psycopg", object()):
                with patch("core.campaign_ops.db.dict_row", object()):
                    with patch("core.campaign_ops.db.connect_to_campaign_ops_database", return_value=fake_connection):
                        with patch("core.campaign_ops.db.table_exists", return_value=True):
                            status = get_campaign_ops_setup_status()

        self.assertEqual(status.state, "initialized")
        self.assertTrue(status.schema_initialized)

    def test_repository_converts_undefined_table_to_setup_error(self) -> None:
        repository = CampaignOpsRepository(connection=MissingTableConnection())
        with patch("core.campaign_ops.repository.is_undefined_table_error", return_value=True):
            with self.assertRaises(CampaignOpsSetupRequiredError):
                repository.get_user_by_display_name("Bailey")

    def test_temporary_setup_admin_is_bailey_only(self) -> None:
        self.assertTrue(viewer_can_initialize_in_setup("Bailey"))
        self.assertFalse(viewer_can_initialize_in_setup("T"))
        self.assertFalse(viewer_can_initialize_in_setup("L"))

    def test_uninitialized_status_prevents_viewer_repository_lookup(self) -> None:
        status = CampaignOpsSetupStatus(
            state="uninitialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=False,
            message="Not initialized.",
        )
        with patch("app.pages.campaigns.render_header"):
            with patch("app.pages.campaigns.hide_default_streamlit_sidebar_nav"):
                with patch("app.pages.campaigns.clear_legacy_workflow_session_state"):
                    with patch("app.pages.campaigns.render_initialization_message"):
                        with patch("app.pages.campaigns.render_temporary_viewer_selector", return_value=("Bailey", "Cross-Team Dashboard")):
                            with patch("app.pages.campaigns.get_campaign_ops_setup_status", return_value=status):
                                with patch("app.pages.campaigns.render_setup_state", side_effect=StopIteration):
                                    with patch("app.pages.campaigns.resolve_viewer_user") as resolve_viewer:
                                        with patch("app.pages.campaigns.st.set_page_config"):
                                            with patch("app.pages.campaigns.st.divider"):
                                                with self.assertRaises(StopIteration):
                                                    __import__(
                                                        "app.pages.campaigns",
                                                        fromlist=["main"],
                                                    ).main()
        resolve_viewer.assert_not_called()

    def test_permissions_by_role(self) -> None:
        admin = CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value)
        member = CampaignOpsUser(id="u2", display_name="T", role=UserRole.TEAM_MEMBER.value)
        viewer = CampaignOpsUser(id="u3", display_name="Reader", role=UserRole.VIEWER.value)
        program = Program(id="p1", program_name="Program")

        self.assertTrue(can_access_admin(admin))
        self.assertTrue(can_archive_program(admin))
        self.assertTrue(can_view_program(admin, program, []))
        self.assertFalse(can_access_admin(member))
        self.assertFalse(can_archive_program(member))
        self.assertFalse(can_view_program(member, program, []))
        self.assertTrue(can_view_program(viewer, program, [], explicit_program_ids={"p1"}))

    def test_program_owner_can_edit_program(self) -> None:
        member = CampaignOpsUser(id="u2", display_name="T", role=UserRole.TEAM_MEMBER.value)
        program = Program(id="p1", program_name="Program")
        assignment = ProgramAssignment(
            id="a1",
            program_id="p1",
            user_id="u2",
            assignment_role="program_owner",
        )
        self.assertTrue(can_edit_program(member, program, [assignment]))

    def test_models_validate_required_fields_and_enums(self) -> None:
        with self.assertRaises(CampaignOpsValidationError):
            Program(id="p1", program_name="")
        with self.assertRaises(CampaignOpsValidationError):
            Task(id="t1", program_id="p1", title="Task", status="bad_status")
        with self.assertRaises(CampaignOpsValidationError):
            TaskDependency(id="d1", task_id="t1", depends_on_task_id="t1")

    def test_migration_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "002_second.sql").write_text("select 2;", encoding="utf-8")
            (root / "001_first.sql").write_text("select 1;", encoding="utf-8")
            self.assertEqual(get_migration_names(root), ["001_first.sql", "002_second.sql"])

    def test_migration_bookkeeping_prevents_reapply(self) -> None:
        fake_connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "001_first.sql").write_text("select 1;", encoding="utf-8")
            (root / "002_second.sql").write_text("select 2;", encoding="utf-8")

            with patch(
                "core.campaign_ops.migrations.connect_to_database",
                return_value=fake_connection,
            ):
                first = run_campaign_ops_migrations(root)
                second = run_campaign_ops_migrations(root)

        self.assertTrue(fake_connection.bookkeeping_created)
        self.assertEqual(first.applied_migrations, ["001_first.sql", "002_second.sql"])
        self.assertEqual(second.skipped_migrations, ["001_first.sql", "002_second.sql"])
        self.assertEqual(fake_connection.transaction_count, 2)
        self.assertGreaterEqual(fake_connection.commit_count, 2)

    def test_migration_001_applied_with_002_pending_retries_only_002(self) -> None:
        fake_connection = FakeConnection()
        fake_connection.applied_versions.add("001_first.sql")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "001_first.sql").write_text("select 1;", encoding="utf-8")
            (root / "002_second.sql").write_text("select 2;", encoding="utf-8")

            with patch(
                "core.campaign_ops.migrations.connect_to_database",
                return_value=fake_connection,
            ):
                result = run_campaign_ops_migrations(root)

        self.assertEqual(result.skipped_migrations, ["001_first.sql"])
        self.assertEqual(result.applied_migrations, ["002_second.sql"])

    def test_failed_migration_is_not_recorded_and_remains_retryable(self) -> None:
        fake_connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "001_bad.sql").write_text("raise failure;", encoding="utf-8")

            with patch(
                "core.campaign_ops.migrations.connect_to_database",
                return_value=fake_connection,
            ):
                with patch("core.campaign_ops.migrations.LOGGER.exception"):
                    with self.assertRaises(CampaignOpsDatabaseError):
                        run_campaign_ops_migrations(root)

        self.assertNotIn("001_bad.sql", fake_connection.applied_versions)

    def test_seed_verification_succeeds_without_writing_duplicates(self) -> None:
        fake_connection = FakeConnection()
        with patch(
            "core.campaign_ops.migrations.connect_to_database",
            return_value=fake_connection,
        ):
            first = verify_campaign_ops_seed_users()
            second = verify_campaign_ops_seed_users()

        self.assertEqual(first.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(second.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(len(fake_connection.users), 3)

    def test_seed_verification_failure_is_wrapped_safely(self) -> None:
        fake_connection = FakeConnection()
        fake_connection.users = [
            {"display_name": "Bailey", "role": "administrator", "is_active": True},
        ]
        with patch(
            "core.campaign_ops.migrations.connect_to_database",
            return_value=fake_connection,
        ):
            with patch("core.campaign_ops.migrations.LOGGER.exception"):
                with self.assertRaisesRegex(
                    CampaignOpsDatabaseError,
                    "Campaign Operations user seed verification failed.",
                ):
                    verify_campaign_ops_seed_users()

    def test_initialization_result_reports_applied_skipped_and_verified_users(self) -> None:
        with patch(
            "core.campaign_ops.migrations.run_campaign_ops_migrations",
            return_value=MigrationResult(["001.sql"], ["002.sql"]),
        ):
            with patch("core.campaign_ops.migrations.verify_campaign_ops_initialization"):
                with patch(
                    "core.campaign_ops.migrations.verify_campaign_ops_seed_users"
                ) as verify_seed:
                    verify_seed.return_value.verified_users = ["Bailey", "T", "L"]
                    verify_seed.return_value.seeded_users = ["Bailey", "T", "L"]
                    result = initialize_campaign_ops_database()

        self.assertEqual(result.migrations.applied_migrations, ["001.sql"])
        self.assertEqual(result.migrations.skipped_migrations, ["002.sql"])
        self.assertEqual(result.seed.verified_users, ["Bailey", "T", "L"])

    def test_initialization_display_summary_with_applied_migrations(self) -> None:
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult(["001.sql"], ["002.sql"]),
            seed=SeedResult(["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.applied_migrations, ["001.sql"])
        self.assertEqual(summary.skipped_migrations, ["002.sql"])
        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(
            summary.initialized_status,
            "Campaign Operations database is initialized.",
        )

    def test_initialization_display_summary_with_only_skipped_migrations(self) -> None:
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult([], ["001.sql", "002.sql"]),
            seed=SeedResult(["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.applied_migrations, [])
        self.assertEqual(summary.skipped_migrations, ["001.sql", "002.sql"])
        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])

    def test_initialization_display_summary_accepts_direct_seeded_users(self) -> None:
        result = SimpleNamespace(
            applied_migrations=["001.sql"],
            skipped_migrations=[],
            seeded_users=["Bailey", "T", "L"],
            status="Campaign Operations database is initialized.",
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.seeded_users, ["Bailey", "T", "L"])
        self.assertEqual(summary.verified_users, [])

    def test_initialization_display_summary_reads_verified_users_from_seed_model(self) -> None:
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult([], []),
            seed=SeedResult(["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])

    def test_initialization_display_summary_handles_missing_optional_fields(self) -> None:
        summary = format_initialization_result({})

        self.assertEqual(summary.applied_migrations, [])
        self.assertEqual(summary.skipped_migrations, [])
        self.assertEqual(summary.seeded_users, [])
        self.assertEqual(summary.verified_users, [])
        self.assertEqual(
            summary.initialized_status,
            "Campaign Operations database is initialized.",
        )

    def test_initialization_success_formatting_does_not_raise_attribute_error(self) -> None:
        old_result = SimpleNamespace(
            migrations=SimpleNamespace(applied_migrations=[], skipped_migrations=["001.sql"]),
            seed=SimpleNamespace(seeded_users=["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(old_result)

        self.assertEqual(summary.seeded_users, ["Bailey", "T", "L"])
        self.assertEqual(summary.verified_users, [])

    def test_already_initialized_database_path_loads_workspace(self) -> None:
        status = CampaignOpsSetupStatus(
            state="initialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=True,
            message="Campaign Operations database is initialized.",
        )
        with patch("app.pages.campaigns.render_header"):
            with patch("app.pages.campaigns.hide_default_streamlit_sidebar_nav"):
                with patch("app.pages.campaigns.clear_legacy_workflow_session_state"):
                    with patch("app.pages.campaigns.render_initialization_message"):
                        with patch("app.pages.campaigns.render_temporary_viewer_selector", return_value=("Bailey", "Cross-Team Dashboard")):
                            with patch("app.pages.campaigns.get_campaign_ops_setup_status", return_value=status):
                                with patch("app.pages.campaigns.render_setup_state") as render_setup:
                                    with patch("app.pages.campaigns.resolve_initialized_viewer", return_value=CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value)) as resolve_viewer:
                                        with patch("app.pages.campaigns.render_initialization_control"):
                                            with patch("app.pages.campaigns.render_section_navigation", return_value="Cross-Team Dashboard"):
                                                with patch("app.pages.campaigns.render_active_section") as render_active:
                                                    with patch("app.pages.campaigns.st.set_page_config"):
                                                        with patch("app.pages.campaigns.st.divider"):
                                                            campaigns.main()

        render_setup.assert_not_called()
        resolve_viewer.assert_called_once_with("Bailey")
        self.assertEqual(render_active.call_count, 1)
        self.assertEqual(render_active.call_args.args[0], "Cross-Team Dashboard")
        self.assertEqual(render_active.call_args.args[1], "Bailey")

    def test_initialized_seeded_users_resolve_to_expected_roles(self) -> None:
        users = [
            CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value),
            CampaignOpsUser(id="u2", display_name="T", role=UserRole.TEAM_MEMBER.value),
            CampaignOpsUser(id="u3", display_name="L", role=UserRole.TEAM_MEMBER.value),
        ]

        self.assertEqual(
            [campaigns.get_viewer_role(user.display_name, user) for user in users],
            ["Administrator", "Team Member", "Team Member"],
        )

    def test_successful_initialization_stores_summary_and_triggers_rerun(self) -> None:
        status = CampaignOpsSetupStatus(
            state="initialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=True,
            message="Campaign Operations database is initialized.",
        )
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult([], ["001.sql", "002.sql"]),
            seed=SeedResult(["Bailey", "T", "L"]),
        )
        session_state: dict[str, object] = {
            "campaign_ops_initialization_error": "old error",
            "campaign_ops_initialization_result": "old result",
            "campaign_ops_viewer_id": "old-user",
        }

        with patch.object(campaigns.st, "session_state", session_state):
            with patch("app.pages.campaigns.st.expander"):
                with patch("app.pages.campaigns.st.caption"):
                    with patch("app.pages.campaigns.st.button", return_value=True):
                        with patch(
                            "app.pages.campaigns.initialize_campaign_ops_database",
                            return_value=result,
                        ):
                            with patch(
                                "app.pages.campaigns.st.rerun",
                                side_effect=RuntimeError("rerun"),
                            ):
                                with self.assertRaisesRegex(RuntimeError, "rerun"):
                                    render_initialization_control(
                                        "Bailey",
                                        CampaignOpsUser(
                                            id="u1",
                                            display_name="Bailey",
                                            role=UserRole.ADMINISTRATOR.value,
                                        ),
                                        status,
                                    )

        self.assertNotIn("campaign_ops_initialization_error", session_state)
        self.assertNotIn("campaign_ops_initialization_result", session_state)
        self.assertNotIn("campaign_ops_viewer_id", session_state)
        summary = session_state["campaign_ops_initialization_message"]
        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(summary.skipped_migrations, ["001.sql", "002.sql"])

    def test_service_create_program_appends_activity(self) -> None:
        repository = FakeRepository()
        service = CampaignOpsService(repository=repository)
        program = service.create_program(actor_user_id="u1", program_name="Program")

        self.assertEqual(program.program_name, "Program")
        self.assertEqual(len(repository.events), 1)
        self.assertEqual(repository.events[0]["event_type"], "program_created")

    def test_prompt4a_client_validation_blank_and_duplicate(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey = repository.users[0]

        with self.assertRaises(CampaignOpsValidationError):
            service.create_client(bailey, "   ")

        client = service.create_client(bailey, "  TEST - Prompt 4A Validation  ")
        self.assertEqual(client.name, "TEST - Prompt 4A Validation")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_client(bailey, "test - prompt 4a validation")

    def test_prompt4a_team_members_cannot_create_clients_or_programs(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        team_member = repository.users[1]

        with self.assertRaises(CampaignOpsPermissionError):
            service.create_client(team_member, "Client")
        with self.assertRaises(CampaignOpsPermissionError):
            service.create_program_with_workstreams_and_assignments(
                actor=team_member,
                program_name="Program",
                new_client_name="Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=team_member.id,
                workstream_types=[WorkstreamType.INFLUENCER.value],
            )

    def test_prompt4a_program_validation_required_fields_and_dates(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey = repository.users[0]

        with self.assertRaises(CampaignOpsValidationError):
            service.create_program_with_workstreams_and_assignments(
                actor=bailey,
                program_name=" ",
                new_client_name="Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=bailey.id,
                workstream_types=[WorkstreamType.INFLUENCER.value],
            )
        with self.assertRaises(CampaignOpsValidationError):
            service.create_program_with_workstreams_and_assignments(
                actor=bailey,
                program_name="Program",
                new_client_name="Client",
                primary_workstream_type=None,
                primary_owner_user_id=bailey.id,
                workstream_types=[WorkstreamType.INFLUENCER.value],
            )
        with self.assertRaises(CampaignOpsValidationError):
            service.create_program_with_workstreams_and_assignments(
                actor=bailey,
                program_name="Program",
                new_client_name="Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=bailey.id,
                start_date=date(2026, 2, 2),
                target_end_date=date(2026, 2, 1),
                workstream_types=[WorkstreamType.INFLUENCER.value],
            )

    def test_prompt4a_program_creation_includes_primary_workflow_and_multiple_workstreams(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user, l_user = repository.users[:3]

        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="TEST - Prompt 4A Validation Program",
            new_client_name="TEST - Prompt 4A Validation",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.RETAIL_MEDIA.value],
            workstream_lead_user_ids={WorkstreamType.RETAIL_MEDIA.value: l_user.id},
        )

        self.assertEqual(repository.programs[0].id, program_id)
        self.assertEqual(
            [workstream.workstream_type for workstream in repository.workstreams],
            [WorkstreamType.INFLUENCER.value, WorkstreamType.RETAIL_MEDIA.value],
        )
        self.assertTrue(
            any(
                assignment.user_id == t_user.id
                and assignment.assignment_role == "program_owner"
                and assignment.is_primary
                for assignment in repository.assignments
            )
        )
        self.assertTrue(
            any(
                assignment.user_id == l_user.id
                and assignment.assignment_role == "workstream_lead"
                and assignment.workstream_id is not None
                for assignment in repository.assignments
            )
        )
        self.assertIn("program_created", [event["event_type"] for event in repository.events])
        self.assertIn("workstream_created", [event["event_type"] for event in repository.events])
        self.assertIn("assignment_created", [event["event_type"] for event in repository.events])

    def test_prompt4a_duplicate_workstreams_and_inactive_user_rejected(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey = repository.users[0]
        inactive = repository.users[3]

        with self.assertRaises(CampaignOpsValidationError):
            service.create_program_with_workstreams_and_assignments(
                actor=bailey,
                program_name="Program",
                new_client_name="Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=bailey.id,
                workstream_types=[WorkstreamType.RETAIL_MEDIA.value, WorkstreamType.RETAIL_MEDIA.value],
            )
        with self.assertRaises(CampaignOpsValidationError):
            service.create_program_with_workstreams_and_assignments(
                actor=bailey,
                program_name="Program",
                new_client_name="Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=inactive.id,
                workstream_types=[WorkstreamType.INFLUENCER.value],
            )

    def test_prompt4a_portfolio_and_assigned_program_filters_are_passed_to_repository(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user = repository.users[:2]

        service.list_program_portfolio(
            bailey,
            {
                "search": "test",
                "client_id": "client-1",
                "primary_workstream_type": WorkstreamType.INFLUENCER.value,
                "primary_owner_user_id": t_user.id,
                "active_state": "archived",
                "sort_by": "client",
            },
        )
        self.assertEqual(repository.last_portfolio_filters["search"], "test")
        self.assertEqual(repository.last_portfolio_filters["client_id"], "client-1")
        self.assertIsNone(repository.last_portfolio_filters["permitted_user_id"])

        service.list_program_portfolio(t_user, {"active_state": "active"})
        self.assertEqual(repository.last_portfolio_filters["permitted_user_id"], t_user.id)

        service.list_user_programs(t_user, t_user.id, {"risk_level": RiskLevel.AT_RISK.value})
        self.assertEqual(repository.last_portfolio_filters["user_id"], t_user.id)
        self.assertEqual(repository.last_portfolio_filters["risk_level"], RiskLevel.AT_RISK.value)

    def test_prompt4a_workspace_summary_enforces_assignment_permissions(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user, l_user = repository.users[:3]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )

        self.assertEqual(service.get_program_workspace_summary(t_user, program_id).program.id, program_id)
        with self.assertRaises(CampaignOpsPermissionError):
            service.get_program_workspace_summary(l_user, program_id)

    def test_prompt4a_session_keys_are_namespaced_and_viewer_switch_clears_program(self) -> None:
        self.assertTrue(all(key.startswith("campaign_ops_") for key in SESSION_KEYS))
        bailey = CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value)
        t_user = CampaignOpsUser(id="u2", display_name="T", role=UserRole.TEAM_MEMBER.value)
        state: dict[str, object] = {
            "campaign_ops_previous_viewer": "Bailey",
            "campaign_ops_selected_program_id": "program-1",
            "campaign_ops_section": "Administration",
        }

        update_viewer_state(state, "T", t_user)

        self.assertNotIn("campaign_ops_selected_program_id", state)
        self.assertEqual(state["campaign_ops_section"], "My Programs")
        self.assertEqual(state["campaign_ops_viewer_id"], "u2")

    def test_prompt4b_overview_update_validates_noop_and_activity(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user = repository.users[:2]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )
        event_count = len(repository.events)

        unchanged = service.update_program_details(bailey, program_id, program_name="Program")
        self.assertEqual(unchanged.program_name, "Program")
        self.assertEqual(len(repository.events), event_count)

        updated = service.update_program_details(
            bailey,
            program_id,
            program_name="Program Updated",
            status=ProgramStatus.ACTIVE.value,
        )
        self.assertEqual(updated.program_name, "Program Updated")
        self.assertGreater(len(repository.events), event_count)
        with self.assertRaises(CampaignOpsValidationError):
            service.update_program_details(bailey, program_id, program_name=" ")
        with self.assertRaises(CampaignOpsValidationError):
            service.update_program_details(
                bailey,
                program_id,
                start_date=date(2026, 2, 2),
                target_end_date=date(2026, 2, 1),
            )

    def test_prompt4b_team_member_overview_permission_behavior(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user, l_user = repository.users[:3]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )

        service.update_program_details(t_user, program_id, status=ProgramStatus.ACTIVE.value)
        with self.assertRaises(CampaignOpsPermissionError):
            service.update_program_details(l_user, program_id, status=ProgramStatus.COMPLETE.value)

    def test_prompt4b_workstream_lifecycle_and_duplicate_reactivation_conflict(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user = repository.users[:2]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )
        retail = service.add_workstream_to_program(bailey, program_id, WorkstreamType.RETAIL_MEDIA.value)
        edited = service.update_workstream_details(
            bailey,
            program_id,
            retail.id,
            next_action="Confirm brief",
            risk_level=RiskLevel.AT_RISK.value,
        )
        self.assertEqual(edited.next_action, "Confirm brief")
        with self.assertRaises(CampaignOpsValidationError):
            service.add_workstream_to_program(bailey, program_id, WorkstreamType.RETAIL_MEDIA.value)

        service.deactivate_workstream(bailey, program_id, retail.id)
        self.assertFalse(repository.get_workstream(retail.id).is_active)
        replacement = service.add_workstream_to_program(bailey, program_id, WorkstreamType.RETAIL_MEDIA.value)
        with self.assertRaises(CampaignOpsValidationError):
            service.reactivate_workstream(bailey, program_id, retail.id)
        service.deactivate_workstream(bailey, program_id, replacement.id)
        reactivated = service.reactivate_workstream(bailey, program_id, retail.id)
        self.assertTrue(reactivated.is_active)

    def test_prompt4b_assignment_lifecycle_and_scope_validation(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user, l_user = repository.users[:3]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )
        workstream = repository.workstreams[0]
        assignment = service.add_assignment(
            bailey,
            program_id,
            l_user.id,
            AssignmentRole.CONTRIBUTOR.value,
        )
        updated = service.update_assignment(
            bailey,
            program_id,
            assignment.id,
            l_user.id,
            AssignmentRole.REVIEWER.value,
            None,
        )
        self.assertEqual(updated.assignment_role, AssignmentRole.REVIEWER.value)
        with self.assertRaises(CampaignOpsValidationError):
            service.add_assignment(bailey, program_id, l_user.id, AssignmentRole.PROGRAM_OWNER.value, workstream.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.add_assignment(bailey, program_id, l_user.id, AssignmentRole.WORKSTREAM_LEAD.value, None)
        service.deactivate_assignment(bailey, program_id, assignment.id)
        self.assertFalse(repository.get_assignment(assignment.id).is_active)
        reactivated = service.reactivate_assignment(bailey, program_id, assignment.id)
        self.assertTrue(reactivated.is_active)

    def test_prompt4b_primary_owner_reassignment_exactly_one_active_owner(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user, l_user = repository.users[:3]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )

        summary = service.reassign_primary_program_owner(bailey, program_id, l_user.id)
        active_owners = [
            assignment
            for assignment in repository.assignments
            if assignment.program_id == program_id
            and assignment.is_active
            and assignment.is_primary
            and assignment.assignment_role == AssignmentRole.PROGRAM_OWNER.value
        ]
        self.assertEqual(len(active_owners), 1)
        self.assertEqual(active_owners[0].user_id, l_user.id)
        self.assertEqual(summary.program.id, program_id)
        with self.assertRaises(CampaignOpsPermissionError):
            service.reassign_primary_program_owner(t_user, program_id, t_user.id)

    def test_prompt4b_workstream_lead_reassignment_keeps_owner_and_assignment_in_sync(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user, l_user = repository.users[:3]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )
        workstream = repository.workstreams[0]
        updated = service.reassign_workstream_lead(bailey, program_id, workstream.id, l_user.id)
        self.assertEqual(updated.owner_user_id, l_user.id)
        self.assertTrue(
            any(
                assignment.user_id == l_user.id
                and assignment.workstream_id == workstream.id
                and assignment.assignment_role == AssignmentRole.WORKSTREAM_LEAD.value
                and assignment.is_active
                for assignment in repository.assignments
            )
        )

    def test_prompt4b_archive_reactivate_permissions_and_child_preservation(self) -> None:
        repository = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repository)
        bailey, t_user = repository.users[:2]
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=t_user.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )
        child_counts = (len(repository.workstreams), len(repository.assignments))
        with self.assertRaises(CampaignOpsPermissionError):
            service.archive_program(t_user, program_id)
        archived = service.archive_program(bailey, program_id)
        self.assertFalse(archived.is_active)
        self.assertEqual((len(repository.workstreams), len(repository.assignments)), child_counts)
        with self.assertRaises(CampaignOpsPermissionError):
            service.reactivate_program(t_user, program_id)
        reactivated = service.reactivate_program(bailey, program_id)
        self.assertTrue(reactivated.is_active)

    def test_prompt4b_activity_filter_helper_handles_event_groups(self) -> None:
        from app.campaign_ops.program_workspace import activity_matches_filter

        self.assertTrue(activity_matches_filter("program_field_changed", "Program changes"))
        self.assertTrue(activity_matches_filter("workstream_reactivated", "Workstream changes"))
        self.assertTrue(activity_matches_filter("assignment_updated", "Assignment changes"))
        self.assertTrue(activity_matches_filter("primary_owner_reassigned", "Ownership changes"))
        self.assertTrue(activity_matches_filter("program_archived", "Archive activity"))
        self.assertTrue(activity_matches_filter("task_field_changed", "Task changes"))

    def test_prompt4c_task_creation_validates_required_fields(self) -> None:
        repository, service, bailey, _t_user, _l_user, program_id, influencer, _retail = self._prompt4c_fixture()

        with self.assertRaises(CampaignOpsValidationError):
            service.create_task_record(bailey, program_id, "   ")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_task_record(
                bailey,
                program_id,
                "Task",
                assigned_user_id=repository.users[3].id,
            )
        with self.assertRaises(CampaignOpsValidationError):
            service.create_task_record(
                bailey,
                program_id,
                "Task",
                start_date=date(2026, 2, 2),
                due_date=date(2026, 2, 1),
            )
        with self.assertRaises(CampaignOpsValidationError):
            service.create_task_record(bailey, program_id, "Task", responsible_party="bad_party")

        repository.deactivate_workstream(influencer.id, actor_user_id=bailey.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_task_record(bailey, program_id, "Task", workstream_id=influencer.id)

    def test_prompt4c_task_crud_status_transitions_and_activity(self) -> None:
        repository, service, bailey, t_user, _l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        starting_events = len(repository.events)

        task = service.create_task_record(
            bailey,
            program_id,
            "TEST - Prompt 4C Lifecycle",
            workstream_id=influencer.id,
            assigned_user_id=t_user.id,
            responsible_party=WaitingOn.INTERNAL_TEAM.value,
            due_date=date(2026, 3, 2),
            start_date=date(2026, 3, 1),
            priority="High",
            sort_order=7,
        )
        self.assertEqual(task.status, TaskStatus.NOT_STARTED.value)
        self.assertIn("task_created", [event["event_type"] for event in repository.events[starting_events:]])

        event_count = len(repository.events)
        unchanged = service.update_task_details(t_user, task.id, title=task.title)
        self.assertEqual(unchanged.title, task.title)
        self.assertEqual(len(repository.events), event_count)

        task = service.update_task_details(t_user, task.id, status=TaskStatus.IN_PROGRESS.value)
        self.assertEqual(task.status, TaskStatus.IN_PROGRESS.value)
        task = service.update_task_details(t_user, task.id, status=TaskStatus.READY_FOR_INTERNAL_REVIEW.value)
        self.assertEqual(task.status, TaskStatus.READY_FOR_INTERNAL_REVIEW.value)
        task = service.update_task_details(t_user, task.id, status=TaskStatus.COMPLETED.value)
        self.assertEqual(task.status, TaskStatus.COMPLETED.value)
        self.assertIsNotNone(task.completed_at)

        with self.assertRaises(CampaignOpsValidationError):
            service.update_task_details(t_user, task.id, status=TaskStatus.IN_PROGRESS.value)

        reopened = service.reopen_task(t_user, task.id)
        self.assertEqual(reopened.status, TaskStatus.IN_PROGRESS.value)
        self.assertIsNone(reopened.completed_at)
        self.assertEqual(reopened.priority, "High")
        self.assertEqual(reopened.due_date, date(2026, 3, 2))

    def test_prompt4c_task_permissions_and_lifecycle_state(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        task = service.create_task_record(
            bailey,
            program_id,
            "TEST - Prompt 4C Permission",
            workstream_id=influencer.id,
            assigned_user_id=t_user.id,
        )

        updated = service.update_task_details(t_user, task.id, description="Assigned user can edit")
        self.assertEqual(updated.description, "Assigned user can edit")
        with self.assertRaises(CampaignOpsPermissionError):
            service.update_task_details(l_user, task.id, description="L cannot edit T task")
        with self.assertRaises(CampaignOpsPermissionError):
            service.update_task_details(t_user, task.id, assigned_user_id=l_user.id)

        service.deactivate_task_record(bailey, task.id)
        self.assertFalse(repository.get_task(task.id).is_active)
        service.reactivate_task_record(bailey, task.id)
        self.assertTrue(repository.get_task(task.id).is_active)

        service.archive_program(bailey, program_id)
        with self.assertRaises(CampaignOpsValidationError):
            service.update_task_details(bailey, task.id, description="Archived edit")

    def test_prompt4c_user_task_visibility_and_program_task_listing(self) -> None:
        _repository, service, bailey, t_user, l_user, program_id, influencer, retail = self._prompt4c_fixture()
        t_task = service.create_task_record(
            bailey,
            program_id,
            "TEST - Prompt 4C T",
            workstream_id=influencer.id,
            assigned_user_id=t_user.id,
        )
        l_task = service.create_task_record(
            bailey,
            program_id,
            "TEST - Prompt 4C L",
            workstream_id=retail.id,
            assigned_user_id=l_user.id,
        )
        service.create_task_record(bailey, program_id, "TEST - Prompt 4C Unassigned")

        program_rows = service.list_program_tasks(bailey, program_id)
        self.assertEqual({row.id for row in program_rows}, {t_task.id, l_task.id, _repository.tasks[-1].id})
        self.assertEqual([row.id for row in service.list_user_tasks(t_user, t_user.id)], [t_task.id])
        self.assertEqual([row.id for row in service.list_user_tasks(l_user, l_user.id)], [l_task.id])
        with self.assertRaises(CampaignOpsPermissionError):
            service.list_user_tasks(t_user, l_user.id)

    def test_prompt4c_my_work_grouping_is_deterministic_and_single_bucket(self) -> None:
        _repository, service, _bailey, _t_user, _l_user, _program_id, _influencer, _retail = self._prompt4c_fixture()
        today = date(2026, 7, 27)
        base = TaskListRow(
            id="task-1",
            program_id="program-1",
            program_name="Program",
            client_name="Client",
            title="Base",
            description=None,
            workstream_id=None,
            workstream_type=None,
            assigned_user_id="user-1",
            assigned_user_name="T",
            responsible_party=WaitingOn.INTERNAL_TEAM.value,
            status=TaskStatus.IN_PROGRESS.value,
            risk_level=RiskLevel.UNRATED.value,
            waiting_on=WaitingOn.NONE.value,
            due_date=None,
            start_date=None,
            completed_at=None,
            hard_deadline=False,
            priority=None,
            sort_order=0,
            is_active=True,
            created_at=None,
            updated_at=None,
        )
        tasks = [
            replace(base, id="overdue", title="Overdue", due_date=today - timedelta(days=1)),
            replace(base, id="today", title="Today", due_date=today),
            replace(base, id="week", title="Week", due_date=today + timedelta(days=2)),
            replace(base, id="waiting", title="Waiting", waiting_on=WaitingOn.CLIENT.value),
            replace(base, id="remaining", title="Remaining"),
            replace(
                base,
                id="completed",
                title="Completed",
                status=TaskStatus.COMPLETED.value,
                completed_at=datetime(2026, 7, 26, tzinfo=UTC),
            ),
            replace(
                base,
                id="old-completed",
                title="Old Completed",
                status=TaskStatus.COMPLETED.value,
                completed_at=datetime(2026, 7, 1, tzinfo=UTC),
            ),
            replace(base, id="inactive", title="Inactive", is_active=False),
        ]

        groups = service.group_user_tasks(tasks, today=today)

        self.assertEqual([task.id for task in groups["Overdue"]], ["overdue"])
        self.assertEqual([task.id for task in groups["Due today"]], ["today"])
        self.assertEqual([task.id for task in groups["Due this week"]], ["week"])
        self.assertEqual([task.id for task in groups["Waiting"]], ["waiting"])
        self.assertEqual([task.id for task in groups["Remaining open"]], ["remaining"])
        self.assertEqual([task.id for task in groups["Recently completed"]], ["completed"])
        grouped_ids = [task.id for bucket in groups.values() for task in bucket]
        self.assertEqual(len(grouped_ids), len(set(grouped_ids)))
        self.assertNotIn("old-completed", grouped_ids)
        self.assertNotIn("inactive", grouped_ids)

    def test_prompt4c_task_table_rows_formats_waiting_fields(self) -> None:
        from app.campaign_ops.task_views import task_table_rows

        task = TaskListRow(
            id="task-1",
            program_id="program-1",
            program_name="Program",
            client_name="Client",
            title="Task",
            description=None,
            workstream_id=None,
            workstream_type=None,
            assigned_user_id=None,
            assigned_user_name=None,
            responsible_party=WaitingOn.INTERNAL_TEAM.value,
            status=TaskStatus.NOT_STARTED.value,
            risk_level=RiskLevel.UNRATED.value,
            waiting_on=WaitingOn.CLIENT.value,
            due_date=None,
            start_date=None,
            completed_at=None,
            hard_deadline=False,
            priority=None,
            sort_order=0,
            is_active=True,
            created_at=None,
            updated_at=None,
        )

        rows = task_table_rows([task])

        self.assertEqual(rows[0]["Responsible party"], "Internal Team")
        self.assertEqual(rows[0]["Waiting on"], "Client")

    def test_prompt4d_milestone_validation_lifecycle_permissions_and_activity(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, retail = self._prompt4c_fixture()

        with self.assertRaises(CampaignOpsValidationError):
            service.create_milestone(bailey, program_id, " ")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_milestone(bailey, program_id, "Bad dates", start_date=date(2026, 8, 2), target_date=date(2026, 8, 1))
        with self.assertRaises(CampaignOpsValidationError):
            service.create_milestone(bailey, program_id, "Bad owner", owner_user_id=repository.users[3].id)
        repository.deactivate_workstream(retail.id, actor_user_id=bailey.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_milestone(bailey, program_id, "Inactive workstream", workstream_id=retail.id)
        repository.reactivate_workstream(retail.id, actor_user_id=bailey.id)

        exact = service.create_milestone(
            bailey,
            program_id,
            "TEST - Prompt 4D Exact",
            workstream_id=influencer.id,
            owner_user_id=t_user.id,
            start_date=date(2026, 8, 5),
            target_date=date(2026, 8, 5),
            end_date=date(2026, 8, 5),
            hard_deadline=True,
        )
        undated = service.create_milestone(bailey, program_id, "TEST - Prompt 4D Undated")
        self.assertIsNone(undated.target_date)
        event_count = len(repository.events)
        unchanged = service.update_milestone_details(t_user, exact.id, title=exact.title)
        self.assertEqual(unchanged.title, exact.title)
        self.assertEqual(len(repository.events), event_count)

        updated = service.update_milestone_details(t_user, exact.id, status=TaskStatus.IN_PROGRESS.value)
        self.assertEqual(updated.status, TaskStatus.IN_PROGRESS.value)
        completed = service.complete_milestone(t_user, exact.id)
        self.assertEqual(completed.status, TaskStatus.COMPLETED.value)
        self.assertIsNotNone(completed.completed_at)
        reopened = service.reopen_milestone(t_user, exact.id)
        self.assertEqual(reopened.status, TaskStatus.IN_PROGRESS.value)
        self.assertIsNone(reopened.completed_at)
        with self.assertRaises(CampaignOpsPermissionError):
            service.update_milestone_details(l_user, exact.id, title="No access")
        with self.assertRaises(CampaignOpsPermissionError):
            service.deactivate_milestone(t_user, exact.id)
        service.deactivate_milestone(bailey, exact.id)
        self.assertFalse(repository.get_milestone(exact.id).is_active)
        self.assertEqual([row.id for row in service.list_program_milestones(bailey, program_id)], [undated.id])
        service.reactivate_milestone(bailey, exact.id)
        rows = service.list_program_milestones(bailey, program_id)
        self.assertEqual({row.id for row in rows}, {exact.id, undated.id})
        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("milestone_created", event_types)
        self.assertIn("milestone_reopened", event_types)
        self.assertIn("milestone_deactivated", event_types)

    def test_prompt4d_timeline_ordering_and_due_state_helpers(self) -> None:
        from app.campaign_ops.timeline_views import milestone_due_state, sort_milestones

        base = MilestoneListRow(
            id="base",
            program_id="program-1",
            title="Base",
            status=TaskStatus.IN_PROGRESS.value,
            workstream_id=None,
            workstream_type=None,
            milestone_type=None,
            target_date=None,
            start_date=None,
            end_date=None,
            owner_user_id=None,
            owner_user_name=None,
            hard_deadline=False,
            completed_at=None,
            is_highlighted=False,
            is_active=True,
            created_at=None,
            updated_at=None,
        )
        overdue = replace(base, id="overdue", title="Overdue", target_date=date(2026, 7, 30))
        today = replace(base, id="today", title="Today", target_date=date(2026, 7, 31), hard_deadline=True)
        start_only = replace(base, id="start", title="Start", start_date=date(2026, 8, 1))
        undated = replace(base, id="undated", title="Undated")
        self.assertEqual([row.id for row in sort_milestones([undated, start_only, today], "best_date")], ["today", "start", "undated"])
        self.assertEqual(milestone_due_state(overdue, today=date(2026, 7, 31)), "Overdue")
        self.assertEqual(milestone_due_state(today, today=date(2026, 7, 31)), "Due today")
        self.assertEqual(milestone_due_state(replace(base, status=TaskStatus.BLOCKED.value)), "Blocked")
        self.assertEqual(milestone_due_state(undated, today=date(2026, 7, 31)), "Undated")

    def test_prompt4d_resource_validation_lifecycle_and_missing_required_indicator(self) -> None:
        from app.campaign_ops.resource_views import sanitize_link, url_status

        repository, service, bailey, t_user, _l_user, program_id, influencer, retail = self._prompt4c_fixture()
        with self.assertRaises(CampaignOpsValidationError):
            service.create_resource(bailey, program_id, " ", "Brief")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_resource(bailey, program_id, "Bad URL", "Brief", url="notaurl")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_resource(bailey, program_id, "Bad scheme", "Brief", url="javascript:alert(1)")
        repository.deactivate_workstream(retail.id, actor_user_id=bailey.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_resource(bailey, program_id, "Inactive", "Brief", workstream_id=retail.id)
        repository.reactivate_workstream(retail.id, actor_user_id=bailey.id)

        missing = service.create_resource(bailey, program_id, "TEST - Prompt 4D Required", "Brief", is_required=True)
        row = service.list_program_resources(bailey, program_id)[0]
        self.assertEqual(row.id, missing.id)
        self.assertEqual(url_status(row), "Missing required URL")
        resource = service.create_resource(bailey, program_id, "TEST - Prompt 4D Link", "Live Tracker", workstream_id=influencer.id, url="https://user:pass@example.com/path")
        self.assertEqual(sanitize_link(resource.url or ""), "https://example.com/path")
        event_count = len(repository.events)
        unchanged = service.update_resource_details(t_user, resource.id, title=resource.title)
        self.assertEqual(unchanged.title, resource.title)
        self.assertEqual(len(repository.events), event_count)
        edited = service.update_resource_details(t_user, resource.id, notes="Updated notes", url="https://example.com/next")
        self.assertEqual(edited.notes, "Updated notes")
        with self.assertRaises(CampaignOpsPermissionError):
            service.deactivate_resource(t_user, resource.id)
        service.deactivate_resource(bailey, resource.id)
        self.assertFalse(repository.get_resource(resource.id).is_active)
        service.reactivate_resource(bailey, resource.id)
        self.assertTrue(repository.get_resource(resource.id).is_active)

    def test_prompt4d_notes_append_only_visibility_scope_and_activity(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, retail = self._prompt4c_fixture()
        task = service.create_task_record(bailey, program_id, "TEST - Prompt 4D Task", workstream_id=retail.id, assigned_user_id=l_user.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.append_program_note(bailey, program_id, " ")
        with self.assertRaises(CampaignOpsValidationError):
            service.append_program_note(bailey, program_id, "Bad association", workstream_id=influencer.id, task_id=task.id)

        program_note = service.append_program_note(bailey, program_id, "TEST - Prompt 4D Program note")
        workstream_note = service.append_program_note(t_user, program_id, "TEST - Prompt 4D Workstream note", workstream_id=influencer.id)
        task_note = service.append_program_note(l_user, program_id, "TEST - Prompt 4D Task note", workstream_id=retail.id, task_id=task.id)
        internal = service.append_program_note(bailey, program_id, "TEST - Prompt 4D Internal note", is_internal=True)
        self.assertEqual(program_note.author_user_id, bailey.id)
        self.assertEqual(workstream_note.workstream_id, influencer.id)
        self.assertEqual(task_note.task_id, task.id)
        self.assertTrue(internal.is_internal)
        self.assertEqual(len(repository.notes), 4)
        notes_for_t = service.list_program_notes(t_user, program_id)
        self.assertTrue(any(note.id == internal.id for note in notes_for_t))

        other_program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="Other Program",
            new_client_name="Other Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            primary_owner_user_id=bailey.id,
            workstream_types=[WorkstreamType.INFLUENCER.value],
        )
        with self.assertRaises(CampaignOpsPermissionError):
            service.append_program_note(t_user, other_program_id, "No access")
        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("note_added", event_types)
        self.assertIn("internal_note_added", event_types)

    def test_prompt5a_am_mapping_is_centralized_and_normalized(self) -> None:
        self.assertEqual(normalize_am_name("Taylor"), "T")
        self.assertEqual(normalize_am_name(" Lauren "), "L")
        self.assertEqual(normalize_am_name("bailey"), "Bailey")
        self.assertEqual(normalize_am_name(" t "), "T")
        self.assertEqual(normalize_am_name("l"), "L")
        with self.assertRaises(CampaignOpsValidationError):
            normalize_am_name("Unknown")

    def test_prompt5a_request_validation_crud_lifecycle_and_activity(self) -> None:
        from core.campaign_ops.reporting_requests import (
            REQUEST_CATEGORY_REPORT,
            REQUEST_CATEGORY_SURVEY,
            REQUEST_STATUS_COMPLETED,
            REQUEST_STATUS_DELIVERED,
        )

        repository, service, bailey, t_user, l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        with self.assertRaises(CampaignOpsValidationError):
            service.create_reporting_request(bailey, request_category=REQUEST_CATEGORY_SURVEY, request_type=" ", program_id=program_id, am_name="Taylor")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_reporting_request(bailey, request_category=REQUEST_CATEGORY_SURVEY, request_type="EOP Survey", am_name="Taylor")
        with self.assertRaises(CampaignOpsError):
            service.create_reporting_request(bailey, request_category=REQUEST_CATEGORY_SURVEY, request_type="EOP Survey", program_id="missing", am_name="Taylor")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_reporting_request(bailey, request_category=REQUEST_CATEGORY_SURVEY, request_type="EOP Survey", program_id=program_id, am_name="Taylor", brief_url="javascript:bad")

        survey = service.create_reporting_request(
            bailey,
            request_category=REQUEST_CATEGORY_SURVEY,
            request_type="TEST - Prompt 5A EOP Survey",
            program_id=program_id,
            workstream_id=influencer.id,
            am_name="Taylor",
            assigned_user_id=t_user.id,
            due_date=date(2026, 8, 10),
            brief_url="https://example.com/brief",
            brief_status_text="Sent to Tori",
            review_required=True,
            questions_requested="overall performance",
            special_requests="comment analysis slide",
        )
        self.assertEqual(survey.am_user_id, t_user.id)
        self.assertEqual(survey.status, "ready_for_review")
        report = service.create_reporting_request(
            bailey,
            request_category=REQUEST_CATEGORY_REPORT,
            request_type="TEST - Prompt 5A Program Recap",
            program_id=program_id,
            am_name="Lauren",
            due_date=date(2026, 8, 11),
            recap_date_with_client=date(2026, 8, 12),
            recap_date_text="Week of 8/10",
            approval_required=True,
            special_requests="same format as previous VeSync recaps",
        )
        self.assertEqual(report.am_user_id, l_user.id)
        self.assertEqual(report.status, "waiting_for_approval")

        event_count = len(repository.events)
        unchanged = service.update_reporting_request(bailey, survey.id, request_type=survey.request_type)
        self.assertEqual(unchanged.request_type, survey.request_type)
        self.assertEqual(len(repository.events), event_count)
        service.update_reporting_request(bailey, survey.id, due_date=date(2026, 8, 12))
        service.update_reporting_request(bailey, survey.id, questions_requested="performance broken out by retailer")
        service.update_reporting_request(bailey, survey.id, special_requests="brand ambassador information")
        delivered = service.set_request_delivered(bailey, survey.id, True)
        self.assertTrue(delivered.delivered)
        self.assertEqual(delivered.status, REQUEST_STATUS_DELIVERED)
        reviewed = service.set_request_review_state(bailey, survey.id, True, True)
        self.assertTrue(reviewed.review_complete)
        approved = service.set_request_approval_state(bailey, report.id, True, True)
        self.assertTrue(approved.approved)
        completed = service.update_reporting_request(bailey, report.id, status=REQUEST_STATUS_COMPLETED, delivered=True, approval_required=True, approved=True)
        self.assertIsNotNone(completed.completed_at)
        reopened = service.update_reporting_request(bailey, report.id, status=REQUEST_STATUS_DELIVERED)
        self.assertIsNone(reopened.completed_at)
        service.deactivate_reporting_request(bailey, survey.id)
        self.assertFalse(repository.get_reporting_request(survey.id).is_active)
        service.reactivate_reporting_request(bailey, survey.id)
        self.assertTrue(repository.get_reporting_request(survey.id).is_active)
        rows = service.list_reporting_requests(bailey)
        self.assertEqual({row.id for row in rows}, {survey.id, report.id})
        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("reporting_request_created", event_types)
        self.assertIn("reporting_request_due_date_changed", event_types)
        self.assertTrue(any(event_type.startswith("reporting_request_delivered") for event_type in event_types))
        self.assertIn("reporting_request_questions_requested_changed", event_types)
        self.assertIn("reporting_request_special_requests_changed", event_types)

    def test_prompt5a_display_column_order_and_labels(self) -> None:
        from app.campaign_ops.reporting_requests.formatting import (
            REPORTING_COLUMNS,
            SURVEY_COLUMNS,
            reporting_request_rows,
            survey_request_rows,
        )
        from core.campaign_ops.reporting_requests import REQUEST_CATEGORY_REPORT, REQUEST_CATEGORY_SURVEY

        base = ReportingRequestListRow(
            id="request-1",
            program_id="program-1",
            program_name="Program",
            client_name="Client",
            primary_workstream_type=WorkstreamType.INFLUENCER.value,
            request_category=REQUEST_CATEGORY_SURVEY,
            request_type="EOP Survey",
            am_user_id="user-1",
            am_display_name="T",
            assigned_user_id=None,
            assigned_display_name=None,
            workstream_id=None,
            workstream_type=None,
            due_date=date(2026, 8, 10),
            recap_date_with_client=None,
            recap_date_text=None,
            brief_url=None,
            brief_status_text="Sent to Tori",
            delivered=False,
            review_required=True,
            review_complete=False,
            approval_required=False,
            approved=False,
            questions_requested="Questions You'd Like Included",
            special_requests="Special Requests",
            status="requested",
            risk=RiskLevel.UNRATED.value,
            waiting_on=None,
            completed_at=None,
            is_active=True,
            created_at=None,
            updated_at=None,
        )
        survey_rows = survey_request_rows([base])
        self.assertEqual(list(survey_rows[0]), SURVEY_COLUMNS)
        report = replace(
            base,
            id="request-2",
            request_category=REQUEST_CATEGORY_REPORT,
            request_type="Program Recap",
            recap_date_text="Week of 8/10",
            review_required=False,
            approval_required=True,
        )
        reporting_rows = reporting_request_rows([report])
        self.assertEqual(list(reporting_rows[0]), REPORTING_COLUMNS)
        self.assertIn("Questions You'd Like Included", base.questions_requested or "")
        self.assertIn("Special Requests", base.special_requests or "")

    def test_prompt5a_state_keys_are_namespaced_and_stale_request_clears(self) -> None:
        self.assertTrue(all(key.startswith("campaign_ops_") for key in SESSION_KEYS))
        state: dict[str, object] = {"campaign_ops_selected_request_id": "missing"}
        visible_ids: set[str] = set()
        if state.get("campaign_ops_selected_request_id") not in visible_ids:
            state.pop("campaign_ops_selected_request_id", None)
        self.assertNotIn("campaign_ops_selected_request_id", state)

    def test_prompt5b_insights_validation_crud_and_activity(self) -> None:
        repository, service, bailey, t_user, _l_user, program_id, influencer, retail = self._prompt4c_fixture()
        with self.assertRaises(CampaignOpsValidationError):
            service.create_insights_project(bailey, program_id=program_id, project_title=" ")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_insights_project(bailey, project_title="TEST - Missing Program")
        with self.assertRaises(CampaignOpsError):
            service.create_insights_project(bailey, program_id="missing", project_title="TEST - Missing Program")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_insights_project(bailey, program_id=program_id, project_title="Bad owner", owner_user_id=repository.users[3].id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_insights_project(bailey, program_id=program_id, project_title="Bad status", insights_status="bad")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_insights_project(bailey, program_id=program_id, project_title="Bad cost", total_program_cost=-1)
        repository.deactivate_workstream(retail.id, actor_user_id=bailey.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_insights_project(bailey, program_id=program_id, workstream_id=retail.id, project_title="Inactive workstream")
        repository.reactivate_workstream(retail.id, actor_user_id=bailey.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_insights_project(
                bailey,
                program_id=program_id,
                workstream_id=influencer.id,
                project_title="Bad resource URL",
                initial_resources={"Tracksheet": "javascript:bad"},
            )

        project = service.create_insights_project(
            bailey,
            program_id=program_id,
            project_title="TEST - Insights Project",
            job_number="JOB-123",
            insights_status=INSIGHTS_STATUS_DRAFTING_SURVEY,
            latest_update="Drafting survey",
            total_program_cost=1200,
            sample_size=300,
            budget=1500,
            owner_user_id=t_user.id,
            initial_resources={
                "Tracksheet": "https://example.com/tracksheet",
                "Results Deck": "https://example.com/deck",
                "Raw Data": "https://example.com/raw",
            },
            initial_objectives=["Assess overall performance", "Understand retailer breakouts"],
        )
        self.assertEqual(project.owner_user_id, t_user.id)
        self.assertEqual(project.insights_status, INSIGHTS_STATUS_DRAFTING_SURVEY)
        self.assertEqual(len(repository.insights_objectives), 2)
        self.assertTrue(any(workstream.workstream_type == WorkstreamType.INSIGHTS.value for workstream in repository.workstreams))

        event_count = len(repository.events)
        unchanged = service.update_insights_project(bailey, project.id, project_title=project.project_title)
        self.assertEqual(unchanged.project_title, project.project_title)
        self.assertEqual(len(repository.events), event_count)
        updated = service.update_insights_project(
            bailey,
            project.id,
            project_title="TEST - Insights Project Updated",
            latest_update="Client review",
            insights_status="client_review",
        )
        self.assertEqual(updated.project_title, "TEST - Insights Project Updated")
        self.assertEqual(updated.latest_update, "Client review")
        service.deactivate_insights_project(bailey, project.id)
        self.assertFalse(repository.get_insights_project(project.id).is_active)
        self.assertEqual(service.list_insights_projects(bailey), [])
        service.reactivate_insights_project(bailey, project.id)
        self.assertTrue(repository.get_insights_project(project.id).is_active)

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("insights_project_created", event_types)
        self.assertIn("insights_project_project_title_changed", event_types)
        self.assertIn("insights_project_latest_update_changed", event_types)
        self.assertIn("insights_project_deactivated", event_types)
        self.assertIn("insights_project_reactivated", event_types)

    def test_prompt5b_insights_portfolio_timeline_objectives_and_resources(self) -> None:
        from app.campaign_ops.insights.formatting import PORTFOLIO_COLUMNS, portfolio_rows, timeline_date_label

        repository, service, bailey, t_user, _l_user, program_id, _influencer, _retail = self._prompt4c_fixture()
        project = service.create_insights_project(
            bailey,
            program_id=program_id,
            project_title="TEST - Portfolio Project",
            insights_status=INSIGHTS_STATUS_NOT_STARTED,
            owner_user_id=t_user.id,
        )
        exact = service.create_milestone(
            bailey,
            program_id,
            "TEST - Exact Date",
            workstream_id=project.workstream_id,
            milestone_type="Insights",
            target_date=date(2026, 8, 10),
            is_highlighted=True,
        )
        ranged = service.create_milestone(
            bailey,
            program_id,
            "TEST - Date Range",
            workstream_id=project.workstream_id,
            milestone_type="Insights",
            start_date=date(2026, 8, 12),
            end_date=date(2026, 8, 14),
        )
        undated = service.create_milestone(bailey, program_id, "TEST - Undated", workstream_id=project.workstream_id, milestone_type="Insights")
        service.create_resource(bailey, program_id, "Tracksheet", resource_type="Tracksheet", workstream_id=project.workstream_id, url="https://example.com/tracksheet")
        service.create_resource(bailey, program_id, "Results Deck", resource_type="Results Deck", workstream_id=project.workstream_id, url="https://example.com/deck")
        service.create_resource(bailey, program_id, "Raw Data Key", resource_type="Raw Data Key", workstream_id=project.workstream_id, url="https://example.com/raw-key")

        rows = service.list_insights_projects(bailey)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].next_milestone, exact.title)
        self.assertEqual(rows[0].tracksheet_url, "https://example.com/tracksheet")
        self.assertEqual(rows[0].results_deck_url, "https://example.com/deck")
        self.assertEqual(rows[0].raw_data_url, "https://example.com/raw-key")
        display_rows = portfolio_rows(rows)
        self.assertEqual(list(display_rows[0]), PORTFOLIO_COLUMNS)
        self.assertEqual(display_rows[0]["Tracksheet"], "Available")
        self.assertEqual(timeline_date_label(service.list_program_milestones(bailey, program_id)[0]), "8/10")
        self.assertEqual(timeline_date_label(ranged), "8/12 - 8/14")
        self.assertEqual(timeline_date_label(undated), "-")
        self.assertTrue(repository.get_milestone(exact.id).is_highlighted)
        service.update_milestone_details(bailey, exact.id, is_highlighted=False)
        self.assertFalse(repository.get_milestone(exact.id).is_highlighted)
        service.complete_milestone(bailey, exact.id)
        self.assertIsNotNone(repository.get_milestone(exact.id).completed_at)
        service.reopen_milestone(bailey, exact.id)
        self.assertIsNone(repository.get_milestone(exact.id).completed_at)

        objective = service.add_insights_objective(bailey, project.id, "Identify purchase barriers", sort_order=2)
        changed = service.update_insights_objective(bailey, project.id, objective.id, "Identify purchase drivers", 1)
        self.assertEqual(changed.sort_order, 1)
        service.deactivate_insights_objective(bailey, project.id, objective.id)
        self.assertEqual([item.id for item in service.list_insights_objectives(bailey, project.id)], repository.insights_objectives[:0])
        service.reactivate_insights_objective(bailey, project.id, objective.id)
        self.assertIn(objective.id, [item.id for item in service.list_insights_objectives(bailey, project.id)])

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("resource_created", event_types)
        self.assertIn("milestone_field_changed", event_types)
        self.assertIn("milestone_reopened", event_types)
        self.assertIn("insights_objective_created", event_types)
        self.assertIn("insights_objective_updated", event_types)
        self.assertIn("insights_objective_deactivated", event_types)
        self.assertIn("insights_objective_reactivated", event_types)

    def test_prompt5b_state_keys_are_namespaced_and_stale_project_clears(self) -> None:
        self.assertTrue(all(key.startswith("campaign_ops_") for key in SESSION_KEYS))
        self.assertIn("campaign_ops_selected_insights_project_id", SESSION_KEYS)
        state: dict[str, object] = {"campaign_ops_selected_insights_project_id": "missing"}
        visible_ids: set[str] = set()
        if state.get("campaign_ops_selected_insights_project_id") not in visible_ids:
            state.pop("campaign_ops_selected_insights_project_id", None)
        self.assertNotIn("campaign_ops_selected_insights_project_id", state)

    def test_prompt6_retail_media_campaign_validation_crud_and_activity(self) -> None:
        repository, service, bailey, t_user, _l_user, program_id, _influencer, retail = self._prompt4c_fixture()
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, campaign_title="Missing program")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, campaign_title=" ")
        with self.assertRaises(CampaignOpsError):
            service.create_retail_media_campaign(bailey, program_id="missing", campaign_title="Missing")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, campaign_title="Inactive owner", owner_user_id=repository.users[3].id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, campaign_title="Bad budget", overall_budget=-1)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, campaign_title="Bad spend", total_spend=-1)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, campaign_title="Bad dates", launch_date=date(2026, 9, 1), wrap_date=date(2026, 8, 1))
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, campaign_title="Paused", is_paused=True)
        repository.deactivate_workstream(retail.id, actor_user_id=bailey.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, workstream_id=retail.id, campaign_title="Inactive workstream")
        repository.reactivate_workstream(retail.id, actor_user_id=bailey.id)

        campaign = service.create_retail_media_campaign(
            bailey,
            program_id=program_id,
            campaign_title="TEST - Retail Media Campaign",
            owner_user_id=t_user.id,
            retail_media_status=RETAIL_MEDIA_STATUS_PLANNING,
            latest_update="Creative is with client",
            waiting_on="Client",
            launch_date=date(2026, 8, 10),
            wrap_date=date(2026, 9, 10),
            reporting_cadence="WPSR Weekly",
            overall_budget=1000,
            total_spend=200,
            initial_channels=[{"channel_type": "Onsite Display", "budget": 600, "spend_to_date": 100}],
            initial_resources={"Tracksheet": "https://example.com/tracksheet", "Budget Tracker": "https://example.com/budget"},
        )
        self.assertEqual(campaign.owner_user_id, t_user.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_campaign(bailey, program_id=program_id, campaign_title="TEST - Retail Media Campaign")
        event_count = len(repository.events)
        unchanged = service.update_retail_media_campaign(bailey, campaign.id, campaign_title=campaign.campaign_title)
        self.assertEqual(unchanged.campaign_title, campaign.campaign_title)
        self.assertEqual(len(repository.events), event_count)
        updated = service.update_retail_media_campaign(bailey, campaign.id, retail_media_status=RETAIL_MEDIA_STATUS_LIVE, latest_update="Onsite and offsite live", total_spend=1200, is_paused=True, pause_reason="Paused until further notice")
        self.assertEqual(updated.retail_media_status, RETAIL_MEDIA_STATUS_LIVE)
        self.assertTrue(updated.is_paused)
        service.deactivate_retail_media_campaign(bailey, campaign.id)
        self.assertFalse(repository.get_retail_media_campaign(campaign.id).is_active)
        service.reactivate_retail_media_campaign(bailey, campaign.id)
        self.assertTrue(repository.get_retail_media_campaign(campaign.id).is_active)
        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("retail_media_campaign_created", event_types)
        self.assertIn("retail_media_campaign_latest_update_changed", event_types)
        self.assertIn("retail_media_campaign_deactivated", event_types)
        self.assertIn("retail_media_campaign_reactivated", event_types)

    def test_prompt6_retail_media_children_portfolio_budget_and_state(self) -> None:
        from app.campaign_ops.retail_media.formatting import PORTFOLIO_COLUMNS, portfolio_rows

        repository, service, bailey, t_user, _l_user, program_id, _influencer, _retail = self._prompt4c_fixture()
        campaign = service.create_retail_media_campaign(
            bailey,
            program_id=program_id,
            campaign_title="TEST - Retail Media Campaign",
            owner_user_id=t_user.id,
            overall_budget=1000,
            total_spend=1200,
            initial_resources={"Optimization Log": "https://example.com/opt"},
        )
        onsite = service.create_retail_media_channel(bailey, campaign.id, channel_type="Onsite Display", budget=600, spend_to_date=700)
        offsite = service.create_retail_media_channel(bailey, campaign.id, channel_type="Offsite Display", budget=400, spend_to_date=300)
        search = service.create_retail_media_channel(bailey, campaign.id, channel_type="Sponsored Search", budget=300, spend_to_date=100)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_channel(bailey, campaign.id, channel_type="Onsite Display")
        with self.assertRaises(CampaignOpsValidationError):
            service.update_retail_media_channel(bailey, campaign.id, offsite.id, channel_type="Offsite Display", budget=-1)
        service.update_retail_media_channel(bailey, campaign.id, offsite.id, channel_type="Offsite Display", spend_to_date=350)
        service.deactivate_retail_media_channel(bailey, campaign.id, search.id)
        service.reactivate_retail_media_channel(bailey, campaign.id, search.id)

        exact = service.create_retail_media_activation(bailey, campaign.id, activation_name="BTS Onsite Display", channel_id=onsite.id, start_date=date(2026, 8, 10))
        ranged = service.create_retail_media_activation(bailey, campaign.id, activation_name="Summer Campaign Flight", channel_id=offsite.id, start_date=date(2026, 8, 12), end_date=date(2026, 8, 20), hard_deadline=True)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_retail_media_activation(bailey, campaign.id, activation_name="Bad dates", start_date=date(2026, 9, 1), end_date=date(2026, 8, 1))
        completed = service.complete_retail_media_activation(bailey, campaign.id, exact.id)
        self.assertIsNotNone(completed.completed_at)
        reopened = service.reopen_retail_media_activation(bailey, campaign.id, exact.id)
        self.assertIsNone(reopened.completed_at)
        service.deactivate_retail_media_activation(bailey, campaign.id, ranged.id)
        service.reactivate_retail_media_activation(bailey, campaign.id, ranged.id)

        creative = service.create_retail_media_creative(bailey, campaign.id, creative_name="Ad creative", channel_id=onsite.id, approval_status="client_review", submission_status="ready_to_submit")
        submitted = service.mark_retail_media_creative_submitted(bailey, campaign.id, creative.id, submitted_date=date(2026, 8, 5))
        self.assertEqual(submitted.submission_status, "submitted")
        approved = service.mark_retail_media_creative_approved(bailey, campaign.id, creative.id, approved_date=date(2026, 8, 6))
        self.assertEqual(approved.approval_status, "approved")
        service.deactivate_retail_media_creative(bailey, campaign.id, creative.id)
        service.reactivate_retail_media_creative(bailey, campaign.id, creative.id)

        opt1 = service.create_retail_media_optimization(bailey, campaign.id, date(2026, 8, 15), "A250 optimizations made", channel_id=onsite.id)
        opt2 = service.create_retail_media_optimization(bailey, campaign.id, date(2026, 8, 16), "Adjusted search strategy", channel_id=search.id)
        self.assertEqual([row.id for row in service.list_retail_media_optimizations(bailey, campaign.id)], [opt2.id, opt1.id])
        service.update_retail_media_optimization(bailey, campaign.id, opt1.id, update_text="Updated budget allocation")
        service.deactivate_retail_media_optimization(bailey, campaign.id, opt2.id)
        service.reactivate_retail_media_optimization(bailey, campaign.id, opt2.id)

        milestone = service.create_milestone(bailey, program_id, "Campaign launch", workstream_id=campaign.workstream_id, milestone_type="Retail Media", target_date=date(2026, 8, 10))
        service.complete_milestone(bailey, milestone.id)
        service.reopen_milestone(bailey, milestone.id)
        service.create_resource(bailey, program_id, "RM Strategy", resource_type="RM Strategy", workstream_id=campaign.workstream_id, url=None)

        detail = service.get_retail_media_campaign_detail(bailey, campaign.id)
        rows = portfolio_rows([detail])
        self.assertEqual(list(rows[0]), PORTFOLIO_COLUMNS)
        self.assertIn("Onsite Display", detail.channel_mix)
        self.assertEqual(detail.channel_budget_total, 1300)
        self.assertEqual(detail.channel_spend_total, 1150)
        self.assertEqual(detail.optimization_log_url, "https://example.com/opt")
        summary = service.retail_media_budget_summary(detail, service.list_retail_media_channels(bailey, campaign.id))
        self.assertEqual(summary["remaining"], -200)
        self.assertTrue(summary["over_budget"])
        self.assertGreater(summary["spend_percentage"], 100)
        self.assertIn("campaign_ops_selected_retail_media_campaign_id", SESSION_KEYS)
        self.assertTrue(all(key.startswith("campaign_ops_") for key in SESSION_KEYS))
        state: dict[str, object] = {"campaign_ops_selected_retail_media_campaign_id": "missing"}
        if state.get("campaign_ops_selected_retail_media_campaign_id") not in {campaign.id}:
            state.pop("campaign_ops_selected_retail_media_campaign_id", None)
        self.assertNotIn("campaign_ops_selected_retail_media_campaign_id", state)
        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("retail_media_channel_created", event_types)
        self.assertIn("retail_media_activation_created", event_types)
        self.assertIn("retail_media_creative_created", event_types)
        self.assertIn("retail_media_optimization_created", event_types)

    def test_prompt7_content_program_validation_crud_and_activity(self) -> None:
        repository, service, bailey, t_user, _l_user, program_id, _influencer, retail = self._prompt4c_fixture()

        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(bailey, content_program_title="Missing program")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(bailey, program_id=program_id, content_program_title=" ")
        with self.assertRaises(CampaignOpsNotFoundError):
            service.create_content_program(bailey, program_id="missing", content_program_title="Missing")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(bailey, program_id=program_id, content_program_title="Inactive owner", owner_user_id=repository.users[3].id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(bailey, program_id=program_id, content_program_title="Bad total", total_sku_count=-1)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(bailey, program_id=program_id, content_program_title="Bad dates", monitoring_start_date=date(2026, 8, 10), maintenance_end_date=date(2026, 8, 1))
        repository.deactivate_workstream(retail.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(bailey, program_id=program_id, workstream_id=retail.id, content_program_title="Inactive workstream")
        repository.reactivate_workstream(retail.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(
                bailey,
                program_id=program_id,
                content_program_title="Too many groups",
                total_sku_count=2,
                initial_sku_groups=[{"group_name": "FS", "expected_sku_count": 3}],
            )

        content = service.create_content_program(
            bailey,
            program_id=program_id,
            content_program_title="TEST - Content Management Program",
            owner_user_id=t_user.id,
            content_status=CONTENT_STATUS_CLIENT_REVIEW,
            latest_update="Copy and graphics in client review.",
            waiting_on="Client",
            total_sku_count=371,
            default_graphics_per_sku=5,
            monitoring_start_date=date(2026, 8, 10),
            maintenance_end_date=date(2026, 9, 10),
            initial_sku_groups=[
                {"group_name": "FS", "expected_sku_count": 70},
                {"group_name": "3PG", "expected_sku_count": 228},
                {"group_name": "Gaming", "expected_sku_count": 73},
            ],
            initial_resources={
                "SKU List": "https://example.com/sku-list",
                "Tracksheet": "https://example.com/tracksheet",
            },
        )

        self.assertEqual(content.owner_user_id, t_user.id)
        self.assertEqual(content.content_status, CONTENT_STATUS_CLIENT_REVIEW)
        self.assertEqual(content.workstream_id, next(workstream.id for workstream in repository.workstreams if workstream.program_id == program_id and workstream.workstream_type == WorkstreamType.ECOMMERCE.value))
        self.assertEqual([group.group_name for group in service.list_content_sku_groups(bailey, content.id)], ["FS", "3PG", "Gaming"])

        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_program(bailey, program_id=program_id, content_program_title="TEST - Content Management Program")

        before_events = len(repository.events)
        unchanged = service.update_content_program(bailey, content.id, content_program_title=content.content_program_title)
        self.assertEqual(unchanged.id, content.id)
        self.assertEqual(len(repository.events), before_events)

        updated = service.update_content_program(bailey, content.id, content_status=CONTENT_STATUS_READY_TO_SUBMIT, latest_update="Ready to submit to retailer.")
        self.assertEqual(updated.content_status, CONTENT_STATUS_READY_TO_SUBMIT)

        service.deactivate_content_program(bailey, content.id)
        self.assertFalse(repository.get_content_program(content.id).is_active)
        self.assertEqual(service.list_content_programs(bailey), [])
        service.reactivate_content_program(bailey, content.id)
        self.assertTrue(repository.get_content_program(content.id).is_active)

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("content_program_created", event_types)
        self.assertIn("content_program_latest_update_changed", event_types)
        self.assertIn("content_program_deactivated", event_types)
        self.assertIn("content_program_reactivated", event_types)

    def test_prompt7_content_children_portfolio_resources_and_state(self) -> None:
        from app.campaign_ops.content_management.formatting import PORTFOLIO_COLUMNS, portfolio_rows

        repository, service, bailey, t_user, _l_user, program_id, _influencer, _retail = self._prompt4c_fixture()
        content = service.create_content_program(
            bailey,
            program_id=program_id,
            content_program_title="TEST - Content Child Program",
            owner_user_id=t_user.id,
            total_sku_count=4,
            default_graphics_per_sku=5,
            initial_sku_groups=[
                {"group_name": "Jumex", "expected_sku_count": 1},
                {"group_name": "Pelon", "expected_sku_count": 2},
                {"group_name": "Sandibrochas", "expected_sku_count": 1},
            ],
            initial_resources={
                "SKU List": "https://example.com/skus",
                "Tracksheet": "https://example.com/tracker",
                "Creative Request Deck": "https://example.com/creative",
                "Keyword Insights": "https://example.com/keywords",
                "Photography Folder": "https://example.com/photos",
            },
        )
        groups = service.list_content_sku_groups(bailey, content.id)
        jumex = groups[0]
        service.update_content_sku_group(bailey, content.id, jumex.id, latest_update="Jumex copy drafted")
        service.reorder_content_sku_groups(bailey, content.id, [groups[2].id, groups[1].id, groups[0].id])
        service.deactivate_content_sku_group(bailey, content.id, groups[1].id)
        service.reactivate_content_sku_group(bailey, content.id, groups[1].id)

        sku = service.create_content_sku(bailey, content.id, sku_group_id=jumex.id, product_name="Jumex Mango", sku_code="JM-1", copy_status="drafting", graphics_status="in_progress")
        live_sku = service.create_content_sku(bailey, content.id, sku_group_id=groups[1].id, product_name="Pelon Original", sku_code="PL-1")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_sku(bailey, content.id, sku_group_id=jumex.id, product_name="Duplicate", sku_code="JM-1")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_sku(bailey, content.id, sku_group_id="missing", product_name="Missing group")
        with self.assertRaises(CampaignOpsValidationError):
            service.update_content_sku(bailey, content.id, sku.id, live_url="javascript:bad")
        service.update_content_sku(bailey, content.id, sku.id, copy_status="approved", attribute_status="Optimized", graphics_status="approved")
        service.mark_content_sku_live(bailey, content.id, sku.id, live_url="https://example.com/live/jm-1")
        service.mark_content_sku_issue_found(bailey, content.id, sku.id, "image issue")
        service.clear_content_sku_issue(bailey, content.id, sku.id)
        service.mark_content_sku_live(bailey, content.id, live_sku.id, live_url="https://example.com/live/pl-1")
        service.deactivate_content_sku(bailey, content.id, sku.id)
        service.reactivate_content_sku(bailey, content.id, sku.id)

        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_deliverable(bailey, content.id, deliverable_name="Bad quantity", required_quantity=1, completed_quantity=2)
        deliverable = service.create_content_deliverable(bailey, content.id, sku_group_id=jumex.id, sku_id=sku.id, deliverable_name="PDP copy", deliverable_type="PDP copy", required_quantity=1)
        service.mark_content_deliverable_delivered(bailey, content.id, deliverable.id, date(2026, 8, 11))
        service.mark_content_deliverable_approved(bailey, content.id, deliverable.id, date(2026, 8, 12))
        service.reopen_content_deliverable(bailey, content.id, deliverable.id)
        service.deactivate_content_deliverable(bailey, content.id, deliverable.id)
        service.reactivate_content_deliverable(bailey, content.id, deliverable.id)
        service.mark_content_deliverable_approved(bailey, content.id, deliverable.id, date(2026, 8, 13))

        submission = service.create_content_submission(bailey, content.id, sku_group_id=jumex.id, sku_id=sku.id, retailer_or_platform="Walmart", submission_type="PDP", expected_live_date=date(2026, 8, 20))
        service.mark_content_submission_submitted(bailey, content.id, submission.id, date(2026, 8, 14))
        service.mark_content_submission_approved(bailey, content.id, submission.id, date(2026, 8, 15))
        service.mark_content_submission_published(bailey, content.id, submission.id, date(2026, 8, 21), live_url="https://example.com/walmart/jm-1")
        service.mark_content_submission_issue(bailey, content.id, submission.id, "Retailer rejected image")
        service.resolve_content_submission_issue(bailey, content.id, submission.id)
        service.deactivate_content_submission(bailey, content.id, submission.id)
        service.reactivate_content_submission(bailey, content.id, submission.id)

        update_one = service.create_content_monitoring_update(bailey, content.id, date(2026, 8, 22), "Live checks completed", live_review_count=1)
        update_two = service.create_content_monitoring_update(bailey, content.id, date(2026, 8, 23), "Maintenance pass", publication_state="Monitoring")
        self.assertEqual([item.id for item in service.list_content_monitoring_updates(bailey, content.id)], [update_two.id, update_one.id])
        service.update_content_monitoring_update(bailey, content.id, update_one.id, update_text="Live checks completed across Walmart")
        service.deactivate_content_monitoring_update(bailey, content.id, update_two.id)
        service.reactivate_content_monitoring_update(bailey, content.id, update_two.id)

        with self.assertRaises(CampaignOpsValidationError):
            service.create_content_invoice_checkpoint(bailey, content.id, "Bad invoice", amount=-1)
        invoice = service.create_content_invoice_checkpoint(bailey, content.id, "Initial invoice", due_date=date(2026, 8, 30), amount=1250)
        service.mark_content_invoice_sent(bailey, content.id, invoice.id, date(2026, 8, 24))
        service.mark_content_invoice_paid(bailey, content.id, invoice.id)
        service.deactivate_content_invoice_checkpoint(bailey, content.id, invoice.id)
        service.reactivate_content_invoice_checkpoint(bailey, content.id, invoice.id)

        exact = service.create_milestone(bailey, program_id, "Submit PDP copy", workstream_id=content.workstream_id, milestone_type="Content Management", target_date=date(2026, 8, 18))
        ranged = service.create_milestone(bailey, program_id, "Monitoring window", workstream_id=content.workstream_id, milestone_type="Content Management", start_date=date(2026, 8, 21), end_date=date(2026, 9, 21))
        service.complete_milestone(bailey, exact.id)
        service.reopen_milestone(bailey, exact.id)
        self.assertEqual(ranged.milestone_type, "Content Management")

        detail = service.get_content_program_detail(bailey, content.id)
        self.assertEqual(detail.group_expected_sku_total, 4)
        self.assertEqual(detail.active_sku_count, 2)
        self.assertEqual(detail.delivered_count, 1)
        self.assertEqual(detail.live_count, 1)
        self.assertEqual(detail.issue_count, 0)
        self.assertEqual(detail.sku_list_url, "https://example.com/skus")
        self.assertEqual(detail.next_milestone, "Submit PDP copy")
        self.assertEqual(PORTFOLIO_COLUMNS[:5], ["Content Program", "Client", "Shared Program", "Owner", "Status"])
        rendered = portfolio_rows([detail])[0]
        self.assertEqual(list(rendered), PORTFOLIO_COLUMNS)
        self.assertEqual(rendered["Graphics per SKU"], "5")

        self.assertIn("campaign_ops_selected_content_program_id", SESSION_KEYS)
        state: dict[str, object] = {"campaign_ops_selected_content_program_id": "missing"}
        if state.get("campaign_ops_selected_content_program_id") not in {content.id}:
            state.pop("campaign_ops_selected_content_program_id", None)
        self.assertNotIn("campaign_ops_selected_content_program_id", state)

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("content_sku_group_created", event_types)
        self.assertIn("content_sku_created", event_types)
        self.assertIn("content_deliverable_created", event_types)
        self.assertIn("content_submission_created", event_types)
        self.assertIn("content_monitoring_update_created", event_types)
        self.assertIn("content_invoice_checkpoint_created", event_types)

    def test_prompt8_influencer_campaign_validation_crud_manager_views_and_activity(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, retail = self._prompt4c_fixture()

        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, campaign_title="Missing program")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title=" ")
        with self.assertRaises(CampaignOpsNotFoundError):
            service.create_influencer_campaign(bailey, program_id="missing", campaign_title="Missing")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title="Bad workstream", workstream_id=retail.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title="Inactive manager", manager_user_id=repository.users[3].id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title="Bad target", target_creator_count=-1)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title="Bad dates", launch_date=date(2026, 9, 1), wrap_date=date(2026, 8, 1))
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title="Held without reason", is_on_hold=True)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title="Bad invoice", invoice_amount=-1)

        campaign = service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="TEST - Influencer Planning Campaign",
            manager_user_id=t_user.id,
            planning_status=PLANNING_STATUS_BRIEF_DEVELOPMENT,
            latest_update="Brief approved.",
            waiting_on="Client",
            launch_date=date(2026, 8, 20),
            wrap_date=date(2026, 9, 20),
            invoice_date=date(2026, 10, 31),
            invoice_status="Invoicing in full on 10/31",
            invoice_amount=385000,
            target_creator_count=20,
            approved_creator_count=12,
            contracted_creator_count=10,
        )
        self.assertEqual(campaign.influencer_stage, INFLUENCER_STAGE_PLANNING)
        self.assertEqual(campaign.manager_user_id, t_user.id)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_campaign(bailey, program_id=program_id, campaign_title="TEST - Influencer Planning Campaign")

        before_events = len(repository.events)
        unchanged = service.update_influencer_campaign(bailey, campaign.id, campaign_title=campaign.campaign_title)
        self.assertEqual(unchanged.id, campaign.id)
        self.assertEqual(len(repository.events), before_events)

        service.place_influencer_campaign_on_hold(bailey, campaign.id, "waiting on influencer approvals and ad creative approval")
        held = repository.get_influencer_campaign(campaign.id)
        self.assertTrue(held.is_on_hold)
        self.assertEqual(held.planning_status, PLANNING_STATUS_ON_HOLD)
        service.resume_influencer_campaign(bailey, campaign.id, PLANNING_STATUS_INFLUENCER_LIST_REVIEW)
        service.update_influencer_campaign(bailey, campaign.id, manager_user_id=l_user.id, approved_creator_count=16, latest_update="Client approved influencer list.")

        t_rows = service.list_influencer_campaigns(bailey, manager_user_id=t_user.id)
        l_rows = service.list_influencer_campaigns(bailey, manager_user_id=l_user.id)
        all_rows = service.list_influencer_campaigns(bailey)
        self.assertNotIn(campaign.id, [row.id for row in t_rows])
        self.assertIn(campaign.id, [row.id for row in l_rows])
        self.assertEqual(1, len([row for row in all_rows if row.id == campaign.id]))

        service.deactivate_influencer_campaign(bailey, campaign.id)
        self.assertFalse(repository.get_influencer_campaign(campaign.id).is_active)
        service.reactivate_influencer_campaign(bailey, campaign.id)
        self.assertTrue(repository.get_influencer_campaign(campaign.id).is_active)

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("influencer_campaign_created", event_types)
        self.assertIn("influencer_campaign_manager_user_id_changed", event_types)
        self.assertIn("influencer_campaign_placed_on_hold", event_types)
        self.assertIn("influencer_campaign_resumed", event_types)
        self.assertIn("influencer_campaign_deactivated", event_types)
        self.assertIn("influencer_campaign_reactivated", event_types)

    def test_prompt8_influencer_children_template_portfolio_resources_state(self) -> None:
        from app.campaign_ops.influencer.formatting import PORTFOLIO_COLUMNS, planning_portfolio_rows

        repository, service, bailey, t_user, _l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        campaign = service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="TEST - Influencer Planning Child Campaign",
            manager_user_id=t_user.id,
            planning_status=PLANNING_STATUS_BRIEF_DEVELOPMENT,
            target_creator_count=10,
            approved_creator_count=4,
            contracted_creator_count=2,
            initial_resources={
                "Track Sheet": "https://example.com/track",
                "Influencer Brief": "https://example.com/brief",
                "Bitly Link": "https://example.com/bitly",
                "Invoice": "https://example.com/invoice",
                "EOP Survey": "https://example.com/eop",
                "Campaign Brief": "https://example.com/campaign-brief",
                "Click2Cart Link": "https://example.com/click2cart",
            },
        )
        created = service.create_standard_influencer_planning_template(bailey, campaign.id)
        self.assertEqual(len(STANDARD_PLANNING_TEMPLATE), len(created))
        created_again = service.create_standard_influencer_planning_template(bailey, campaign.id)
        self.assertEqual([], created_again)
        steps = service.list_influencer_planning_steps(bailey, campaign.id)
        self.assertEqual(STANDARD_PLANNING_TEMPLATE[0], steps[0].step_title)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_planning_step(bailey, campaign.id, "Bad date", start_date=date(2026, 9, 1), due_date=date(2026, 8, 1))
        custom = service.create_influencer_planning_step(bailey, campaign.id, "TEST - Custom planning action", responsible_party="Client", due_date=date(2026, 8, 10), sequence_order=0)
        service.complete_influencer_planning_step(bailey, campaign.id, custom.id, date(2026, 8, 9))
        service.reopen_influencer_planning_step(bailey, campaign.id, custom.id)
        service.reorder_influencer_planning_steps(bailey, campaign.id, [custom.id, steps[0].id])
        service.deactivate_influencer_planning_step(bailey, campaign.id, custom.id)
        service.reactivate_influencer_planning_step(bailey, campaign.id, custom.id)

        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_approval_round(bailey, campaign.id, "Influencer List", round_number=0)
        approval = service.create_influencer_approval_round(bailey, campaign.id, "Influencer List", requested_date=date(2026, 8, 5), feedback_due_date=date(2026, 8, 8))
        service.mark_influencer_approval_sent(bailey, campaign.id, approval.id, date(2026, 8, 5))
        service.mark_influencer_approval_feedback_received(bailey, campaign.id, approval.id, date(2026, 8, 7))
        service.mark_influencer_approval_approved(bailey, campaign.id, approval.id, date(2026, 8, 8))
        service.reopen_influencer_approval_round(bailey, campaign.id, approval.id)
        service.deactivate_influencer_approval_round(bailey, campaign.id, approval.id)
        service.reactivate_influencer_approval_round(bailey, campaign.id, approval.id)

        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_content_round(bailey, campaign.id, 0)
        scripts = service.create_influencer_content_round(bailey, campaign.id, 1, content_type="Scripts and Captions", internal_review_due_date=date(2026, 8, 12))
        first = service.create_influencer_content_round(bailey, campaign.id, 2, content_type="First Round Content", client_review_sent_date=date(2026, 8, 15), client_feedback_due_date=date(2026, 8, 18))
        service.mark_influencer_content_round_sent_for_review(bailey, campaign.id, first.id, date(2026, 8, 15))
        service.mark_influencer_content_round_feedback_received(bailey, campaign.id, first.id, date(2026, 8, 17))
        service.mark_influencer_content_round_approved(bailey, campaign.id, first.id, date(2026, 8, 18))
        service.reopen_influencer_content_round(bailey, campaign.id, first.id)
        service.deactivate_influencer_content_round(bailey, campaign.id, scripts.id)
        service.reactivate_influencer_content_round(bailey, campaign.id, scripts.id)

        summary = service.create_or_update_influencer_creator_summary(bailey, campaign.id, target_creator_count=10, applicants_count=30, vetted_count=20, submitted_for_approval_count=15, approved_count=8, contracted_count=6, content_submitted_count=4, content_approved_count=2, notes="Creator counts validated.")
        self.assertEqual(8, summary.approved_count)
        exact = service.create_milestone(bailey, program_id, "Influencer launch", workstream_id=campaign.workstream_id, milestone_type="Influencer Planning", target_date=date(2026, 8, 20))
        ranged = service.create_milestone(bailey, program_id, "Influencer flight", workstream_id=campaign.workstream_id, milestone_type="Influencer Planning", start_date=date(2026, 8, 20), end_date=date(2026, 9, 20))
        service.complete_milestone(bailey, exact.id)
        service.reopen_milestone(bailey, exact.id)
        self.assertEqual("Influencer Planning", ranged.milestone_type)
        service.append_program_note(bailey, program_id, "Influencer campaign note", workstream_id=campaign.workstream_id, note_type="Influencer Planning")

        detail = service.get_influencer_campaign_detail(bailey, campaign.id)
        self.assertEqual("TEST - Custom planning action", detail.next_planning_step)
        self.assertEqual(8, detail.approved_creator_count)
        self.assertEqual("https://example.com/track", detail.track_sheet_url)
        self.assertEqual(PORTFOLIO_COLUMNS[:4], ["Influencer Campaign", "Client", "Shared Program", "Manager"])
        rendered = planning_portfolio_rows([detail])[0]
        self.assertEqual(list(rendered), PORTFOLIO_COLUMNS)

        self.assertIn("campaign_ops_selected_influencer_campaign_id", SESSION_KEYS)
        state: dict[str, object] = {"campaign_ops_selected_influencer_campaign_id": "missing"}
        if state.get("campaign_ops_selected_influencer_campaign_id") not in {campaign.id}:
            state.pop("campaign_ops_selected_influencer_campaign_id", None)
        self.assertNotIn("campaign_ops_selected_influencer_campaign_id", state)

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("influencer_planning_step_created", event_types)
        self.assertIn("influencer_approval_round_created", event_types)
        self.assertIn("influencer_content_round_created", event_types)
        self.assertIn("influencer_creator_summary_updated", event_types)

    def test_prompt26_influencer_planning_manager_filters_and_sequence_first_next_step(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        t_campaign = service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="TEST - T Planning Campaign",
            manager_user_id=t_user.id,
            latest_update="Latest T update",
            waiting_on="Client approvals",
            is_on_hold=True,
            hold_reason="Waiting on client approvals",
        )
        l_campaign = service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="TEST - L Planning Campaign",
            manager_user_id=l_user.id,
        )
        completed = service.create_influencer_planning_step(bailey, t_campaign.id, "TEST - Completed sequence 1", sequence_order=1, due_date=date(2026, 8, 1), status="not_started")
        service.complete_influencer_planning_step(bailey, t_campaign.id, completed.id, date(2026, 8, 1))
        inactive = service.create_influencer_planning_step(bailey, t_campaign.id, "TEST - Inactive sequence 2", sequence_order=2, due_date=date(2026, 8, 2), status="not_started")
        service.deactivate_influencer_planning_step(bailey, t_campaign.id, inactive.id)
        expected_next = service.create_influencer_planning_step(bailey, t_campaign.id, "TEST - Sequence-first next", sequence_order=3, due_date=date(2026, 9, 15), status="not_started")
        service.create_influencer_planning_step(bailey, t_campaign.id, "TEST - Earlier date later sequence", sequence_order=4, due_date=date(2026, 8, 15), status="not_started")
        service.create_resource(bailey, program_id, title="Education", resource_type="Influencer Education", workstream_id=influencer.id, url="https://example.com/education")

        t_rows = service.list_influencer_campaigns(bailey, manager_user_id=t_user.id)
        l_rows = service.list_influencer_campaigns(bailey, manager_user_id=l_user.id)
        all_rows = service.list_influencer_campaigns(bailey)
        detail = service.get_influencer_campaign_detail(bailey, t_campaign.id)

        self.assertIn(t_campaign.id, [row.id for row in t_rows])
        self.assertNotIn(l_campaign.id, [row.id for row in t_rows])
        self.assertIn(l_campaign.id, [row.id for row in l_rows])
        self.assertNotIn(t_campaign.id, [row.id for row in l_rows])
        self.assertIn(t_campaign.id, [row.id for row in all_rows])
        self.assertIn(l_campaign.id, [row.id for row in all_rows])
        self.assertEqual(expected_next.step_title, detail.next_planning_step)
        self.assertEqual(expected_next.due_date, detail.next_planning_step_due_date)
        self.assertEqual("https://example.com/education", detail.influencer_education_url)
        self.assertTrue(detail.is_on_hold)
        self.assertEqual("Waiting on client approvals", detail.hold_reason)

    def test_prompt9_influencer_live_transition_manager_views_and_activity(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        campaign = service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="TEST - Influencer Live Campaign",
            manager_user_id=t_user.id,
            planning_status=PLANNING_STATUS_BRIEF_DEVELOPMENT,
            use_standard_template=True,
        )
        planning_steps_before = service.list_influencer_planning_steps(bailey, campaign.id, include_inactive=True)
        moved = service.transition_influencer_campaign_to_live(bailey, campaign.id)
        self.assertEqual(campaign.id, moved.id)
        self.assertEqual(INFLUENCER_STAGE_LIVE, moved.influencer_stage)
        self.assertEqual(LIVE_STATUS_READY_TO_LAUNCH, moved.planning_status)
        self.assertEqual(planning_steps_before, service.list_influencer_planning_steps(bailey, campaign.id, include_inactive=True))
        self.assertNotIn(campaign.id, [row.id for row in service.list_influencer_campaigns(bailey)])
        self.assertIn(campaign.id, [row.id for row in service.list_influencer_live_campaigns(bailey)])
        self.assertIn(campaign.id, [row.id for row in service.list_influencer_live_campaigns(bailey, manager_user_id=t_user.id)])
        self.assertNotIn(campaign.id, [row.id for row in service.list_influencer_live_campaigns(bailey, manager_user_id=l_user.id)])

        service.update_influencer_live_overview(bailey, campaign.id, manager_user_id=l_user.id, planning_status=LIVE_STATUS_LIVE, latest_update="Creators are live in waves.")
        self.assertNotIn(campaign.id, [row.id for row in service.list_influencer_live_campaigns(bailey, manager_user_id=t_user.id)])
        self.assertIn(campaign.id, [row.id for row in service.list_influencer_live_campaigns(bailey, manager_user_id=l_user.id)])
        service.place_influencer_campaign_on_hold(bailey, campaign.id, "client holding one influencer until October")
        self.assertTrue(repository.get_influencer_campaign(campaign.id).is_on_hold)
        service.resume_influencer_campaign(bailey, campaign.id, LIVE_STATUS_LIVE)
        service.deactivate_influencer_campaign(bailey, campaign.id)
        service.reactivate_influencer_campaign(bailey, campaign.id)

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("influencer_stage_moved_to_live", event_types)
        self.assertIn("influencer_campaign_manager_user_id_changed", event_types)
        self.assertIn("influencer_campaign_placed_on_hold", event_types)
        self.assertIn("influencer_campaign_resumed", event_types)
        self.assertEqual(1, len([row for row in service.list_influencer_live_campaigns(bailey, include_inactive=True) if row.id == campaign.id]))

    def test_prompt9_influencer_live_children_portfolio_wrap_resources_state(self) -> None:
        repository, service, bailey, t_user, _l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        campaign = service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="TEST - Influencer Live Child Campaign",
            manager_user_id=t_user.id,
            planning_status=PLANNING_STATUS_INFLUENCER_LIST_REVIEW,
            target_creator_count=3,
            approved_creator_count=3,
            contracted_creator_count=3,
            initial_resources={
                "Track Sheet": "https://example.com/live-track",
                "Influencer Brief": "https://example.com/live-brief",
                "EOP Survey": "https://example.com/live-eop",
                "Invoice": "https://example.com/live-invoice",
                "Click2Cart Link": "https://example.com/click2cart",
            },
        )
        service.transition_influencer_campaign_to_live(bailey, campaign.id)
        service.create_resource(bailey, program_id, title="Client-Facing Live Doc", resource_type="Client-Facing Live Doc", workstream_id=influencer.id, url="https://example.com/live-doc")
        service.create_resource(bailey, program_id, title="Daily Impressions", resource_type="Daily Impressions", workstream_id=influencer.id, url="https://example.com/daily-impressions")

        created = service.create_standard_influencer_live_template(bailey, campaign.id)
        self.assertEqual(len(STANDARD_LIVE_CHECKPOINT_TEMPLATE), len(created))
        self.assertEqual([], service.create_standard_influencer_live_template(bailey, campaign.id))
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_live_checkpoint(bailey, campaign.id, "Bad date", start_date=date(2026, 9, 1), due_date=date(2026, 8, 1))
        checkpoint = service.create_influencer_live_checkpoint(bailey, campaign.id, "TEST - Verify links", due_date=date(2026, 8, 10), sequence_order=0)
        service.complete_influencer_live_checkpoint(bailey, campaign.id, checkpoint.id, date(2026, 8, 9))
        service.reopen_influencer_live_checkpoint(bailey, campaign.id, checkpoint.id)
        service.reorder_influencer_live_checkpoints(bailey, campaign.id, [checkpoint.id, created[0].id])
        service.deactivate_influencer_live_checkpoint(bailey, campaign.id, checkpoint.id)
        service.reactivate_influencer_live_checkpoint(bailey, campaign.id, checkpoint.id)

        wave1 = service.create_influencer_creator_wave(bailey, campaign.id, 1, wave_name="Wave 1", planned_start_date=date(2026, 8, 15), planned_end_date=date(2026, 8, 20), planned_creator_count=2, live_creator_count=0, completed_creator_count=0)
        wave2 = service.create_influencer_creator_wave(bailey, campaign.id, 2, wave_name="Wave 2", planned_creator_count=1)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_creator_wave(bailey, campaign.id, 1)
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_creator_wave(bailey, campaign.id, 3, planned_start_date=date(2026, 9, 1), planned_end_date=date(2026, 8, 1))
        service.start_influencer_creator_wave(bailey, campaign.id, wave1.id, date(2026, 8, 15))
        service.complete_influencer_creator_wave(bailey, campaign.id, wave1.id, date(2026, 8, 20))
        service.reopen_influencer_creator_wave(bailey, campaign.id, wave1.id)
        service.deactivate_influencer_creator_wave(bailey, campaign.id, wave2.id)
        service.reactivate_influencer_creator_wave(bailey, campaign.id, wave2.id)

        creator1 = service.create_influencer_live_creator(bailey, campaign.id, "Jordan", wave_id=wave1.id, scheduled_live_date=date(2026, 8, 16), content_url="https://example.com/content-jordan", click2cart_url="https://example.com/c2c-jordan", retailer_url="https://example.com/retailer-jordan", impressions_reporting_required=True)
        creator2 = service.create_influencer_live_creator(bailey, campaign.id, "Casey", wave_id=wave1.id, scheduled_live_date=date(2026, 8, 18))
        creator3 = service.create_influencer_live_creator(bailey, campaign.id, "Morgan", wave_id=wave2.id, scheduled_live_date=date(2026, 9, 1))
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_live_creator(bailey, campaign.id, "Bad URL", content_url="javascript:bad")
        service.mark_influencer_live_creator_draft_submitted(bailey, campaign.id, creator1.id)
        service.mark_influencer_live_creator_approved(bailey, campaign.id, creator1.id)
        service.mark_influencer_live_creator_scheduled(bailey, campaign.id, creator1.id, date(2026, 8, 16))
        service.mark_influencer_live_creator_live(bailey, campaign.id, creator1.id, date(2026, 8, 16))
        service.mark_influencer_live_creator_paid_live_complete(bailey, campaign.id, creator1.id, date(2026, 10, 1))
        service.update_influencer_live_creator_impressions(bailey, campaign.id, creator1.id, 125000, date(2026, 8, 17))
        service.deactivate_influencer_live_creator(bailey, campaign.id, creator3.id)
        service.reactivate_influencer_live_creator(bailey, campaign.id, creator3.id)

        exception1 = service.create_influencer_live_exception(bailey, campaign.id, "Waiting on client feedback for three drafts", live_creator_id=creator2.id, exception_type="Client Feedback", status="waiting_on_client", opened_date=date(2026, 8, 18), due_date=date(2026, 8, 20), is_highlighted=True)
        exception2 = service.create_influencer_live_exception(bailey, campaign.id, "Creator resubmitting with client feedback", live_creator_id=creator2.id, exception_type="Creator Resubmission", status="open")
        service.resolve_influencer_live_exception(bailey, campaign.id, exception2.id, "Creator resubmitted.")
        service.reopen_influencer_live_exception(bailey, campaign.id, exception2.id)
        service.deactivate_influencer_live_exception(bailey, campaign.id, exception2.id)
        service.reactivate_influencer_live_exception(bailey, campaign.id, exception2.id)

        detail = service.get_influencer_live_campaign_detail(bailey, campaign.id)
        readiness = service.influencer_live_wrap_readiness(
            detail,
            service.list_influencer_live_checkpoints(bailey, campaign.id),
            service.list_influencer_creator_waves(bailey, campaign.id),
            service.list_influencer_live_creators(bailey, campaign.id),
            service.list_influencer_live_exceptions(bailey, campaign.id),
        )
        self.assertEqual("Needs Attention", readiness)
        service.resolve_influencer_live_exception(bailey, campaign.id, exception1.id, "Feedback received.")
        service.resolve_influencer_live_exception(bailey, campaign.id, exception2.id, "Resubmission accepted.")
        for cp in service.list_influencer_live_checkpoints(bailey, campaign.id):
            service.complete_influencer_live_checkpoint(bailey, campaign.id, cp.id, date(2026, 8, 21))
        for wave in service.list_influencer_creator_waves(bailey, campaign.id):
            service.update_influencer_creator_wave(bailey, campaign.id, wave.id, live_creator_count=wave.planned_creator_count or 1, completed_creator_count=wave.planned_creator_count or 1, status="complete")
        service.mark_influencer_live_creator_live(bailey, campaign.id, creator2.id, date(2026, 8, 18))
        service.mark_influencer_live_creator_live(bailey, campaign.id, creator3.id, date(2026, 9, 1))
        ready = service.influencer_live_wrap_readiness(
            service.get_influencer_live_campaign_detail(bailey, campaign.id),
            service.list_influencer_live_checkpoints(bailey, campaign.id),
            service.list_influencer_creator_waves(bailey, campaign.id),
            service.list_influencer_live_creators(bailey, campaign.id),
            service.list_influencer_live_exceptions(bailey, campaign.id),
        )
        self.assertIn(ready, {"Ready to Wrap", "Wrapped"})

        detail = service.get_influencer_live_campaign_detail(bailey, campaign.id)
        self.assertEqual(checkpoint.checkpoint_title, detail.next_checkpoint if detail.next_checkpoint else checkpoint.checkpoint_title)
        self.assertEqual(2, detail.active_wave_count)
        self.assertEqual(3, detail.live_creator_count)
        self.assertEqual(0, detail.open_exception_count)
        self.assertEqual("https://example.com/live-track", detail.track_sheet_url)
        self.assertEqual("https://example.com/live-doc", detail.client_facing_live_doc_url)
        self.assertIn("campaign_ops_selected_influencer_live_campaign_id", SESSION_KEYS)

        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("influencer_live_checkpoint_created", event_types)
        self.assertIn("influencer_creator_wave_created", event_types)
        self.assertIn("influencer_live_creator_created", event_types)
        self.assertIn("influencer_live_creator_impressions_updated", event_types)
        self.assertIn("influencer_live_exception_created", event_types)

    def test_prompt29_influencer_live_manager_board_batch_data(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        t_campaign = service.create_influencer_campaign(bailey, program_id=program_id, workstream_id=influencer.id, campaign_title="TEST - T Live Board", manager_user_id=t_user.id, target_creator_count=2)
        l_campaign = service.create_influencer_campaign(bailey, program_id=program_id, workstream_id=influencer.id, campaign_title="TEST - L Live Board", manager_user_id=l_user.id, target_creator_count=1)
        service.create_influencer_planning_step(bailey, t_campaign.id, "Planning board row", sequence_order=2, due_date=None)
        service.create_influencer_planning_step(bailey, t_campaign.id, "Planning first row", sequence_order=1, due_date=date(2026, 7, 1))
        service.transition_influencer_campaign_to_live(bailey, t_campaign.id)
        service.transition_influencer_campaign_to_live(bailey, l_campaign.id)
        service.create_influencer_live_checkpoint(bailey, t_campaign.id, "Checkpoint second", sequence_order=2, due_date=None)
        service.create_influencer_live_checkpoint(bailey, t_campaign.id, "Checkpoint first", sequence_order=1, due_date=date(2026, 7, 2))
        service.create_influencer_creator_wave(bailey, t_campaign.id, 2, wave_name="Second wave", planned_start_date=date(2026, 8, 2), planned_creator_count=1)
        service.create_influencer_creator_wave(bailey, t_campaign.id, 1, wave_name="First wave", planned_start_date=date(2026, 8, 1), planned_creator_count=1)
        creator = service.create_influencer_live_creator(bailey, t_campaign.id, "Creator", scheduled_live_date=date(2026, 8, 3), live_status="scheduled")
        service.create_resource(bailey, program_id, title="Walmart", resource_type="Walmart Link", workstream_id=influencer.id, url="https://example.com/walmart")

        t_rows = service.list_influencer_live_campaigns(bailey, manager_user_id=t_user.id)
        l_rows = service.list_influencer_live_campaigns(bailey, manager_user_id=l_user.id)
        all_rows = service.list_influencer_live_campaigns(bailey)
        board = service.get_influencer_live_manager_board_data(bailey, t_rows)
        detail = service.get_influencer_live_campaign_detail(bailey, t_campaign.id)

        self.assertIn(t_campaign.id, [row.id for row in t_rows])
        self.assertNotIn(l_campaign.id, [row.id for row in t_rows])
        self.assertIn(l_campaign.id, [row.id for row in l_rows])
        self.assertIn(t_campaign.id, [row.id for row in all_rows])
        self.assertIn(l_campaign.id, [row.id for row in all_rows])
        self.assertEqual(["Planning first row", "Planning board row"], [row.step_title for row in board["planning_steps"][t_campaign.id]])
        self.assertEqual(["Checkpoint first", "Checkpoint second"], [row.checkpoint_title for row in board["checkpoints"][t_campaign.id]])
        self.assertEqual(["First wave", "Second wave"], [row.wave_name for row in board["waves"][t_campaign.id]])
        self.assertEqual("Walmart Link", board["resources"][program_id][-1].resource_type)
        self.assertEqual(creator.scheduled_live_date, detail.next_go_live_date)
        self.assertEqual(0, detail.open_exception_count)

    def _live_campaign_ready_for_recap(self) -> tuple[FakePrompt4ARepository, CampaignOpsService, CampaignOpsUser, CampaignOpsUser, CampaignOpsUser, str, Workstream, InfluencerCampaignRecord]:
        repository, service, bailey, t_user, l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        campaign = service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="TEST - Influencer Recapping Campaign",
            manager_user_id=t_user.id,
            planning_status=PLANNING_STATUS_BRIEF_DEVELOPMENT,
            target_creator_count=3,
            initial_resources={
                "Track Sheet": "https://example.com/track",
                "Influencer Brief": "https://example.com/brief",
                "Click2Cart Link": "https://example.com/click2cart",
                "Invoice": "https://example.com/invoice",
                "EOP Survey": "https://example.com/eop",
            },
            use_standard_template=True,
        )
        service.create_influencer_approval_round(bailey, campaign.id, "Influencer List", status="approved")
        service.create_influencer_content_round(bailey, campaign.id, 1, content_type="First Round Content", status="approved")
        service.transition_influencer_campaign_to_live(bailey, campaign.id)
        service.create_standard_influencer_live_template(bailey, campaign.id)
        for cp in service.list_influencer_live_checkpoints(bailey, campaign.id):
            service.complete_influencer_live_checkpoint(bailey, campaign.id, cp.id, date(2026, 8, 21))
        wave = service.create_influencer_creator_wave(bailey, campaign.id, 1, planned_creator_count=3, live_creator_count=3, completed_creator_count=3, status="complete")
        for name in ("Jordan", "Casey", "Morgan"):
            creator = service.create_influencer_live_creator(bailey, campaign.id, name, wave_id=wave.id, live_status="paid_live_complete", content_url=f"https://example.com/{name.lower()}", impressions_reporting_required=True, latest_impressions=1000)
            service.mark_influencer_live_creator_paid_live_complete(bailey, campaign.id, creator.id, date(2026, 9, 1))
        return repository, service, bailey, t_user, l_user, program_id, influencer, campaign

    def test_prompt10_influencer_recapping_transition_manager_views_and_activity(self) -> None:
        repository, service, bailey, t_user, l_user, _program_id, _influencer, campaign = self._live_campaign_ready_for_recap()
        planning_before = service.list_influencer_planning_steps(bailey, campaign.id, include_inactive=True)
        live_before = service.list_influencer_live_checkpoints(bailey, campaign.id, include_inactive=True)
        moved = service.transition_influencer_campaign_to_recapping(bailey, campaign.id)
        self.assertEqual(campaign.id, moved.id)
        self.assertEqual(INFLUENCER_STAGE_RECAPPING, moved.influencer_stage)
        self.assertEqual(RECAP_STATUS_READY_TO_RECAP, moved.planning_status)
        self.assertEqual(planning_before, service.list_influencer_planning_steps(bailey, campaign.id, include_inactive=True))
        self.assertEqual(live_before, service.list_influencer_live_checkpoints(bailey, campaign.id, include_inactive=True))
        self.assertNotIn(campaign.id, [row.id for row in service.list_influencer_live_campaigns(bailey)])
        self.assertIn(campaign.id, [row.id for row in service.list_influencer_recap_campaigns(bailey)])
        self.assertIn(campaign.id, [row.id for row in service.list_influencer_recap_campaigns(bailey, manager_user_id=t_user.id)])
        service.update_influencer_campaign(bailey, campaign.id, manager_user_id=l_user.id, influencer_stage=INFLUENCER_STAGE_RECAPPING, planning_status=RECAP_STATUS_COLLECTING_DATA)
        self.assertNotIn(campaign.id, [row.id for row in service.list_influencer_recap_campaigns(bailey, manager_user_id=t_user.id)])
        self.assertIn(campaign.id, [row.id for row in service.list_influencer_recap_campaigns(bailey, manager_user_id=l_user.id)])
        self.assertEqual(1, len([row for row in service.list_influencer_recap_campaigns(bailey, include_inactive=True) if row.id == campaign.id]))
        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("influencer_stage_moved_to_recapping", event_types)
        self.assertIn("influencer_campaign_manager_user_id_changed", event_types)

    def test_prompt10_influencer_recapping_children_closeout_complete_and_state(self) -> None:
        repository, service, bailey, _t_user, _l_user, program_id, influencer, campaign = self._live_campaign_ready_for_recap()
        service.transition_influencer_campaign_to_recapping(bailey, campaign.id)
        record = service.create_or_update_influencer_recap_record(
            bailey,
            campaign.id,
            recap_status=RECAP_STATUS_COLLECTING_DATA,
            reporting_due_date=date(2026, 9, 5),
            client_recap_date=date(2026, 9, 12),
            sales_lift_analysis_required=True,
            sales_lift_analysis_status="required",
            final_performance_data_status="waiting",
            creator_closeout_status="in_progress",
            eop_survey_status="sent",
            invoice_status="not_sent",
            financial_close_status="open",
        )
        event_count = len(repository.events)
        service.create_or_update_influencer_recap_record(
            bailey,
            campaign.id,
            recap_status=record.recap_status,
            reporting_due_date=record.reporting_due_date,
            client_recap_date=record.client_recap_date,
            sales_lift_analysis_required=record.sales_lift_analysis_required,
            sales_lift_analysis_status=record.sales_lift_analysis_status,
            final_performance_data_status=record.final_performance_data_status,
            creator_closeout_status=record.creator_closeout_status,
            eop_survey_status=record.eop_survey_status,
            invoice_status=record.invoice_status,
            financial_close_status=record.financial_close_status,
        )
        self.assertEqual(event_count, len(repository.events))

        created = service.create_standard_influencer_recap_template(bailey, campaign.id)
        self.assertEqual(len(STANDARD_RECAP_CHECKLIST_TEMPLATE), len(created))
        self.assertEqual([], service.create_standard_influencer_recap_template(bailey, campaign.id))
        custom = service.create_influencer_recap_checkpoint(bailey, campaign.id, "TEST - Final recap QA", due_date=date(2026, 9, 8), sequence_order=0, responsible_party="Client")
        service.complete_influencer_recap_checkpoint(bailey, campaign.id, custom.id, date(2026, 9, 8))
        service.reopen_influencer_recap_checkpoint(bailey, campaign.id, custom.id)
        service.reorder_influencer_recap_checkpoints(bailey, campaign.id, [custom.id, created[0].id])
        service.deactivate_influencer_recap_checkpoint(bailey, campaign.id, custom.id)
        service.reactivate_influencer_recap_checkpoint(bailey, campaign.id, custom.id)

        resource = service.create_resource(bailey, program_id, title="Recap Deck", resource_type="Recap Deck", workstream_id=influencer.id, url="https://example.com/recap")
        survey = service.create_reporting_request(bailey, request_category=REQUEST_CATEGORY_SURVEY, request_type="EOP Survey", program_id=program_id, am_name="Taylor")
        report = service.create_reporting_request(bailey, request_category=REQUEST_CATEGORY_REPORT, request_type="Program Recap", program_id=program_id, am_name="Lauren")
        final_links = service.create_influencer_recap_requirement(bailey, campaign.id, "Final Creator Links", "Final links", resource_id=resource.id)
        impressions = service.create_influencer_recap_requirement(bailey, campaign.id, "Final Impressions", "Final impressions")
        performance = service.create_influencer_recap_requirement(bailey, campaign.id, "Performance Data", "Final performance data")
        sales = service.create_influencer_recap_requirement(bailey, campaign.id, "Sales Lift Analysis", "Sales lift analysis")
        eop = service.create_influencer_recap_requirement(bailey, campaign.id, "EOP Survey", "EOP survey", reporting_request_id=survey.id)
        deck = service.create_influencer_recap_requirement(bailey, campaign.id, "Recap Deck", "Recap deck", reporting_request_id=report.id)
        client = service.create_influencer_recap_requirement(bailey, campaign.id, "Client Recap", "Client recap meeting")
        service.mark_influencer_recap_requirement_received(bailey, campaign.id, performance.id, date(2026, 9, 3))
        for req in (final_links, impressions, performance, sales, eop, deck, client):
            service.complete_influencer_recap_requirement(bailey, campaign.id, req.id, date(2026, 9, 10))
        service.reopen_influencer_recap_requirement(bailey, campaign.id, eop.id)
        service.complete_influencer_recap_requirement(bailey, campaign.id, eop.id, date(2026, 9, 10))
        service.deactivate_influencer_recap_requirement(bailey, campaign.id, client.id)
        service.reactivate_influencer_recap_requirement(bailey, campaign.id, client.id)
        service.complete_influencer_recap_requirement(bailey, campaign.id, client.id, date(2026, 9, 12))

        moms = service.create_influencer_recap_launch_item(bailey, campaign.id, "Levoit Vital Pet Pro Air Purifier", group_name="MOMS", retailer_name="Walmart", product_url="https://example.com/product", retailer_url="https://example.com/retailer")
        dads = service.create_influencer_recap_launch_item(bailey, campaign.id, "Cosori Smart Toaster Oven", group_name="DADS", retailer_name="Target")
        other = service.create_influencer_recap_launch_item(bailey, campaign.id, "Levoit VortexIQ Pro Cordless Stick Vacuum", retailer_name="Walmart")
        with self.assertRaises(CampaignOpsValidationError):
            service.create_influencer_recap_launch_item(bailey, campaign.id, "Bad URL", product_url="javascript:bad")
        service.mark_influencer_recap_launch_online(bailey, campaign.id, moms.id, date(2026, 8, 30))
        service.mark_influencer_recap_launch_in_store(bailey, campaign.id, moms.id, date(2026, 9, 2))
        service.reorder_influencer_recap_launch_items(bailey, campaign.id, [dads.id, moms.id, other.id])
        service.deactivate_influencer_recap_launch_item(bailey, campaign.id, other.id)
        service.reactivate_influencer_recap_launch_item(bailey, campaign.id, other.id)

        for cp in service.list_influencer_recap_checkpoints(bailey, campaign.id):
            service.complete_influencer_recap_checkpoint(bailey, campaign.id, cp.id, date(2026, 9, 15))
        service.create_or_update_influencer_recap_record(
            bailey,
            campaign.id,
            recap_status=RECAP_STATUS_READY_TO_CLOSE,
            sales_lift_analysis_required=True,
            sales_lift_analysis_status="complete",
            final_performance_data_status="complete",
            creator_closeout_status="complete",
            eop_survey_status="complete",
            invoice_status="sent",
            financial_close_status="complete",
            recap_delivered_date=date(2026, 9, 12),
            final_close_date=date(2026, 9, 15),
            lessons_learned="TEST - lessons learned",
        )
        summary = service.get_influencer_recap_workspace_summary(bailey, campaign.id)
        self.assertEqual(3, summary.creator_closeout.total_creators)
        self.assertEqual(0, summary.creator_closeout.missing_final_links)
        self.assertEqual(0, summary.creator_closeout.missing_final_impressions)
        self.assertEqual("Ready to Close", summary.ready_to_close_state)
        completed = service.complete_influencer_campaign_from_recapping(bailey, campaign.id)
        self.assertEqual("complete", completed.influencer_stage)
        self.assertEqual(campaign.id, completed.id)
        self.assertNotIn(campaign.id, [row.id for row in service.list_influencer_recap_campaigns(bailey)])
        self.assertIn(campaign.id, [row.id for row in service.list_influencer_recap_campaigns(bailey, include_inactive=True)])
        self.assertEqual(3, len(service.list_influencer_live_creators(bailey, campaign.id, include_inactive=True)))
        self.assertIn("campaign_ops_selected_influencer_recap_campaign_id", SESSION_KEYS)
        event_types = [event["event_type"] for event in repository.events]
        self.assertIn("influencer_recap_checkpoint_created", event_types)
        self.assertIn("influencer_recap_requirement_created", event_types)
        self.assertIn("influencer_recap_launch_item_created", event_types)
        self.assertIn("influencer_stage_completed", event_types)

    def test_prompt11_cross_team_dashboard_filters_metrics_and_sections(self) -> None:
        repository, service, bailey, t_user, l_user, program_id, influencer, _retail = self._prompt4c_fixture()
        program = repository.get_program(program_id)
        program.latest_update = "Cross-team validation update"
        program.risk_level = RiskLevel.AT_RISK.value
        program.status = ProgramStatus.ACTIVE.value
        program.target_end_date = date.today() + timedelta(days=7)
        service.create_task_record(
            bailey,
            program_id,
            "Dashboard overdue task",
            workstream_id=influencer.id,
            assigned_user_id=t_user.id,
            due_date=date.today() - timedelta(days=2),
            status=TaskStatus.IN_PROGRESS.value,
            risk_level=RiskLevel.AT_RISK.value,
            waiting_on=WaitingOn.CLIENT.value,
            hard_deadline=True,
        )
        service.create_milestone(
            bailey,
            program_id,
            "Dashboard upcoming milestone",
            workstream_id=influencer.id,
            owner_user_id=l_user.id,
            target_date=date.today() + timedelta(days=4),
            status=TaskStatus.IN_PROGRESS.value,
        )
        service.create_resource(bailey, program_id, "Dashboard missing resource", "Track Sheet", workstream_id=influencer.id, is_required=True)
        service.create_influencer_campaign(
            bailey,
            program_id=program_id,
            workstream_id=influencer.id,
            campaign_title="Dashboard Influencer Planning",
            manager_user_id=t_user.id,
            influencer_stage=INFLUENCER_STAGE_PLANNING,
            planning_status=PLANNING_STATUS_ON_HOLD,
            is_on_hold=True,
            hold_reason="Client feedback",
            waiting_on=WaitingOn.CLIENT.value,
        )
        service.create_retail_media_campaign(
            bailey,
            program_id=program_id,
            campaign_title="Dashboard Retail",
            owner_user_id=l_user.id,
            retail_media_status=RETAIL_MEDIA_STATUS_LIVE,
            overall_budget=100,
            total_spend=125,
            is_paused=True,
            pause_reason="Budget review",
            waiting_on=WaitingOn.INTERNAL_TEAM.value,
        )
        content = service.create_content_program(
            bailey,
            program_id=program_id,
            content_program_title="Dashboard Content",
            owner_user_id=t_user.id,
            content_status=CONTENT_STATUS_LIVE,
            waiting_on=WaitingOn.ASSETS.value,
        )
        service.create_content_sku(bailey, content.id, product_name="Dashboard SKU", publication_status="issue_found", issue_status="Publication issue")
        service.create_insights_project(
            bailey,
            program_id=program_id,
            project_title="Dashboard Insights",
            owner_user_id=l_user.id,
            insights_status=INSIGHTS_STATUS_DRAFTING_SURVEY,
        )
        service.create_reporting_request(
            bailey,
            request_category=REQUEST_CATEGORY_REPORT,
            request_type="Dashboard Report",
            program_id=program_id,
            am_name="Taylor",
            due_date=date.today() - timedelta(days=1),
            waiting_on=WaitingOn.CLIENT.value,
        )
        summary = service.get_cross_team_dashboard_summary(bailey, {"include_test_records": True})
        self.assertEqual(summary.metrics.active_programs, 1)
        self.assertGreaterEqual(summary.metrics.needs_attention, 1)
        self.assertEqual(summary.metrics.high_risk, 1)
        self.assertEqual(summary.metrics.overdue_tasks, 1)
        self.assertEqual(summary.metrics.upcoming_milestones, 1)
        self.assertGreaterEqual(summary.metrics.waiting_on_client, 2)
        self.assertGreaterEqual(summary.metrics.paused_on_hold, 2)
        reasons = {row.attention_reason for row in summary.needs_attention}
        self.assertIn("Overdue Task", reasons)
        self.assertIn("Missing Required Resource", reasons)
        self.assertIn("Influencer On Hold", reasons)
        self.assertIn("Retail Media Over Budget", reasons)
        self.assertIn("Content Publication Issue", reasons)
        self.assertIn("Reporting Request Overdue", reasons)
        self.assertTrue(any(row.attention_reason == "Overdue Task" and row.severity == "Critical" for row in summary.needs_attention))
        self.assertTrue(any(row.waiting_category == "Client" and row.waiting_on == WaitingOn.CLIENT.value for row in summary.waiting_on))
        self.assertLessEqual(len(summary.influencer_cards), 2)
        self.assertLessEqual(len(summary.retail_media_cards), 2)
        self.assertLessEqual(len(summary.content_cards), 2)
        self.assertLessEqual(len(summary.insights_cards), 2)
        self.assertLessEqual(len(summary.request_cards), 2)
        self.assertIn("Influencer:", summary.programs[0].specialized_stage)

    def test_prompt11_cross_team_dashboard_excludes_tests_and_enforces_personal_access(self) -> None:
        repository, service, bailey, t_user, _l_user, program_id, _influencer, _retail = self._prompt4c_fixture()
        repository.get_program(program_id).program_name = "TEST - Dashboard Hidden"
        hidden = service.get_cross_team_dashboard_summary(bailey, {})
        self.assertEqual(hidden.metrics.active_programs, 0)
        shown = service.get_cross_team_dashboard_summary(bailey, {"include_test_records": True})
        self.assertEqual(shown.metrics.active_programs, 1)
        t_summary = service.get_cross_team_dashboard_summary(t_user, {"include_test_records": True, "person_view": "Bailey"})
        self.assertEqual(t_summary.metrics.active_programs, 1)
        self.assertEqual(repository.last_portfolio_filters["permitted_user_id"], t_user.id)
        self.assertEqual(service.validate_cross_team_person_view(t_user, "L"), "T")
        self.assertEqual(service.normalize_waiting_on_category("client feedback"), "Client")
        self.assertEqual(service.normalize_waiting_on_category("retailer approval"), "Retailer")
        self.assertEqual(service.normalize_waiting_on_category("asset missing"), "Assets")
        self.assertEqual(service.normalize_waiting_on_category("unknown"), "Other")

    def test_prompt11_cross_team_state_and_imports(self) -> None:
        import app.campaign_ops.cross_team.views as cross_team_views
        import app.pages.campaigns as campaigns_page

        self.assertTrue(hasattr(cross_team_views, "render_cross_team_dashboard"))
        self.assertTrue(hasattr(campaigns_page, "render_cross_team_dashboard"))
        for key in (
            "campaign_ops_cross_team_filters",
            "campaign_ops_cross_team_person_view",
            "campaign_ops_cross_team_include_test_records",
            "campaign_ops_cross_team_upcoming_days",
            "campaign_ops_cross_team_selected_program_id",
        ):
            self.assertIn(key, SESSION_KEYS)

    def test_prompt12_shared_ui_formatting_and_navigation_helpers(self) -> None:
        from app.campaign_ops.ui.badges import status_label
        from app.campaign_ops.ui.formatting import (
            display_record_title,
            format_boolean,
            format_currency,
            format_display_date,
            readable_label,
            safe_link_label,
        )
        from app.campaign_ops.ui.navigation import (
            clear_incompatible_specialized_state,
            route_to_program_workspace,
            route_to_specialized_workspace,
        )

        self.assertEqual(readable_label("waiting_on_client"), "Waiting On Client")
        self.assertEqual(format_display_date(date(2026, 8, 27)), "Aug 27, 2026")
        self.assertEqual(format_currency(12500), "$12,500.00")
        self.assertEqual(format_boolean(True), "Yes")
        self.assertEqual(display_record_title("TEST - Example"), "TEST - Example [Test]")
        self.assertEqual(safe_link_label(None), "No Link")
        self.assertEqual(safe_link_label("javascript:bad"), "Invalid Link")
        self.assertEqual(status_label("ready_to_close"), "Ready to Close")

        state = {
            "campaign_ops_selected_retail_media_campaign_id": "retail-1",
            "campaign_ops_selected_content_program_id": "content-1",
            "campaign_ops_content_sku_edit_id": "sku-1",
        }
        route_to_specialized_workspace(state, "Influencer", "program-1", "campaign-1")
        self.assertEqual(state["campaign_ops_section"], "Influencer")
        self.assertEqual(state["campaign_ops_selected_influencer_campaign_id"], "campaign-1")
        self.assertNotIn("campaign_ops_selected_retail_media_campaign_id", state)
        self.assertNotIn("campaign_ops_selected_content_program_id", state)
        self.assertNotIn("campaign_ops_content_sku_edit_id", state)
        clear_incompatible_specialized_state(state, "Retail Media")
        self.assertNotIn("campaign_ops_selected_influencer_campaign_id", state)
        route_to_program_workspace(state, "program-1")
        self.assertEqual(state["campaign_ops_selected_program_id"], "program-1")
        self.assertEqual(state["campaign_ops_section"], "All Programs")

    def test_prompt12_viewer_change_clears_stale_specialized_state(self) -> None:
        state = {
            "campaign_ops_previous_viewer": "Bailey",
            "campaign_ops_section": "Cross-Team",
            "campaign_ops_selected_program_id": "program-1",
            "campaign_ops_selected_influencer_campaign_id": "campaign-1",
            "campaign_ops_selected_retail_media_campaign_id": "retail-1",
            "campaign_ops_request_edit_id": "request-1",
            "campaign_ops_cross_team_selected_program_id": "program-2",
        }
        update_viewer_state(state, "T", CampaignOpsUser(id="22222222-2222-4222-8222-222222222222", display_name="T", role=UserRole.TEAM_MEMBER.value))
        self.assertNotIn("campaign_ops_selected_program_id", state)
        self.assertNotIn("campaign_ops_selected_influencer_campaign_id", state)
        self.assertNotIn("campaign_ops_selected_retail_media_campaign_id", state)
        self.assertNotIn("campaign_ops_request_edit_id", state)
        self.assertNotIn("campaign_ops_cross_team_selected_program_id", state)
        self.assertEqual(state["campaign_ops_section"], "My Programs")


if __name__ == "__main__":
    unittest.main()
