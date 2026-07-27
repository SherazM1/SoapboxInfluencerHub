from __future__ import annotations

from core.campaign_ops.enums import AssignmentRole, UserRole
from core.campaign_ops.models import CampaignOpsUser, Program, ProgramAssignment, Task, Workstream


def user_role(user: CampaignOpsUser | None) -> str | None:
    """Return a normalized user role value."""
    return user.role if user else None


def is_administrator(user: CampaignOpsUser | None) -> bool:
    """Return whether a user has administrator privileges."""
    return user_role(user) == UserRole.ADMINISTRATOR.value


def is_team_member(user: CampaignOpsUser | None) -> bool:
    """Return whether a user is a team member."""
    return user_role(user) == UserRole.TEAM_MEMBER.value


def is_viewer(user: CampaignOpsUser | None) -> bool:
    """Return whether a user has viewer-only privileges."""
    return user_role(user) == UserRole.VIEWER.value


def user_has_assignment(
    user: CampaignOpsUser | None,
    assignments: list[ProgramAssignment],
    program_id: str | None = None,
    workstream_id: str | None = None,
) -> bool:
    """Return whether a user has an active matching assignment."""
    if user is None:
        return False
    for assignment in assignments:
        if not assignment.is_active or assignment.user_id != user.id:
            continue
        if program_id is not None and assignment.program_id != program_id:
            continue
        if workstream_id is not None and assignment.workstream_id != workstream_id:
            continue
        return True
    return False


def can_view_program(
    user: CampaignOpsUser | None,
    program: Program,
    assignments: list[ProgramAssignment],
    explicit_program_ids: set[str] | None = None,
) -> bool:
    """Return whether a user can view a program."""
    if is_administrator(user):
        return True
    if is_team_member(user):
        return user_has_assignment(user, assignments, program_id=program.id)
    if is_viewer(user):
        return program.id in (explicit_program_ids or set())
    return False


def can_edit_program(
    user: CampaignOpsUser | None,
    program: Program,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can edit program-level details."""
    if is_administrator(user):
        return True
    if not is_team_member(user):
        return False
    editable_roles = {
        AssignmentRole.PROGRAM_OWNER.value,
        AssignmentRole.ADMIN_OVERSIGHT.value,
    }
    return any(
        assignment.user_id == user.id
        and assignment.program_id == program.id
        and assignment.is_active
        and assignment.assignment_role in editable_roles
        for assignment in assignments
    )


def can_edit_workstream(
    user: CampaignOpsUser | None,
    workstream: Workstream,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can edit an assigned workstream."""
    if is_administrator(user):
        return True
    if not is_team_member(user):
        return False
    return workstream.owner_user_id == user.id or user_has_assignment(
        user,
        assignments,
        program_id=workstream.program_id,
        workstream_id=workstream.id,
    )


def can_manage_assignments(user: CampaignOpsUser | None) -> bool:
    """Return whether a user can manage assignments."""
    return is_administrator(user)


def can_archive_program(user: CampaignOpsUser | None) -> bool:
    """Return whether a user can archive programs."""
    return is_administrator(user)


def can_change_risk_and_priority(user: CampaignOpsUser | None) -> bool:
    """Return whether a user can change cross-team risk and priority fields."""
    return is_administrator(user)


def can_view_activity_history(
    user: CampaignOpsUser | None,
    program: Program,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can view program activity history."""
    return can_view_program(user, program, assignments)


def can_view_task(
    user: CampaignOpsUser | None,
    program: Program,
    task: Task,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can view a task through program access."""
    return can_view_program(user, program, assignments)


def can_edit_task(
    user: CampaignOpsUser | None,
    program: Program,
    task: Task,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can edit task fields or status."""
    if is_administrator(user):
        return True
    if not is_team_member(user) or not program.is_active or not task.is_active:
        return False
    if task.assigned_user_id == user.id:
        return True
    if task.workstream_id:
        return user_has_assignment(
            user,
            assignments,
            program_id=program.id,
            workstream_id=task.workstream_id,
        )
    return False


def can_manage_task_state(
    user: CampaignOpsUser | None,
    program: Program,
    task: Task,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can deactivate or reactivate a task."""
    return is_administrator(user)


def can_access_admin(user: CampaignOpsUser | None) -> bool:
    """Return whether a user can access Campaign Operations administration."""
    return is_administrator(user)
