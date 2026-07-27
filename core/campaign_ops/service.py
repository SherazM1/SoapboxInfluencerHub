from __future__ import annotations

from typing import Any

from core.campaign_ops.enums import ProgramStatus, TaskStatus
from core.campaign_ops.exceptions import CampaignOpsDatabaseError, CampaignOpsNotFoundError
from core.campaign_ops.migrations import connect_to_database
from core.campaign_ops.models import (
    Program,
    ProgramAssignment,
    ProgramNote,
    Resource,
    Task,
    Workstream,
)
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
