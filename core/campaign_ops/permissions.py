from __future__ import annotations

from core.campaign_ops.enums import AssignmentRole, UserRole
from core.campaign_ops.exceptions import CampaignOpsPermissionError
from core.campaign_ops.models import CampaignOpsUser, Milestone, Program, ProgramAssignment, Resource, Task, Workstream


def user_role(user: CampaignOpsUser | None) -> str | None:
    """Return a normalized user role value."""
    return user.role if user else None


def is_administrator(user: CampaignOpsUser | None) -> bool:
    """Return whether a user has administrator privileges."""
    return bool(user and user_role(user) == UserRole.ADMINISTRATOR.value and user.is_active)


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


ACCESS_DENIED = "You do not have access to this program."


def can_view_program(
    user: CampaignOpsUser | None,
    program: Program | None,
    assignments: list[ProgramAssignment],
    explicit_program_ids: set[str] | None = None,
    *,
    workstreams: list[Workstream] = (),
) -> bool:
    """Admin, primary Program Lead Owner, or primary workflow Manager only.

    The retired explicit-ID argument is accepted for API compatibility, never as a grant.
    Archived records remain available only to administrator archive tooling.
    """
    if user is None or not user.is_active or program is None:
        return False
    if is_administrator(user):
        return True
    if not program.is_active or not is_team_member(user):
        return False
    active = [a for a in assignments if a.is_active and a.program_id == program.id and a.user_id == user.id]
    if any(a.assignment_role == AssignmentRole.PROGRAM_OWNER.value and a.is_primary
           and a.workstream_id is None for a in active):
        return True
    primary = [w for w in workstreams if w.is_active and w.program_id == program.id
               and w.workstream_type == program.primary_workstream_type]
    return any(w.owner_user_id == user.id or any(
        a.workstream_id == w.id and a.assignment_role == AssignmentRole.WORKSTREAM_LEAD.value
        for a in active) for w in primary)


def program_access_allowed(repository, actor, program) -> bool:
    """Fresh service-boundary authorization; roster and campaign owner fields are not grants."""
    if actor is None or not actor.is_active or program is None:
        return False
    if is_administrator(actor):
        return True
    return can_view_program(actor, program, repository.list_assignments_by_program(program.id),
                            workstreams=repository.list_workstreams_by_program(program.id))


def require_program_access(repository, actor, program_id, *, active_only=False):
    program = repository.get_program(program_id)
    if not program_access_allowed(repository, actor, program) or (active_only and not program.is_active):
        raise CampaignOpsPermissionError(ACCESS_DENIED)
    return program


def program_scope_user_id(actor):
    """None means administrator SQL scope; invalid actors must never become an unscoped query."""
    if actor is None or not actor.is_active or (not is_administrator(actor) and not is_team_member(actor)):
        raise CampaignOpsPermissionError(ACCESS_DENIED)
    return None if is_administrator(actor) else actor.id


def program_access_sql():
    """SQL equivalent of can_view_program for active actor IDs; Program alias is p."""
    return """(%s::uuid is null or exists (
        select 1 from campaign_ops_assignments access_lead
        where access_lead.program_id = p.id and access_lead.is_active = true
          and access_lead.assignment_role = 'program_owner' and access_lead.is_primary = true
          and access_lead.workstream_id is null and access_lead.user_id = %s::uuid
    ) or exists (
        select 1 from campaign_ops_workstreams access_workstream
        where access_workstream.program_id = p.id and access_workstream.is_active = true
          and access_workstream.workstream_type = p.primary_workstream_type
          and (access_workstream.owner_user_id = %s::uuid or exists (
              select 1 from campaign_ops_assignments access_manager
              where access_manager.program_id = p.id and access_manager.is_active = true
                and access_manager.workstream_id = access_workstream.id
                and access_manager.assignment_role = 'workstream_lead'
                and access_manager.user_id = %s::uuid
          ))
    ))"""


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


def can_edit_milestone(
    user: CampaignOpsUser | None,
    program: Program,
    milestone: Milestone,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can edit milestone fields or status."""
    if is_administrator(user):
        return True
    if not is_team_member(user) or not program.is_active or not milestone.is_active:
        return False
    if milestone.owner_user_id == user.id:
        return True
    if milestone.workstream_id:
        return user_has_assignment(
            user,
            assignments,
            program_id=program.id,
            workstream_id=milestone.workstream_id,
        )
    return False


def can_manage_milestone_state(
    user: CampaignOpsUser | None,
    _program: Program,
    _milestone: Milestone,
    _assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can deactivate or reactivate a milestone."""
    return is_administrator(user)


def can_edit_resource(
    user: CampaignOpsUser | None,
    program: Program,
    resource: Resource,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can edit a program resource."""
    if is_administrator(user):
        return True
    if not is_team_member(user) or not program.is_active or not resource.is_active:
        return False
    if resource.workstream_id:
        return user_has_assignment(
            user,
            assignments,
            program_id=program.id,
            workstream_id=resource.workstream_id,
        )
    return False


def can_manage_resource_state(
    user: CampaignOpsUser | None,
    _program: Program,
    _resource: Resource,
    _assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can deactivate or reactivate a resource."""
    return is_administrator(user)


def can_add_note(
    user: CampaignOpsUser | None,
    program: Program,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can append a note to a program."""
    return program.is_active and can_view_program(user, program, assignments)


def can_view_internal_notes(
    user: CampaignOpsUser | None,
    program: Program,
    assignments: list[ProgramAssignment],
) -> bool:
    """Return whether a user can view internal notes."""
    if is_administrator(user):
        return True
    if is_team_member(user):
        return user_has_assignment(user, assignments, program_id=program.id)
    return False


def can_access_admin(user: CampaignOpsUser | None) -> bool:
    """Return whether a user can access Campaign Operations administration."""
    return is_administrator(user)
