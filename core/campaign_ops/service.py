from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from core.campaign_ops.enums import (
    AssignmentRole,
    CrossStage,
    ProgramStatus,
    RiskLevel,
    TaskStatus,
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
    Workstream,
    enum_value,
    require_text,
)
from core.campaign_ops.permissions import can_access_admin, can_view_program
from core.campaign_ops.repository import CampaignOpsRepository


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
        program = repository.get_program(program_id)
        if program is None:
            raise CampaignOpsNotFoundError("Program was not found.")
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have permission to view this program.")
        return ProgramWorkspaceSummary(
            program=program,
            client=repository.get_program_client(program_id),
            workstreams=repository.list_workstreams_by_program(program_id),
            assignments=assignments,
            users=repository.list_active_users(),
            activity=repository.list_program_activity(program_id),
        )

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

    def archive_program(self, actor_user_id: str | None, program_id: str) -> Program:
        """Archive a program and append activity."""
        def operation(repository: CampaignOpsRepository) -> Program:
            program = repository.archive_program(program_id, actor_user_id=actor_user_id)
            repository.append_event(
                event_type="program_archived",
                entity_type="program",
                entity_id=program.id,
                program_id=program.id,
                actor_user_id=actor_user_id,
                new_value_json={"status": ProgramStatus.ARCHIVED.value},
                message=f"Program archived: {program.program_name}",
            )
            return program

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
            return workstream

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
