from __future__ import annotations

from datetime import date
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from core.campaign_ops.enums import (
    AssignmentRole,
    CrossStage,
    ProgramStatus,
    RiskLevel,
    TaskStatus,
    WaitingOn,
    WorkstreamType,
)
from core.campaign_ops.exceptions import (
    CampaignOpsDatabaseError,
    CampaignOpsNotFoundError,
    CampaignOpsPermissionError,
    CampaignOpsValidationError,
)
from core.campaign_ops.migrations import connect_to_database
from core.campaign_ops.models import (
    CampaignOpsUser,
    Client,
    Program,
    ProgramAssignment,
    ProgramPortfolioRow,
    ProgramWorkspaceSummary,
    ProgramNote,
    Resource,
    Task,
    TaskListRow,
    Workstream,
    enum_value,
    require_text,
)
from core.campaign_ops.permissions import (
    can_access_admin,
    can_edit_program,
    can_edit_task,
    can_edit_workstream,
    can_manage_assignments,
    can_manage_task_state,
    can_view_program,
)
from core.campaign_ops.repository import CampaignOpsRepository

WAITING_TASK_STATUSES = {
    TaskStatus.WAITING_ON_CLIENT.value,
    TaskStatus.WAITING_ON_CREATOR.value,
    TaskStatus.WAITING_ON_INTERNAL_TEAM.value,
}

ALLOWED_TASK_TRANSITIONS = {
    TaskStatus.NOT_STARTED.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.NOT_APPLICABLE.value,
    },
    TaskStatus.IN_PROGRESS.value: {
        TaskStatus.READY_FOR_INTERNAL_REVIEW.value,
        TaskStatus.READY_FOR_CLIENT_REVIEW.value,
        TaskStatus.WAITING_ON_CLIENT.value,
        TaskStatus.WAITING_ON_CREATOR.value,
        TaskStatus.WAITING_ON_INTERNAL_TEAM.value,
        TaskStatus.BLOCKED.value,
        TaskStatus.COMPLETED.value,
    },
    TaskStatus.READY_FOR_INTERNAL_REVIEW.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.APPROVED.value,
        TaskStatus.COMPLETED.value,
    },
    TaskStatus.READY_FOR_CLIENT_REVIEW.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.APPROVED.value,
        TaskStatus.WAITING_ON_CLIENT.value,
        TaskStatus.COMPLETED.value,
    },
    TaskStatus.WAITING_ON_CLIENT.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.APPROVED.value,
        TaskStatus.COMPLETED.value,
    },
    TaskStatus.WAITING_ON_CREATOR.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.APPROVED.value,
        TaskStatus.COMPLETED.value,
    },
    TaskStatus.WAITING_ON_INTERNAL_TEAM.value: {
        TaskStatus.IN_PROGRESS.value,
        TaskStatus.APPROVED.value,
        TaskStatus.COMPLETED.value,
    },
    TaskStatus.BLOCKED.value: {TaskStatus.IN_PROGRESS.value},
    TaskStatus.APPROVED.value: {TaskStatus.COMPLETED.value},
}


