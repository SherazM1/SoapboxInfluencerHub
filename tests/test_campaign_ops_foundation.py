from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
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
    InsightsObjectiveRecord,
    InsightsPortfolioRow,
    InsightsProjectRecord,
    Milestone,
    MilestoneListRow,
    NoteListRow,
    Program,
    ProgramAssignment,
    ProgramNote,
    ReportingRequestListRow,
    ReportingRequestRecord,
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
from core.campaign_ops.insights import INSIGHTS_STATUS_DRAFTING_SURVEY, INSIGHTS_STATUS_NOT_STARTED
from core.campaign_ops.reporting_requests import normalize_am_name


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

    def list_note_rows_by_program(self, program_id: str, include_internal: bool = True, newest_first: bool = True) -> list[NoteListRow]:
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
        return list(reversed(rows)) if newest_first else rows

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

    def append_event(self, **kwargs: str | None) -> object:
        self.events.append(kwargs)
        return SimpleNamespace(id=f"event-{len(self.events)}")

    def list_program_portfolio(self, **kwargs: object) -> list[object]:
        self.last_portfolio_filters = kwargs
        return []

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


if __name__ == "__main__":
    unittest.main()