class CampaignOpsService:
    """Coordinate Campaign Operations writes and activity history."""

    def __init__(self, repository: CampaignOpsRepository | None = None) -> None:
        self.repository = repository

    def _repository_for_connection(self, connection: Any) -> CampaignOpsRepository:
        return self.repository or CampaignOpsRepository(connection)

    def _transaction(self, operation: Any) -> Any:
        if self.repository is not None:
            return operation(self.repository)
        connection = connect_to_database()
        try:
            with connection.transaction():
                return operation(CampaignOpsRepository(connection))
        except Exception:
            raise
        finally:
            connection.close()

    def _require_admin(self, actor: CampaignOpsUser | None) -> None:
        if not can_access_admin(actor):
            raise CampaignOpsPermissionError("You do not have permission to perform this action.")

    def _require_active_user(
        self,
        repository: CampaignOpsRepository,
        user_id: str,
        field_name: str,
    ) -> CampaignOpsUser:
        user = repository.get_user_by_id(user_id)
        if user is None or not user.is_active:
            raise CampaignOpsValidationError(f"{field_name} must be an active user.")
        return user

    def _require_active_client(
        self,
        repository: CampaignOpsRepository,
        client_id: str,
    ) -> Client:
        client = repository.get_client(client_id)
        if client is None or not client.is_active:
            raise CampaignOpsValidationError("Client must be an active client.")
        return client

    def _require_program(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
    ) -> Program:
        program = repository.get_program(program_id)
        if program is None:
            raise CampaignOpsNotFoundError("Program was not found.")
        return program

    def _require_workstream(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
        workstream_id: str,
    ) -> Workstream:
        workstream = repository.get_workstream(workstream_id)
        if workstream is None or workstream.program_id != program_id:
            raise CampaignOpsNotFoundError("Workstream was not found.")
        return workstream

    def _require_assignment(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
        assignment_id: str,
    ) -> ProgramAssignment:
        assignment = repository.get_assignment(assignment_id)
        if assignment is None or assignment.program_id != program_id:
            raise CampaignOpsNotFoundError("Assignment was not found.")
        return assignment

    def _require_task(
        self,
        repository: CampaignOpsRepository,
        task_id: str,
    ) -> Task:
        task = repository.get_task(task_id)
        if task is None:
            raise CampaignOpsNotFoundError("Task was not found.")
        return task

    def _validate_task_workstream(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
        workstream_id: str | None,
        require_active: bool = True,
    ) -> None:
        if workstream_id is None:
            return
        workstream = self._require_workstream(repository, program_id, workstream_id)
        if require_active and not workstream.is_active:
            raise CampaignOpsValidationError("Inactive workstreams cannot receive active task changes.")

    def _validate_task_assignee(
        self,
        repository: CampaignOpsRepository,
        assigned_user_id: str | None,
    ) -> None:
        if assigned_user_id:
            self._require_active_user(repository, assigned_user_id, "Assigned user")

    def _validate_task_dates(
        self,
        start_date: date | None,
        due_date: date | None,
    ) -> None:
        if start_date and due_date and due_date < start_date:
            raise CampaignOpsValidationError("Due date cannot precede start date.")

    def _validate_transition(self, current_status: str, new_status: str) -> None:
        current = enum_value(TaskStatus, current_status, "current_status")
        new = enum_value(TaskStatus, new_status, "status")
        if current == new:
            return
        if current in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value}:
            raise CampaignOpsValidationError("Completed or not applicable tasks require an explicit reopen/reset action.")
        if new not in ALLOWED_TASK_TRANSITIONS.get(current, set()):
            raise CampaignOpsValidationError(f"Invalid task status transition: {current} to {new}.")

    def _task_can_be_changed(
        self,
        actor: CampaignOpsUser | None,
        program: Program,
        task: Task,
        assignments: list[ProgramAssignment],
    ) -> None:
        if not can_edit_task(actor, program, task, assignments):
            raise CampaignOpsPermissionError("You do not have permission to edit this task.")
        if not program.is_active:
            raise CampaignOpsValidationError("Archived programs cannot have task changes.")

    def _validate_assignment_scope(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
        assignment_role: str,
        workstream_id: str | None,
    ) -> None:
        role = enum_value(AssignmentRole, assignment_role, "assignment_role")
        if role == AssignmentRole.PROGRAM_OWNER.value and workstream_id is not None:
            raise CampaignOpsValidationError("Program Owner must be program-scoped.")
        if role == AssignmentRole.WORKSTREAM_LEAD.value and workstream_id is None:
            raise CampaignOpsValidationError("Workstream Lead must be workstream-scoped.")
        if workstream_id is not None:
            self._require_workstream(repository, program_id, workstream_id)

    def _ensure_no_duplicate_active_assignment(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
        user_id: str,
        assignment_role: str,
        workstream_id: str | None,
        exclude_assignment_id: str | None = None,
    ) -> None:
        for assignment in repository.list_assignments_by_program(program_id):
            if exclude_assignment_id and assignment.id == exclude_assignment_id:
                continue
            if (
                assignment.user_id == user_id
                and assignment.assignment_role == assignment_role
                and assignment.workstream_id == workstream_id
                and assignment.is_active
            ):
                raise CampaignOpsValidationError("Duplicate active assignment is not allowed.")

    def _ensure_no_duplicate_active_workstream(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
        workstream_type: str,
        exclude_workstream_id: str | None = None,
    ) -> None:
        for workstream in repository.list_workstreams_by_program(program_id):
            if exclude_workstream_id and workstream.id == exclude_workstream_id:
                continue
            if workstream.workstream_type == workstream_type and workstream.is_active:
                raise CampaignOpsValidationError("Duplicate active workstream type is not allowed.")

    def _append_change_activity(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        program_id: str,
        entity_type: str,
        entity_id: str,
        field_name: str,
        old_value: Any,
        new_value: Any,
        workstream_id: str | None = None,
    ) -> None:
        repository.append_event(
            event_type=f"{entity_type}_field_changed",
            entity_type=entity_type,
            entity_id=entity_id,
            program_id=program_id,
            workstream_id=workstream_id,
            actor_user_id=actor.id if actor else None,
            old_value_json={field_name: self._activity_value(old_value)},
            new_value_json={field_name: self._activity_value(new_value)},
            message=(
                f"{actor.display_name if actor else 'System'} changed "
                f"{field_name.replace('_', ' ')} from {old_value or '-'} to {new_value or '-'}."
            ),
        )

    def _activity_value(self, value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    def _workspace_summary_from_repository(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        program_id: str,
    ) -> ProgramWorkspaceSummary:
        program = self._require_program(repository, program_id)
        assignments = repository.list_all_assignments_by_program(program_id)
        active_assignments = [assignment for assignment in assignments if assignment.is_active]
        if not can_view_program(actor, program, active_assignments):
            raise CampaignOpsPermissionError("You do not have permission to view this program.")
        return ProgramWorkspaceSummary(
            program=program,
            client=repository.get_program_client(program_id),
            workstreams=repository.list_all_workstreams_by_program(program_id),
            assignments=assignments,
            users=repository.list_active_users(),
            activity=repository.list_program_activity(program_id),
        )

    def list_active_users(self) -> list[CampaignOpsUser]:
        repository = self.repository or CampaignOpsRepository()
        return repository.list_active_users()

    def list_active_clients(self) -> list[Client]:
        repository = self.repository or CampaignOpsRepository()
        return repository.list_active_clients()

    def create_client(
        self,
        actor: CampaignOpsUser | None,
        name: str,
    ) -> Client:
        """Create an active client and record activity."""
        self._require_admin(actor)
        cleaned_name = require_text(name, "Client name")

        def operation(repository: CampaignOpsRepository) -> Client:
            existing = repository.get_client_by_normalized_name(cleaned_name)
            if existing is not None:
                raise CampaignOpsValidationError("An active client with this name already exists.")
            client = repository.create_client(cleaned_name, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="client_created",
                entity_type="client",
                entity_id=client.id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"name": client.name},
                message=f"Client created: {client.name}",
            )
            return client

        return self._transaction(operation)

    def list_program_portfolio(
        self,
        actor: CampaignOpsUser | None,
        filters: dict[str, Any] | None = None,
    ) -> list[ProgramPortfolioRow]:
        """List program portfolio rows visible to the actor."""
        filters = filters or {}
        repository = self.repository or CampaignOpsRepository()
        permitted_user_id = None if can_access_admin(actor) else actor.id if actor else ""
        return repository.list_program_portfolio(
            search=filters.get("search"),
            program_name=filters.get("program_name"),
            client_name=filters.get("client_name"),
            client_id=filters.get("client_id"),
            primary_workstream_type=filters.get("primary_workstream_type"),
            connected_workstream_type=filters.get("connected_workstream_type"),
            cross_stage=filters.get("cross_stage"),
            status=filters.get("status"),
            risk_level=filters.get("risk_level"),
            primary_owner_user_id=filters.get("primary_owner_user_id"),
            assigned_user_id=filters.get("assigned_user_id"),
            active_state=filters.get("active_state", "active"),
            sort_by=filters.get("sort_by", "recently_updated"),
            permitted_user_id=permitted_user_id,
        )

    def list_user_programs(
        self,
        actor: CampaignOpsUser | None,
        user_id: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[ProgramPortfolioRow]:
        """List programs assigned to a user, scoped by viewer permissions."""
        if actor is None:
            raise CampaignOpsPermissionError("A Campaign Operations user is required.")
        target_user_id = user_id or actor.id
        if target_user_id != actor.id and not can_access_admin(actor):
            raise CampaignOpsPermissionError("You cannot view another user's assigned programs.")
        filters = filters or {}
        repository = self.repository or CampaignOpsRepository()
        return repository.list_programs_assigned_to_user(
            user_id=target_user_id,
            primary_workstream_type=filters.get("primary_workstream_type"),
            connected_workstream_type=filters.get("connected_workstream_type"),
            cross_stage=filters.get("cross_stage"),
            status=filters.get("status"),
            risk_level=filters.get("risk_level"),
            active_state=filters.get("active_state", "active"),
        )

    def create_program_with_workstreams_and_assignments(
        self,
        actor: CampaignOpsUser | None,
        program_name: str,
        client_id: str | None = None,
        new_client_name: str | None = None,
        description: str | None = None,
        primary_workstream_type: str | None = None,
        status: str = ProgramStatus.DRAFT.value,
        cross_stage: str = CrossStage.DRAFT.value,
        risk_level: str = RiskLevel.UNRATED.value,
        priority: str | None = None,
        start_date: date | None = None,
        target_end_date: date | None = None,
        primary_owner_user_id: str | None = None,
        workstream_types: list[str] | None = None,
        workstream_lead_user_ids: dict[str, str | None] | None = None,
    ) -> str:
        """Create a program, initial workstreams, assignments, and activity."""
        self._require_admin(actor)
        cleaned_name = require_text(program_name, "Program name")
        if not primary_workstream_type:
            raise CampaignOpsValidationError("Primary workflow is required.")
        primary_workflow = enum_value(WorkstreamType, primary_workstream_type, "primary_workflow")
        if not primary_owner_user_id:
            raise CampaignOpsValidationError("Primary owner is required.")
        if start_date and target_end_date and target_end_date < start_date:
            raise CampaignOpsValidationError("Target end date cannot precede start date.")

        selected_workstreams = [
            enum_value(WorkstreamType, item, "workstream")
            for item in (workstream_types or [])
        ]
        if len(set(selected_workstreams)) != len(selected_workstreams):
            raise CampaignOpsValidationError("Duplicate active workstreams are not allowed.")
        deduped_workstreams = list(dict.fromkeys([primary_workflow, *selected_workstreams]))
        if not deduped_workstreams:
            raise CampaignOpsValidationError("At least one workstream is required.")

        lead_map = workstream_lead_user_ids or {}

        def operation(repository: CampaignOpsRepository) -> str:
            self._require_active_user(repository, primary_owner_user_id, "Primary owner")
            if new_client_name:
                cleaned_client_name = require_text(new_client_name, "Client name")
                if repository.get_client_by_normalized_name(cleaned_client_name) is not None:
                    raise CampaignOpsValidationError("An active client with this name already exists.")
                client = repository.create_client(
                    cleaned_client_name,
                    actor_user_id=actor.id if actor else None,
                )
                repository.append_event(
                    event_type="client_created",
                    entity_type="client",
                    entity_id=client.id,
                    actor_user_id=actor.id if actor else None,
                    new_value_json={"name": client.name},
                    message=f"Client created: {client.name}",
                )
                resolved_client_id = client.id
            elif client_id:
                client = self._require_active_client(repository, client_id)
                resolved_client_id = client.id
            else:
                raise CampaignOpsValidationError("Client is required.")

            program = repository.create_program(
                program_name=cleaned_name,
                actor_user_id=actor.id if actor else None,
                client_id=resolved_client_id,
                primary_workstream_type=primary_workflow,
                status=status,
                cross_stage=cross_stage,
                risk_level=risk_level,
                priority=priority.strip() if isinstance(priority, str) and priority.strip() else None,
                description=description.strip() if isinstance(description, str) and description.strip() else None,
                start_date=start_date,
                target_end_date=target_end_date,
            )
            repository.append_event(
                event_type="program_created",
                entity_type="program",
                entity_id=program.id,
                program_id=program.id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"program_name": program.program_name},
                message=f"Program created: {program.program_name}",
            )

            created_workstreams: dict[str, Workstream] = {}
            for workstream_type in deduped_workstreams:
                lead_user_id = lead_map.get(workstream_type)
                if lead_user_id:
                    self._require_active_user(repository, lead_user_id, "Workstream lead")
                workstream = repository.create_workstream(
                    program_id=program.id,
                    workstream_type=workstream_type,
                    actor_user_id=actor.id if actor else None,
                    owner_user_id=lead_user_id,
                    status=ProgramStatus.ACTIVE.value,
                    cross_stage=CrossStage.PLANNING.value,
                    risk_level=RiskLevel.UNRATED.value,
                )
                created_workstreams[workstream_type] = workstream
                repository.append_event(
                    event_type="workstream_created",
                    entity_type="workstream",
                    entity_id=workstream.id,
                    program_id=program.id,
                    workstream_id=workstream.id,
                    actor_user_id=actor.id if actor else None,
                    new_value_json={"workstream_type": workstream.workstream_type},
                    message=f"Workstream created: {workstream.workstream_type}",
                )

            repository.create_assignment(
                program_id=program.id,
                user_id=primary_owner_user_id,
                assignment_role=AssignmentRole.PROGRAM_OWNER.value,
                actor_user_id=actor.id if actor else None,
                is_primary=True,
            )
            repository.append_event(
                event_type="assignment_created",
                entity_type="assignment",
                program_id=program.id,
                actor_user_id=actor.id if actor else None,
                new_value_json={
                    "user_id": primary_owner_user_id,
                    "assignment_role": AssignmentRole.PROGRAM_OWNER.value,
                },
                message="Primary owner assigned.",
            )

            seen_assignments = {(program.id, None, primary_owner_user_id, AssignmentRole.PROGRAM_OWNER.value)}
            for workstream_type, lead_user_id in lead_map.items():
                if not lead_user_id or workstream_type not in created_workstreams:
                    continue
                workstream = created_workstreams[workstream_type]
                assignment_key = (
                    program.id,
                    workstream.id,
                    lead_user_id,
                    AssignmentRole.WORKSTREAM_LEAD.value,
                )
                if assignment_key in seen_assignments:
                    raise CampaignOpsValidationError("Duplicate assignment is not allowed.")
                seen_assignments.add(assignment_key)
                assignment = repository.create_assignment(
                    program_id=program.id,
                    workstream_id=workstream.id,
                    user_id=lead_user_id,
                    assignment_role=AssignmentRole.WORKSTREAM_LEAD.value,
                    actor_user_id=actor.id if actor else None,
                    is_primary=False,
                )
                repository.append_event(
                    event_type="assignment_created",
                    entity_type="assignment",
                    entity_id=assignment.id,
                    program_id=program.id,
                    workstream_id=workstream.id,
                    actor_user_id=actor.id if actor else None,
                    new_value_json={
                        "user_id": assignment.user_id,
                        "assignment_role": assignment.assignment_role,
                    },
                    message=f"Workstream lead assigned: {workstream.workstream_type}",
                )
            return program.id

        return self._transaction(operation)

    def get_program_workspace_summary(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
    ) -> ProgramWorkspaceSummary:
        """Load a permission-checked Program Workspace summary."""
        try:
            UUID(str(program_id))
        except ValueError as exc:
            raise CampaignOpsValidationError("Selected program ID is invalid.") from exc
        repository = self.repository or CampaignOpsRepository()
        return self._workspace_summary_from_repository(repository, actor, program_id)

    def create_program(self, actor_user_id: str | None, program_name: str, **kwargs: Any) -> Program:
        """Create a program and append activity."""
        def operation(repository: CampaignOpsRepository) -> Program:
            program = repository.create_program(
                program_name=program_name,
                actor_user_id=actor_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="program_created",
                entity_type="program",
                entity_id=program.id,
                program_id=program.id,
                actor_user_id=actor_user_id,
                new_value_json={"program_name": program.program_name},
                message=f"Program created: {program.program_name}",
            )
            return program

        return self._transaction(operation)

    def update_program(self, actor_user_id: str | None, program_id: str, **kwargs: Any) -> Program:
        """Update a program and append activity."""
        def operation(repository: CampaignOpsRepository) -> Program:
            before = repository.get_program(program_id)
            if before is None:
                raise CampaignOpsNotFoundError("Program was not found.")
            program = repository.update_program(
                program_id=program_id,
                actor_user_id=actor_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="program_updated",
                entity_type="program",
                entity_id=program.id,
                program_id=program.id,
                actor_user_id=actor_user_id,
                old_value_json={"status": before.status, "risk_level": before.risk_level},
                new_value_json={"status": program.status, "risk_level": program.risk_level},
                message=f"Program updated: {program.program_name}",
            )
            return program

        return self._transaction(operation)

    def archive_program(self, actor: CampaignOpsUser | None, program_id: str) -> Program:
        """Permission-aware soft archive and activity."""
        def operation(repository: CampaignOpsRepository) -> Program:
            self._require_admin(actor)
            before = self._require_program(repository, program_id)
            if not before.is_active:
                raise CampaignOpsValidationError("Program is already archived.")
            program = repository.archive_program(program_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="program_archived",
                entity_type="program",
                entity_id=program.id,
                program_id=program.id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"status": ProgramStatus.ARCHIVED.value},
                message=f"{actor.display_name if actor else 'System'} archived the program.",
            )
            return program

        return self._transaction(operation)

    def reactivate_program(self, actor: CampaignOpsUser | None, program_id: str) -> Program:
        """Permission-aware soft reactivation and activity."""
        def operation(repository: CampaignOpsRepository) -> Program:
            self._require_admin(actor)
            before = self._require_program(repository, program_id)
            if before.is_active:
                raise CampaignOpsValidationError("Program is already active.")
            program = repository.reactivate_program(program_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="program_reactivated",
                entity_type="program",
                entity_id=program.id,
                program_id=program.id,
                actor_user_id=actor.id if actor else None,
                old_value_json={"is_active": False},
                new_value_json={"is_active": True},
                message=f"{actor.display_name if actor else 'System'} reactivated the program.",
            )
            return program

        return self._transaction(operation)

    def update_program_details(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        **kwargs: Any,
    ) -> Program:
        """Update shared program details and append readable field-change activity."""
        def operation(repository: CampaignOpsRepository) -> Program:
            program = self._require_program(repository, program_id)
            assignments = repository.list_assignments_by_program(program_id)
            if not can_edit_program(actor, program, assignments):
                raise CampaignOpsPermissionError("You do not have permission to edit this program.")
            if not program.is_active:
                raise CampaignOpsValidationError("Archived programs cannot be edited.")
            if "program_name" in kwargs:
                kwargs["program_name"] = require_text(kwargs["program_name"], "Program name")
            if kwargs.get("client_id"):
                self._require_active_client(repository, kwargs["client_id"])
            if kwargs.get("primary_workstream_type"):
                kwargs["primary_workstream_type"] = enum_value(
                    WorkstreamType,
                    kwargs["primary_workstream_type"],
                    "primary_workstream_type",
                )
            if kwargs.get("status"):
                kwargs["status"] = enum_value(ProgramStatus, kwargs["status"], "status")
            if kwargs.get("cross_stage"):
                kwargs["cross_stage"] = enum_value(CrossStage, kwargs["cross_stage"], "cross_stage")
            if kwargs.get("risk_level"):
                kwargs["risk_level"] = enum_value(RiskLevel, kwargs["risk_level"], "risk_level")
            if kwargs.get("start_date") and kwargs.get("target_end_date") and kwargs["target_end_date"] < kwargs["start_date"]:
                raise CampaignOpsValidationError("Target end date cannot precede start date.")

            editable_fields = {
                "program_name",
                "client_id",
                "primary_workstream_type",
                "status",
                "cross_stage",
                "risk_level",
                "priority",
                "description",
                "latest_update",
                "start_date",
                "target_end_date",
            }
            changes = {
                field: value
                for field, value in kwargs.items()
                if field in editable_fields and getattr(program, field) != value
            }
            if not changes:
                return program
            updated = repository.update_program(
                program_id=program_id,
                actor_user_id=actor.id if actor else None,
                **changes,
            )
            for field, value in changes.items():
                self._append_change_activity(
                    repository,
                    actor,
                    program_id,
                    "program",
                    program_id,
                    field,
                    getattr(program, field),
                    value,
                )
            return updated

        return self._transaction(operation)

    def add_workstream(
        self,
        actor_user_id: str | None,
        program_id: str,
        workstream_type: str,
        **kwargs: Any,
    ) -> Workstream:
        """Add a workstream and append activity."""
        def operation(repository: CampaignOpsRepository) -> Workstream:
            workstream = repository.create_workstream(
                program_id=program_id,
                workstream_type=workstream_type,
                actor_user_id=actor_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="workstream_created",
                entity_type="workstream",
                entity_id=workstream.id,
                program_id=program_id,
                workstream_id=workstream.id,
                actor_user_id=actor_user_id,
                new_value_json={"workstream_type": workstream.workstream_type},
            )
            if owner_user_id:
                assignment = repository.create_assignment(
                    program_id=program_id,
                    workstream_id=workstream.id,
                    user_id=owner_user_id,
                    assignment_role=AssignmentRole.WORKSTREAM_LEAD.value,
                    actor_user_id=actor.id if actor else None,
                )
                repository.append_event(
                    event_type="assignment_created",
                    entity_type="assignment",
                    entity_id=assignment.id,
                    program_id=program_id,
                    workstream_id=workstream.id,
                    actor_user_id=actor.id if actor else None,
                    new_value_json={
                        "user_id": assignment.user_id,
                        "assignment_role": assignment.assignment_role,
                    },
                    message=f"{actor.display_name if actor else 'System'} assigned a workstream lead.",
                )
            return workstream

        return self._transaction(operation)

    def add_workstream_to_program(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        workstream_type: str,
        owner_user_id: str | None = None,
        **kwargs: Any,
    ) -> Workstream:
        """Permission-aware generic workstream creation."""
        def operation(repository: CampaignOpsRepository) -> Workstream:
            program = self._require_program(repository, program_id)
            if not can_access_admin(actor):
                raise CampaignOpsPermissionError("You do not have permission to add workstreams.")
            if not program.is_active:
                raise CampaignOpsValidationError("Archived programs cannot be changed.")
            workstream_type_value = enum_value(WorkstreamType, workstream_type, "workstream_type")
            self._ensure_no_duplicate_active_workstream(repository, program_id, workstream_type_value)
            if owner_user_id:
                self._require_active_user(repository, owner_user_id, "Workstream lead")
            workstream = repository.create_workstream(
                program_id=program_id,
                workstream_type=workstream_type_value,
                actor_user_id=actor.id if actor else None,
                owner_user_id=owner_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="workstream_created",
                entity_type="workstream",
                entity_id=workstream.id,
                program_id=program_id,
                workstream_id=workstream.id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"workstream_type": workstream.workstream_type},
                message=f"{actor.display_name if actor else 'System'} added {workstream.workstream_type} workstream.",
            )
            if owner_user_id:
                assignment = repository.create_assignment(
                    program_id=program_id,
                    workstream_id=workstream.id,
                    user_id=owner_user_id,
                    assignment_role=AssignmentRole.WORKSTREAM_LEAD.value,
                    actor_user_id=actor.id if actor else None,
                )
                repository.append_event(
                    event_type="assignment_created",
                    entity_type="assignment",
                    entity_id=assignment.id,
                    program_id=program_id,
                    workstream_id=workstream.id,
                    actor_user_id=actor.id if actor else None,
                    new_value_json={
                        "user_id": assignment.user_id,
                        "assignment_role": assignment.assignment_role,
                    },
                    message=f"{actor.display_name if actor else 'System'} assigned a workstream lead.",
                )
            return workstream

        return self._transaction(operation)

    def update_workstream_details(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        workstream_id: str,
        **kwargs: Any,
    ) -> Workstream:
        """Update a generic workstream with permission checks and activity."""
        def operation(repository: CampaignOpsRepository) -> Workstream:
            workstream = self._require_workstream(repository, program_id, workstream_id)
            assignments = repository.list_assignments_by_program(program_id)
            if not can_edit_workstream(actor, workstream, assignments):
                raise CampaignOpsPermissionError("You do not have permission to edit this workstream.")
            if kwargs.get("workstream_type"):
                kwargs["workstream_type"] = enum_value(WorkstreamType, kwargs["workstream_type"], "workstream_type")
                self._ensure_no_duplicate_active_workstream(
                    repository,
                    program_id,
                    kwargs["workstream_type"],
                    exclude_workstream_id=workstream_id,
                )
            if kwargs.get("owner_user_id"):
                self._require_active_user(repository, kwargs["owner_user_id"], "Workstream lead")
            for enum_field, enum_type in {
                "status": ProgramStatus,
                "cross_stage": CrossStage,
                "risk_level": RiskLevel,
                "waiting_on": WaitingOn,
            }.items():
                if kwargs.get(enum_field):
                    kwargs[enum_field] = enum_value(enum_type, kwargs[enum_field], enum_field)
            editable_fields = {
                "status",
                "cross_stage",
                "risk_level",
                "owner_user_id",
                "next_action",
                "next_due_date",
                "waiting_on",
                "latest_update",
            }
            changes = {
                field: value
                for field, value in kwargs.items()
                if field in editable_fields and getattr(workstream, field) != value
            }
            if not changes:
                return workstream
            updated = repository.update_workstream(
                workstream_id,
                actor_user_id=actor.id if actor else None,
                **changes,
            )
            if "owner_user_id" in changes and changes["owner_user_id"]:
                for assignment in repository.list_assignments_by_program(program_id):
                    if (
                        assignment.workstream_id == workstream_id
                        and assignment.assignment_role == AssignmentRole.WORKSTREAM_LEAD.value
                        and assignment.is_active
                    ):
                        repository.deactivate_assignment(assignment.id, actor_user_id=actor.id if actor else None)
                assignment = repository.create_assignment(
                    program_id=program_id,
                    workstream_id=workstream_id,
                    user_id=changes["owner_user_id"],
                    assignment_role=AssignmentRole.WORKSTREAM_LEAD.value,
                    actor_user_id=actor.id if actor else None,
                )
                repository.append_event(
                    event_type="assignment_created",
                    entity_type="assignment",
                    entity_id=assignment.id,
                    program_id=program_id,
                    workstream_id=workstream_id,
                    actor_user_id=actor.id if actor else None,
                    new_value_json={
                        "user_id": assignment.user_id,
                        "assignment_role": assignment.assignment_role,
                    },
                    message=f"{actor.display_name if actor else 'System'} assigned a workstream lead.",
                )
            for field, value in changes.items():
                self._append_change_activity(
                    repository,
                    actor,
                    program_id,
                    "workstream",
                    workstream_id,
                    field,
                    getattr(workstream, field),
                    value,
                    workstream_id,
                )
            return updated

        return self._transaction(operation)

    def deactivate_workstream(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        workstream_id: str,
    ) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            self._require_admin(actor)
            self._require_workstream(repository, program_id, workstream_id)
            repository.deactivate_workstream(workstream_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="workstream_deactivated",
                entity_type="workstream",
                entity_id=workstream_id,
                program_id=program_id,
                workstream_id=workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated a workstream.",
            )

        self._transaction(operation)

    def reactivate_workstream(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        workstream_id: str,
    ) -> Workstream:
        def operation(repository: CampaignOpsRepository) -> Workstream:
            self._require_admin(actor)
            workstream = self._require_workstream(repository, program_id, workstream_id)
            self._ensure_no_duplicate_active_workstream(repository, program_id, workstream.workstream_type, workstream_id)
            updated = repository.reactivate_workstream(workstream_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="workstream_reactivated",
                entity_type="workstream",
                entity_id=workstream_id,
                program_id=program_id,
                workstream_id=workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated a workstream.",
            )
            return updated

        return self._transaction(operation)

    def assign_user(
        self,
        actor_user_id: str | None,
        program_id: str,
        user_id: str,
        assignment_role: str,
        **kwargs: Any,
    ) -> ProgramAssignment:
        """Create an assignment and append activity."""
        def operation(repository: CampaignOpsRepository) -> ProgramAssignment:
            assignment = repository.create_assignment(
                program_id=program_id,
                user_id=user_id,
                assignment_role=assignment_role,
                actor_user_id=actor_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="assignment_created",
                entity_type="assignment",
                entity_id=assignment.id,
                program_id=program_id,
                workstream_id=assignment.workstream_id,
                actor_user_id=actor_user_id,
                new_value_json={
                    "user_id": assignment.user_id,
                    "assignment_role": assignment.assignment_role,
                },
            )
            return assignment

        return self._transaction(operation)

    def add_assignment(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        user_id: str,
        assignment_role: str,
        workstream_id: str | None = None,
        is_primary: bool = False,
    ) -> ProgramAssignment:
        def operation(repository: CampaignOpsRepository) -> ProgramAssignment:
            self._require_admin(actor)
            self._require_program(repository, program_id)
            self._require_active_user(repository, user_id, "Assigned user")
            role = enum_value(AssignmentRole, assignment_role, "assignment_role")
            self._validate_assignment_scope(repository, program_id, role, workstream_id)
            self._ensure_no_duplicate_active_assignment(repository, program_id, user_id, role, workstream_id)
            assignment = repository.create_assignment(
                program_id=program_id,
                workstream_id=workstream_id,
                user_id=user_id,
                assignment_role=role,
                actor_user_id=actor.id if actor else None,
                is_primary=is_primary,
            )
            repository.append_event(
                event_type="assignment_created",
                entity_type="assignment",
                entity_id=assignment.id,
                program_id=program_id,
                workstream_id=workstream_id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"user_id": user_id, "assignment_role": role},
                message=f"{actor.display_name if actor else 'System'} added {role.replace('_', ' ')} assignment.",
            )
            return assignment

        return self._transaction(operation)

    def update_assignment(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        assignment_id: str,
        user_id: str,
        assignment_role: str,
        workstream_id: str | None,
        is_primary: bool = False,
    ) -> ProgramAssignment:
        def operation(repository: CampaignOpsRepository) -> ProgramAssignment:
            self._require_admin(actor)
            before = self._require_assignment(repository, program_id, assignment_id)
            self._require_active_user(repository, user_id, "Assigned user")
            role = enum_value(AssignmentRole, assignment_role, "assignment_role")
            self._validate_assignment_scope(repository, program_id, role, workstream_id)
            self._ensure_no_duplicate_active_assignment(repository, program_id, user_id, role, workstream_id, assignment_id)
            if (
                before.user_id == user_id
                and before.assignment_role == role
                and before.workstream_id == workstream_id
                and before.is_primary == is_primary
            ):
                return before
            updated = repository.update_assignment(
                assignment_id,
                actor_user_id=actor.id if actor else None,
                program_id=program_id,
                workstream_id=workstream_id,
                user_id=user_id,
                assignment_role=role,
                is_primary=is_primary,
            )
            repository.append_event(
                event_type="assignment_updated",
                entity_type="assignment",
                entity_id=assignment_id,
                program_id=program_id,
                workstream_id=workstream_id,
                actor_user_id=actor.id if actor else None,
                old_value_json={"user_id": before.user_id, "assignment_role": before.assignment_role},
                new_value_json={"user_id": updated.user_id, "assignment_role": updated.assignment_role},
                message=f"{actor.display_name if actor else 'System'} updated an assignment.",
            )
            return updated

        return self._transaction(operation)

    def deactivate_assignment(self, actor: CampaignOpsUser | None, program_id: str, assignment_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            self._require_admin(actor)
            self._require_assignment(repository, program_id, assignment_id)
            repository.deactivate_assignment(assignment_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="assignment_deactivated",
                entity_type="assignment",
                entity_id=assignment_id,
                program_id=program_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated an assignment.",
            )

        self._transaction(operation)

    def reactivate_assignment(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        assignment_id: str,
    ) -> ProgramAssignment:
        def operation(repository: CampaignOpsRepository) -> ProgramAssignment:
            self._require_admin(actor)
            assignment = self._require_assignment(repository, program_id, assignment_id)
            self._validate_assignment_scope(repository, program_id, assignment.assignment_role, assignment.workstream_id)
            self._ensure_no_duplicate_active_assignment(
                repository,
                program_id,
                assignment.user_id,
                assignment.assignment_role,
                assignment.workstream_id,
                assignment_id,
            )
            updated = repository.reactivate_assignment(assignment_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="assignment_reactivated",
                entity_type="assignment",
                entity_id=assignment_id,
                program_id=program_id,
                workstream_id=assignment.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated an assignment.",
            )
            return updated

        return self._transaction(operation)

    def reassign_primary_program_owner(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        new_owner_user_id: str,
    ) -> ProgramWorkspaceSummary:
        def operation(repository: CampaignOpsRepository) -> ProgramWorkspaceSummary:
            self._require_admin(actor)
            program = self._require_program(repository, program_id)
            if not program.is_active:
                raise CampaignOpsValidationError("Archived programs cannot be reassigned.")
            self._require_active_user(repository, new_owner_user_id, "Primary owner")
            assignments = repository.list_assignments_by_program(program_id)
            current_primary = next(
                (
                    assignment
                    for assignment in assignments
                    if assignment.is_primary and assignment.assignment_role == AssignmentRole.PROGRAM_OWNER.value
                ),
                None,
            )
            if current_primary and current_primary.user_id == new_owner_user_id:
                return self._workspace_summary_from_repository(repository, actor, program_id)
            old_owner = current_primary.user_id if current_primary else None
            if current_primary:
                repository.deactivate_assignment(current_primary.id, actor_user_id=actor.id if actor else None)
            self._ensure_no_duplicate_active_assignment(
                repository,
                program_id,
                new_owner_user_id,
                AssignmentRole.PROGRAM_OWNER.value,
                None,
                current_primary.id if current_primary else None,
            )
            repository.create_assignment(
                program_id=program_id,
                user_id=new_owner_user_id,
                assignment_role=AssignmentRole.PROGRAM_OWNER.value,
                actor_user_id=actor.id if actor else None,
                is_primary=True,
            )
            active_primary_count = sum(
                1
                for assignment in repository.list_assignments_by_program(program_id)
                if assignment.is_primary and assignment.assignment_role == AssignmentRole.PROGRAM_OWNER.value
            )
            if active_primary_count != 1:
                raise CampaignOpsValidationError("Program must have exactly one active primary owner.")
            repository.append_event(
                event_type="primary_owner_reassigned",
                entity_type="assignment",
                program_id=program_id,
                actor_user_id=actor.id if actor else None,
                old_value_json={"user_id": old_owner},
                new_value_json={"user_id": new_owner_user_id},
                message=f"{actor.display_name if actor else 'System'} changed the primary owner.",
            )
            return self._workspace_summary_from_repository(repository, actor, program_id)

        return self._transaction(operation)

    def reassign_workstream_lead(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        workstream_id: str,
        new_lead_user_id: str,
    ) -> Workstream:
        def operation(repository: CampaignOpsRepository) -> Workstream:
            self._require_admin(actor)
            workstream = self._require_workstream(repository, program_id, workstream_id)
            self._require_active_user(repository, new_lead_user_id, "Workstream lead")
            old_lead = workstream.owner_user_id
            updated = repository.update_workstream(
                workstream_id,
                actor_user_id=actor.id if actor else None,
                owner_user_id=new_lead_user_id,
            )
            for assignment in repository.list_assignments_by_program(program_id):
                if (
                    assignment.workstream_id == workstream_id
                    and assignment.assignment_role == AssignmentRole.WORKSTREAM_LEAD.value
                    and assignment.is_active
                ):
                    repository.deactivate_assignment(assignment.id, actor_user_id=actor.id if actor else None)
            repository.create_assignment(
                program_id=program_id,
                workstream_id=workstream_id,
                user_id=new_lead_user_id,
                assignment_role=AssignmentRole.WORKSTREAM_LEAD.value,
                actor_user_id=actor.id if actor else None,
            )
            repository.append_event(
                event_type="workstream_lead_reassigned",
                entity_type="assignment",
                program_id=program_id,
                workstream_id=workstream_id,
                actor_user_id=actor.id if actor else None,
                old_value_json={"user_id": old_lead},
                new_value_json={"user_id": new_lead_user_id},
                message=f"{actor.display_name if actor else 'System'} changed a workstream lead.",
            )
            return updated

        return self._transaction(operation)

    def create_task_record(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        title: str,
        **kwargs: Any,
    ) -> Task:
        """Create a generic Campaign Operations task with activity."""
        cleaned_title = require_text(title, "Title")

        def operation(repository: CampaignOpsRepository) -> Task:
            program = self._require_program(repository, program_id)
            assignments = repository.list_assignments_by_program(program_id)
            temp_task = Task(
                id="00000000-0000-4000-8000-000000000000",
                program_id=program_id,
                title=cleaned_title,
                assigned_user_id=kwargs.get("assigned_user_id"),
            )
            self._task_can_be_changed(actor, program, temp_task, assignments)
            self._validate_task_workstream(repository, program_id, kwargs.get("workstream_id"))
            self._validate_task_assignee(repository, kwargs.get("assigned_user_id"))
            self._validate_task_dates(kwargs.get("start_date"), kwargs.get("due_date"))
            sort_order = int(kwargs.get("sort_order") or 0)
            if sort_order < 0 or sort_order > 100000:
                raise CampaignOpsValidationError("Sort order must be between 0 and 100000.")
            status = enum_value(TaskStatus, kwargs.get("status") or TaskStatus.NOT_STARTED.value, "status")
            completed_at = datetime.now(UTC) if status == TaskStatus.COMPLETED.value else None
            task = repository.create_task(
                program_id=program_id,
                title=cleaned_title,
                actor_user_id=actor.id if actor else None,
                workstream_id=kwargs.get("workstream_id"),
                description=kwargs.get("description"),
                assigned_user_id=kwargs.get("assigned_user_id"),
                responsible_party=enum_value(WaitingOn, kwargs.get("responsible_party") or WaitingOn.INTERNAL_TEAM.value, "responsible_party"),
                status=status,
                risk_level=kwargs.get("risk_level", RiskLevel.UNRATED.value),
                waiting_on=kwargs.get("waiting_on", WaitingOn.NONE.value),
                due_date=kwargs.get("due_date"),
                start_date=kwargs.get("start_date"),
                hard_deadline=bool(kwargs.get("hard_deadline", False)),
                priority=kwargs.get("priority"),
                sort_order=sort_order,
            )
            if completed_at is not None:
                task = repository.update_task_details(
                    task.id,
                    actor_user_id=actor.id if actor else None,
                    title=task.title,
                    description=task.description,
                    workstream_id=task.workstream_id,
                    assigned_user_id=task.assigned_user_id,
                    responsible_party=task.responsible_party,
                    status=task.status,
                    risk_level=task.risk_level,
                    waiting_on=task.waiting_on,
                    due_date=task.due_date,
                    start_date=task.start_date,
                    completed_at=completed_at,
                    hard_deadline=task.hard_deadline,
                    priority=task.priority,
                    sort_order=task.sort_order,
                )
            repository.append_event(
                event_type="task_created",
                entity_type="task",
                entity_id=task.id,
                program_id=program_id,
                workstream_id=task.workstream_id,
                task_id=task.id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"title": task.title, "assigned_user_id": task.assigned_user_id},
                message=f"{actor.display_name if actor else 'System'} created task {task.title}.",
            )
            return task

        return self._transaction(operation)

    def update_task_details(
        self,
        actor: CampaignOpsUser | None,
        task_id: str,
        **kwargs: Any,
    ) -> Task:
        """Update task fields with transition validation and activity."""
        def operation(repository: CampaignOpsRepository) -> Task:
            before = self._require_task(repository, task_id)
            program = self._require_program(repository, before.program_id)
            assignments = repository.list_assignments_by_program(before.program_id)
            self._task_can_be_changed(actor, program, before, assignments)
            if "title" in kwargs:
                kwargs["title"] = require_text(kwargs["title"], "Title")
            if "workstream_id" in kwargs:
                self._validate_task_workstream(repository, before.program_id, kwargs.get("workstream_id"))
            if "assigned_user_id" in kwargs:
                self._validate_task_assignee(repository, kwargs.get("assigned_user_id"))
                if not can_access_admin(actor) and kwargs.get("assigned_user_id") != before.assigned_user_id:
                    raise CampaignOpsPermissionError("Team Members cannot reassign tasks.")
            self._validate_task_dates(
                kwargs.get("start_date", before.start_date),
                kwargs.get("due_date", before.due_date),
            )
            if "status" in kwargs and kwargs["status"] is not None:
                kwargs["status"] = enum_value(TaskStatus, kwargs["status"], "status")
                self._validate_transition(before.status, kwargs["status"])
                kwargs["completed_at"] = (
                    datetime.now(UTC) if kwargs["status"] == TaskStatus.COMPLETED.value else None
                )
            if "responsible_party" in kwargs and kwargs["responsible_party"]:
                kwargs["responsible_party"] = enum_value(WaitingOn, kwargs["responsible_party"], "responsible_party")
            if "waiting_on" in kwargs and kwargs["waiting_on"]:
                kwargs["waiting_on"] = enum_value(WaitingOn, kwargs["waiting_on"], "waiting_on")
            if "risk_level" in kwargs and kwargs["risk_level"]:
                kwargs["risk_level"] = enum_value(RiskLevel, kwargs["risk_level"], "risk_level")
            if "sort_order" in kwargs and kwargs["sort_order"] is not None:
                kwargs["sort_order"] = int(kwargs["sort_order"])
                if kwargs["sort_order"] < 0 or kwargs["sort_order"] > 100000:
                    raise CampaignOpsValidationError("Sort order must be between 0 and 100000.")

            editable = {
                "title",
                "description",
                "workstream_id",
                "assigned_user_id",
                "responsible_party",
                "status",
                "risk_level",
                "waiting_on",
                "due_date",
                "start_date",
                "completed_at",
                "hard_deadline",
                "priority",
                "sort_order",
            }
            changes = {
                field: value
                for field, value in kwargs.items()
                if field in editable and getattr(before, field) != value
            }
            if not changes:
                return before
            merged = {
                "title": before.title,
                "description": before.description,
                "workstream_id": before.workstream_id,
                "assigned_user_id": before.assigned_user_id,
                "responsible_party": before.responsible_party,
                "status": before.status,
                "risk_level": before.risk_level,
                "waiting_on": before.waiting_on,
                "due_date": before.due_date,
                "start_date": before.start_date,
                "completed_at": before.completed_at,
                "hard_deadline": before.hard_deadline,
                "priority": before.priority,
                "sort_order": before.sort_order,
            }
            merged.update(changes)
            updated = repository.update_task_details(
                task_id,
                actor_user_id=actor.id if actor else None,
                **merged,
            )
            for field, value in changes.items():
                self._append_change_activity(
                    repository,
                    actor,
                    before.program_id,
                    "task",
                    task_id,
                    field,
                    getattr(before, field),
                    value,
                    updated.workstream_id,
                )
            return updated

        return self._transaction(operation)

    def change_task_status(
        self,
        actor: CampaignOpsUser | None,
        task_id: str,
        status: str,
    ) -> Task:
        return self.update_task_details(actor, task_id, status=status)

    def complete_task_record(self, actor: CampaignOpsUser | None, task_id: str) -> Task:
        """Explicitly complete a task and set completed timestamp."""
        return self.change_task_status(actor, task_id, TaskStatus.COMPLETED.value)

    def reopen_task(
        self,
        actor: CampaignOpsUser | None,
        task_id: str,
        reopened_status: str = TaskStatus.IN_PROGRESS.value,
    ) -> Task:
        """Explicitly reopen completed or not-applicable tasks."""
        def operation(repository: CampaignOpsRepository) -> Task:
            before = self._require_task(repository, task_id)
            program = self._require_program(repository, before.program_id)
            assignments = repository.list_assignments_by_program(before.program_id)
            self._task_can_be_changed(actor, program, before, assignments)
            if before.status not in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value}:
                raise CampaignOpsValidationError("Only completed or not applicable tasks require explicit reopen.")
            status = enum_value(TaskStatus, reopened_status, "reopened_status")
            if status in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value}:
                raise CampaignOpsValidationError("Reopened status must be active.")
            updated = repository.update_task_details(
                task_id,
                actor_user_id=actor.id if actor else None,
                title=before.title,
                description=before.description,
                workstream_id=before.workstream_id,
                assigned_user_id=before.assigned_user_id,
                responsible_party=before.responsible_party,
                status=status,
                risk_level=before.risk_level,
                waiting_on=before.waiting_on,
                due_date=before.due_date,
                start_date=before.start_date,
                completed_at=None,
                hard_deadline=before.hard_deadline,
                priority=before.priority,
                sort_order=before.sort_order,
            )
            repository.append_event(
                event_type="task_reopened",
                entity_type="task",
                entity_id=task_id,
                program_id=before.program_id,
                workstream_id=before.workstream_id,
                task_id=task_id,
                actor_user_id=actor.id if actor else None,
                old_value_json={"status": before.status, "completed_at": self._activity_value(before.completed_at)},
                new_value_json={"status": status, "completed_at": None},
                message=f"{actor.display_name if actor else 'System'} reopened {before.title}.",
            )
            return updated

        return self._transaction(operation)

    def deactivate_task_record(self, actor: CampaignOpsUser | None, task_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            task = self._require_task(repository, task_id)
            program = self._require_program(repository, task.program_id)
            assignments = repository.list_assignments_by_program(task.program_id)
            if not can_manage_task_state(actor, program, task, assignments):
                raise CampaignOpsPermissionError("You do not have permission to deactivate this task.")
            repository.deactivate_task(task_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="task_deactivated",
                entity_type="task",
                entity_id=task_id,
                program_id=task.program_id,
                workstream_id=task.workstream_id,
                task_id=task_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated {task.title}.",
            )

        self._transaction(operation)

    def reactivate_task_record(self, actor: CampaignOpsUser | None, task_id: str) -> Task:
        def operation(repository: CampaignOpsRepository) -> Task:
            task = self._require_task(repository, task_id)
            program = self._require_program(repository, task.program_id)
            assignments = repository.list_assignments_by_program(task.program_id)
            if not can_manage_task_state(actor, program, task, assignments):
                raise CampaignOpsPermissionError("You do not have permission to reactivate this task.")
            self._validate_task_workstream(repository, task.program_id, task.workstream_id)
            updated = repository.reactivate_task(task_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="task_reactivated",
                entity_type="task",
                entity_id=task_id,
                program_id=task.program_id,
                workstream_id=task.workstream_id,
                task_id=task_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated {task.title}.",
            )
            return updated

        return self._transaction(operation)

    def list_program_tasks(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[TaskListRow]:
        repository = self.repository or CampaignOpsRepository()
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have permission to view program tasks.")
        return repository.list_task_rows_by_program(program_id, include_inactive=include_inactive)

    def list_user_tasks(
        self,
        actor: CampaignOpsUser | None,
        user_id: str,
        include_inactive: bool = False,
    ) -> list[TaskListRow]:
        if actor is None:
            raise CampaignOpsPermissionError("A Campaign Operations user is required.")
        if actor.id != user_id and not can_access_admin(actor):
            raise CampaignOpsPermissionError("You cannot view another user's tasks.")
        repository = self.repository or CampaignOpsRepository()
        return repository.list_task_rows_by_assigned_user(user_id, include_inactive=include_inactive)

    def group_user_tasks(
        self,
        tasks: list[TaskListRow],
        today: date | None = None,
    ) -> dict[str, list[TaskListRow]]:
        today = today or datetime.now(UTC).date()
        groups: dict[str, list[TaskListRow]] = {
            "Overdue": [],
            "Due today": [],
            "Due this week": [],
            "Waiting": [],
            "Remaining open": [],
            "Recently completed": [],
        }
        week_end = date.fromordinal(today.toordinal() + (6 - today.weekday()))
        for task in tasks:
            if not task.is_active:
                continue
            if task.status == TaskStatus.COMPLETED.value:
                if task.completed_at and (today - task.completed_at.date()).days <= 7:
                    groups["Recently completed"].append(task)
                continue
            if task.due_date and task.due_date < today:
                groups["Overdue"].append(task)
            elif task.due_date == today:
                groups["Due today"].append(task)
            elif task.due_date and today < task.due_date <= week_end:
                groups["Due this week"].append(task)
            elif task.status in WAITING_TASK_STATUSES or task.waiting_on != WaitingOn.NONE.value:
                groups["Waiting"].append(task)
            else:
                groups["Remaining open"].append(task)
        return groups

    def add_task(
        self,
        actor_user_id: str | None,
        program_id: str,
        title: str,
        **kwargs: Any,
    ) -> Task:
        """Create a task and append activity."""
        def operation(repository: CampaignOpsRepository) -> Task:
            task = repository.create_task(
                program_id=program_id,
                title=title,
                actor_user_id=actor_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="task_created",
                entity_type="task",
                entity_id=task.id,
                program_id=program_id,
                workstream_id=task.workstream_id,
                task_id=task.id,
                actor_user_id=actor_user_id,
                new_value_json={"title": task.title, "status": task.status},
            )
            return task

        return self._transaction(operation)

    def update_task_status(
        self,
        actor_user_id: str | None,
        task_id: str,
        status: str,
    ) -> Task:
        """Update task status and append activity."""
        def operation(repository: CampaignOpsRepository) -> Task:
            task = repository.update_task(
                task_id=task_id,
                actor_user_id=actor_user_id,
                status=status,
            )
            repository.append_event(
                event_type="task_status_updated",
                entity_type="task",
                entity_id=task.id,
                program_id=task.program_id,
                workstream_id=task.workstream_id,
                task_id=task.id,
                actor_user_id=actor_user_id,
                new_value_json={"status": task.status},
            )
            return task

        return self._transaction(operation)

    def complete_task(self, actor_user_id: str | None, task_id: str) -> Task:
        """Complete a task and append activity."""
        def operation(repository: CampaignOpsRepository) -> Task:
            task = repository.complete_task(task_id=task_id, actor_user_id=actor_user_id)
            repository.append_event(
                event_type="task_completed",
                entity_type="task",
                entity_id=task.id,
                program_id=task.program_id,
                workstream_id=task.workstream_id,
                task_id=task.id,
                actor_user_id=actor_user_id,
                new_value_json={"status": TaskStatus.COMPLETED.value},
            )
            return task

        return self._transaction(operation)

    def add_resource(
        self,
        actor_user_id: str | None,
        program_id: str,
        resource_type: str,
        title: str,
        **kwargs: Any,
    ) -> Resource:
        """Create a resource and append activity."""
        def operation(repository: CampaignOpsRepository) -> Resource:
            resource = repository.create_resource(
                program_id=program_id,
                resource_type=resource_type,
                title=title,
                actor_user_id=actor_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="resource_created",
                entity_type="resource",
                entity_id=resource.id,
                program_id=program_id,
                workstream_id=resource.workstream_id,
                actor_user_id=actor_user_id,
                new_value_json={"title": resource.title},
            )
            return resource

        return self._transaction(operation)

    def add_note(
        self,
        actor_user_id: str | None,
        program_id: str,
        note_text: str,
        **kwargs: Any,
    ) -> ProgramNote:
        """Append a note and activity event."""
        def operation(repository: CampaignOpsRepository) -> ProgramNote:
            note = repository.append_note(
                program_id=program_id,
                note_text=note_text,
                author_user_id=actor_user_id,
                **kwargs,
            )
            repository.append_event(
                event_type="note_added",
                entity_type="note",
                entity_id=note.id,
                program_id=program_id,
                workstream_id=note.workstream_id,
                task_id=note.task_id,
                actor_user_id=actor_user_id,
                message="Note added.",
            )
            return note

        return self._transaction(operation)


def create_service() -> CampaignOpsService:
    """Build the default Campaign Operations service."""
    try:
        return CampaignOpsService()
    except Exception as exc:
        raise CampaignOpsDatabaseError("Campaign Operations service could not start.") from exc
