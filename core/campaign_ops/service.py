from __future__ import annotations

from datetime import date, timedelta
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
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
    ContentDeliverableRecord,
    ContentInvoiceCheckpointRecord,
    ContentMonitoringUpdateRecord,
    ContentPortfolioRow,
    ContentProgramDetail,
    ContentProgramRecord,
    ContentSkuGroupRecord,
    ContentSkuRecord,
    ContentSubmissionRecord,
    CrossTeamDashboardSummary,
    DashboardMetricSet,
    DashboardProgramRow,
    DashboardTaskRow,
    DashboardWorkflowCard,
    InfluencerApprovalRoundRecord,
    InfluencerCampaignDetail,
    InfluencerCampaignRecord,
    InfluencerContentRoundRecord,
    InfluencerCreatorSummaryRecord,
    InfluencerCreatorWaveRecord,
    InfluencerLiveCheckpointRecord,
    InfluencerLiveCreatorRecord,
    InfluencerLiveExceptionRecord,
    InfluencerLivePortfolioRow,
    InfluencerLiveWorkspaceSummary,
    InfluencerPlanningPortfolioRow,
    InfluencerPlanningStepRecord,
    InfluencerCreatorCloseoutSummary,
    InfluencerRecapCheckpointRecord,
    InfluencerRecapLaunchItemRecord,
    InfluencerRecapPortfolioRow,
    InfluencerRecapRecord,
    InfluencerRecapRequirementRecord,
    InfluencerRecapWorkspaceSummary,
    InsightsObjectiveRecord,
    InsightsPortfolioRow,
    InsightsProjectDetail,
    InsightsProjectRecord,
    Milestone,
    MilestoneListRow,
    NeedsAttentionRow,
    NoteListRow,
    Program,
    ProgramAssignment,
    ProgramPortfolioRow,
    ProgramWorkspaceSummary,
    ProgramNote,
    ReportingRequestDetail,
    ReportingRequestListRow,
    ReportingRequestRecord,
    RetailMediaActivationRecord,
    RetailMediaCampaignDetail,
    RetailMediaCampaignRecord,
    RetailMediaChannelRecord,
    RetailMediaCreativeRecord,
    RetailMediaOptimizationRecord,
    RetailMediaPortfolioRow,
    Resource,
    ResourceListRow,
    Task,
    TaskListRow,
    UpcomingMilestoneRow,
    WaitingOnRow,
    WorkloadByPersonRow,
    Workstream,
    enum_value,
    require_text,
)
from core.campaign_ops.permissions import (
    can_access_admin,
    can_add_note,
    can_edit_program,
    can_edit_milestone,
    can_edit_resource,
    can_edit_task,
    can_edit_workstream,
    can_manage_assignments,
    can_manage_milestone_state,
    can_manage_resource_state,
    can_manage_task_state,
    can_view_internal_notes,
    can_view_program,
)
from core.campaign_ops.reporting_requests import (
    REQUEST_CATEGORY_REPORT,
    REQUEST_CATEGORY_SURVEY,
    REQUEST_STATUS_COMPLETED,
    REQUEST_STATUS_DELIVERED,
    REQUEST_STATUS_READY_FOR_REVIEW,
    REQUEST_STATUS_REQUESTED,
    REQUEST_STATUS_WAITING_FOR_APPROVAL,
    normalize_am_name,
    validate_request_category,
    validate_request_status,
)
from core.campaign_ops.insights import (
    INSIGHTS_RESOURCE_TYPES,
    INSIGHTS_STATUS_NOT_STARTED,
    validate_insights_status,
)
from core.campaign_ops.content_management import (
    CONTENT_RESOURCE_TYPES,
    CONTENT_STATUS_COMPLETE,
    CONTENT_STATUS_LIVE,
    CONTENT_STATUS_NOT_STARTED,
    COPY_STATUSES,
    GRAPHICS_STATUSES,
    PUBLICATION_STATUSES,
    SUBMISSION_STATUSES,
    normalize_content_status,
    normalize_optional_status,
)
from core.campaign_ops.influencer import (
    APPROVAL_STATUSES,
    APPROVAL_TYPES,
    CONTENT_ROUND_STATUSES,
    CONTENT_ROUND_TYPES,
    INFLUENCER_RESOURCE_TYPES,
    INFLUENCER_STAGE_LIVE,
    INFLUENCER_STAGE_PLANNING,
    INFLUENCER_STAGE_RECAPPING,
    INFLUENCER_STAGE_COMPLETE,
    LIVE_CHECKPOINT_STATUSES,
    LIVE_EXCEPTION_STATUSES,
    LIVE_EXCEPTION_TYPES,
    LIVE_RESOURCE_TYPES,
    LIVE_STATUS_READY_TO_LAUNCH,
    LIVE_STATUSES,
    PLANNING_STATUS_ON_HOLD,
    PLANNING_STATUS_NOT_STARTED,
    PLANNING_STEP_STATUSES,
    RECAP_CHECKPOINT_STATUSES,
    RECAP_LAUNCH_STATUSES,
    RECAP_REQUIREMENT_STATUSES,
    RECAP_REQUIREMENT_TYPES,
    RECAP_RESOURCE_TYPES,
    RECAP_STATUS_COMPLETE,
    RECAP_STATUS_READY_TO_CLOSE,
    RECAP_STATUS_READY_TO_RECAP,
    RECAP_STATUSES,
    RESPONSIBLE_PARTIES,
    STANDARD_LIVE_CHECKPOINT_TEMPLATE,
    STANDARD_PLANNING_TEMPLATE,
    STANDARD_RECAP_CHECKLIST_TEMPLATE,
    WAVE_STATUSES,
    CREATOR_APPROVAL_STATUSES,
    CREATOR_DRAFT_STATUSES,
    CREATOR_LIVE_STATUSES,
    normalize_influencer_stage,
    normalize_live_status,
    normalize_optional_status as normalize_influencer_optional_status,
    normalize_planning_status,
    normalize_recap_status,
)
from core.campaign_ops.retail_media import (
    RETAIL_MEDIA_RESOURCE_TYPES,
    RETAIL_MEDIA_STATUS_COMPLETE,
    RETAIL_MEDIA_STATUS_NOT_STARTED,
    normalize_approval_status,
    normalize_retail_media_status,
    normalize_submission_status,
)
from core.campaign_ops.repository import CampaignOpsRepository

WAITING_TASK_STATUSES = {
    TaskStatus.WAITING_ON_CLIENT.value,
    TaskStatus.WAITING_ON_CREATOR.value,
    TaskStatus.WAITING_ON_INTERNAL_TEAM.value,
}

ALLOWED_RESOURCE_URL_SCHEMES = {"http", "https"}
REPORTING_REQUEST_EDITABLE_FIELDS = {
    "program_id",
    "workstream_id",
    "request_category",
    "request_type",
    "am_user_id",
    "assigned_user_id",
    "due_date",
    "recap_date_with_client",
    "recap_date_text",
    "brief_url",
    "brief_status_text",
    "delivered",
    "review_required",
    "review_complete",
    "approval_required",
    "approved",
    "questions_requested",
    "special_requests",
    "status",
    "risk",
    "waiting_on",
    "completed_at",
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

    def _validate_milestone_dates(
        self,
        start_date: date | None,
        target_date: date | None,
        end_date: date | None,
    ) -> None:
        if start_date and target_date and target_date < start_date:
            raise CampaignOpsValidationError("Target date cannot precede start date.")
        if start_date and end_date and end_date < start_date:
            raise CampaignOpsValidationError("End date cannot precede start date.")

    def _validate_milestone_owner(
        self,
        repository: CampaignOpsRepository,
        owner_user_id: str | None,
    ) -> None:
        if owner_user_id:
            self._require_active_user(repository, owner_user_id, "Owner")

    def _validate_resource_url(self, url: str | None) -> str | None:
        cleaned = url.strip() if isinstance(url, str) else None
        if not cleaned:
            return None
        parsed = urlparse(cleaned)
        if not parsed.scheme:
            raise CampaignOpsValidationError("URL must include http:// or https://.")
        if parsed.scheme.lower() not in ALLOWED_RESOURCE_URL_SCHEMES:
            raise CampaignOpsValidationError("URL scheme is not allowed.")
        if not parsed.netloc:
            raise CampaignOpsValidationError("URL host is required.")
        return cleaned

    def _validate_resource_type(self, resource_type: str | None) -> str:
        return require_text(resource_type, "Resource type")

    def _validate_note_scope(
        self,
        repository: CampaignOpsRepository,
        program_id: str,
        workstream_id: str | None,
        task_id: str | None,
    ) -> None:
        if workstream_id:
            self._require_workstream(repository, program_id, workstream_id)
        if task_id:
            task = self._require_task(repository, task_id)
            if task.program_id != program_id:
                raise CampaignOpsValidationError("Task must belong to this program.")
            if workstream_id and task.workstream_id and task.workstream_id != workstream_id:
                raise CampaignOpsValidationError("Task does not belong to the selected workstream.")

    def _require_milestone(
        self,
        repository: CampaignOpsRepository,
        milestone_id: str,
    ) -> Milestone:
        milestone = repository.get_milestone(milestone_id)
        if milestone is None:
            raise CampaignOpsNotFoundError("Milestone was not found.")
        return milestone

    def _require_resource(
        self,
        repository: CampaignOpsRepository,
        resource_id: str,
    ) -> Resource:
        resource = repository.get_resource(resource_id)
        if resource is None:
            raise CampaignOpsNotFoundError("Resource was not found.")
        return resource

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

    def normalize_waiting_on_category(self, value: str | None) -> str:
        text = (value or "").strip().lower().replace("_", " ")
        if not text or text == "none":
            return "Other"
        if "client" in text:
            return "Client"
        if "internal" in text or "team" in text:
            return "Internal Team"
        if "creator" in text or "influencer" in text:
            return "Creator / Influencer"
        if "retailer" in text:
            return "Retailer"
        if "platform" in text:
            return "Platform"
        if "vendor" in text:
            return "Vendor"
        if "asset" in text:
            return "Assets"
        if "approval" in text:
            return "Approval"
        if "feedback" in text or "review" in text:
            return "Feedback"
        if "data" in text or "report" in text:
            return "Data"
        return "Other"

    def calculate_days_overdue(self, due_date: date | None, today: date | None = None) -> int | None:
        if due_date is None:
            return None
        today = today or date.today()
        return max((today - due_date).days, 0)

    def calculate_days_until(self, target_date: date | None, today: date | None = None) -> int | None:
        if target_date is None:
            return None
        today = today or date.today()
        return (target_date - today).days

    def calculate_attention_severity(
        self,
        reason: str,
        days_overdue: int | None = None,
        hard_deadline: bool = False,
        risk: str | None = None,
        highlighted: bool = False,
    ) -> str:
        if hard_deadline and (days_overdue or 0) > 0:
            return "Critical"
        if highlighted and (days_overdue or 0) > 0:
            return "Critical"
        if risk in {RiskLevel.AT_RISK.value} and (days_overdue or 0) > 0:
            return "Critical"
        if (days_overdue or 0) > 0:
            return "High"
        if reason in {"High Risk", "Influencer On Hold", "Retail Media Over Budget"}:
            return "High"
        if reason in {"Needs Attention Risk", "Waiting on Client", "Waiting on Internal Team", "Retail Media Paused"}:
            return "Medium"
        return "Low"

    def derive_specialized_stage(
        self,
        program_id: str,
        influencer_rows: list[Any],
        retail_rows: list[RetailMediaPortfolioRow],
        content_rows: list[ContentPortfolioRow],
        insights_rows: list[InsightsPortfolioRow],
        request_rows: list[ReportingRequestListRow],
    ) -> str | None:
        stages: list[str] = []
        for row in influencer_rows:
            if row.program_id == program_id:
                status = getattr(row, "recap_status", None) or getattr(row, "live_status", None) or getattr(row, "planning_status", None)
                stages.append(f"Influencer: {getattr(row, 'influencer_stage', '-')}/{status or '-'}")
        for row in retail_rows:
            if row.program_id == program_id:
                stages.append(f"Retail Media: {row.retail_media_status or '-'}")
        for row in content_rows:
            if row.program_id == program_id:
                stages.append(f"Content: {row.content_status or '-'}")
        for row in insights_rows:
            if row.program_id == program_id:
                stages.append(f"Insights: {row.insights_status or '-'}")
        req_count = len([row for row in request_rows if row.program_id == program_id])
        if req_count:
            stages.append(f"Requests: {req_count} open")
        return "; ".join(stages[:4]) if stages else None

    def validate_cross_team_person_view(self, actor: CampaignOpsUser | None, person_view: str | None) -> str:
        if can_access_admin(actor):
            return person_view or "Cross-Team"
        if actor is None:
            raise CampaignOpsPermissionError("A Campaign Operations user is required.")
        return actor.display_name

    def validate_cross_team_filters(self, actor: CampaignOpsUser | None, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = dict(filters or {})
        filters["person_view"] = self.validate_cross_team_person_view(actor, filters.get("person_view"))
        filters["include_test_records"] = bool(filters.get("include_test_records", False))
        filters["upcoming_days"] = self._non_negative_int(filters.get("upcoming_days", 14), "Upcoming days") or 14
        if filters.get("owner_user_id"):
            self._require_active_user(self.repository or CampaignOpsRepository(), str(filters["owner_user_id"]), "Owner")
        if filters.get("assigned_user_id"):
            self._require_active_user(self.repository or CampaignOpsRepository(), str(filters["assigned_user_id"]), "Assigned person")
        for key, enum_type, label in (
            ("primary_workflow", WorkstreamType, "Primary workflow"),
            ("connected_workstream", WorkstreamType, "Connected workstream"),
            ("cross_stage", CrossStage, "Cross stage"),
            ("program_status", ProgramStatus, "Program status"),
            ("risk", RiskLevel, "Risk"),
            ("waiting_on", WaitingOn, "Waiting on"),
        ):
            if filters.get(key):
                filters[key] = enum_value(enum_type, filters[key], label)
        return filters

    def _dashboard_program_filters(self, actor: CampaignOpsUser | None, filters: dict[str, Any]) -> dict[str, Any]:
        active_state = filters.get("active_state") or "active"
        portfolio_active_state = "archived" if active_state == "inactive" else active_state
        program_filters = {
            "search": filters.get("search"),
            "client_id": filters.get("client_id"),
            "program_name": filters.get("program_name"),
            "primary_workstream_type": filters.get("primary_workflow"),
            "connected_workstream_type": filters.get("connected_workstream"),
            "cross_stage": filters.get("cross_stage"),
            "status": filters.get("program_status"),
            "risk_level": filters.get("risk"),
            "primary_owner_user_id": filters.get("owner_user_id"),
            "assigned_user_id": filters.get("assigned_user_id"),
            "active_state": portfolio_active_state,
            "sort_by": filters.get("sort_by", "recently_updated"),
        }
        person_view = filters.get("person_view")
        if person_view and person_view != "Cross-Team":
            user = (self.repository or CampaignOpsRepository()).get_user_by_display_name(person_view)
            if user:
                if filters.get("owner_or_assigned", True):
                    program_filters.pop("primary_owner_user_id", None)
                    program_filters.pop("assigned_user_id", None)
                else:
                    program_filters["assigned_user_id"] = user.id
        return program_filters

    def _filter_test_programs(self, rows: list[ProgramPortfolioRow], include_test_records: bool) -> list[ProgramPortfolioRow]:
        if include_test_records:
            return rows
        return [row for row in rows if not row.program_name.upper().startswith("TEST -")]

    def _dashboard_visible_programs(self, actor: CampaignOpsUser | None, filters: dict[str, Any]) -> list[ProgramPortfolioRow]:
        rows = self.list_program_portfolio(actor, self._dashboard_program_filters(actor, filters))
        rows = self._filter_test_programs(rows, filters.get("include_test_records", False))
        person_view = filters.get("person_view")
        if person_view and person_view != "Cross-Team":
            user = (self.repository or CampaignOpsRepository()).get_user_by_display_name(person_view)
            if user:
                rows = [row for row in rows if row.primary_owner_user_id == user.id or user.id in row.assigned_user_ids]
        return rows

    def _matches_dashboard_filters(self, program: ProgramPortfolioRow, filters: dict[str, Any]) -> bool:
        start_from = filters.get("start_date_from")
        start_to = filters.get("start_date_to")
        end_from = filters.get("target_end_date_from")
        end_to = filters.get("target_end_date_to")
        if start_from and (program.start_date is None or program.start_date < start_from):
            return False
        if start_to and (program.start_date is None or program.start_date > start_to):
            return False
        if end_from and (program.target_end_date is None or program.target_end_date < end_from):
            return False
        if end_to and (program.target_end_date is None or program.target_end_date > end_to):
            return False
        return True

    def _milestone_row_from_dashboard_raw(self, row: dict[str, Any], today: date) -> UpcomingMilestoneRow:
        best_date = row.get("target_date") or row.get("start_date") or row.get("end_date")
        return UpcomingMilestoneRow(
            id=str(row["id"]),
            program_id=str(row["program_id"]),
            milestone=str(row["title"]),
            program_name=str(row["program_name"]),
            client_name=row.get("client_name"),
            workstream=row.get("workstream_type"),
            owner_user_id=str(row["owner_user_id"]) if row.get("owner_user_id") else None,
            owner_name=row.get("owner_user_name"),
            status=str(row["status"]),
            best_available_date=best_date,
            days_until=self.calculate_days_until(best_date, today),
            hard_deadline=bool(row.get("hard_deadline", False)),
            highlighted=bool(row.get("is_highlighted", False)),
        )

    def _dashboard_task_row(self, task: TaskListRow, today: date) -> DashboardTaskRow:
        return DashboardTaskRow(
            id=task.id,
            program_id=task.program_id,
            task=task.title,
            program_name=task.program_name,
            client_name=task.client_name,
            workstream=task.workstream_type,
            assigned_user_id=task.assigned_user_id,
            assigned_user_name=task.assigned_user_name,
            responsible_party=task.responsible_party,
            status=task.status,
            risk=task.risk_level,
            due_date=task.due_date,
            days_overdue=self.calculate_days_overdue(task.due_date, today) or 0,
            waiting_on=task.waiting_on,
            hard_deadline=task.hard_deadline,
        )

    def _attention_row(
        self,
        key: str,
        program: ProgramPortfolioRow,
        workflow: str,
        reason: str,
        due_date: date | None,
        today: date,
        owner_user_id: str | None = None,
        owner_name: str | None = None,
        assigned_user_id: str | None = None,
        assigned_name: str | None = None,
        stage: str | None = None,
        waiting_on: str | None = None,
        latest_update: str | None = None,
        hard_deadline: bool = False,
        highlighted: bool = False,
        target_section: str = "Program Workspace",
        target_record_id: str | None = None,
    ) -> NeedsAttentionRow:
        days = self.calculate_days_overdue(due_date, today)
        return NeedsAttentionRow(
            id=key,
            program_id=program.id,
            program_name=program.program_name,
            client_name=program.client_name,
            workflow=workflow,
            stage=stage or program.cross_stage,
            owner_user_id=owner_user_id or program.primary_owner_user_id,
            owner_name=owner_name or program.primary_owner_name,
            assigned_user_id=assigned_user_id,
            assigned_name=assigned_name,
            attention_reason=reason,
            severity=self.calculate_attention_severity(reason, days, hard_deadline, program.risk_level, highlighted),
            risk=program.risk_level,
            waiting_on=waiting_on,
            due_date=due_date,
            days_overdue=days,
            latest_update=latest_update or program.latest_update,
            target_section=target_section,
            target_record_id=target_record_id,
        )

    def _waiting_row(
        self,
        key: str,
        program: ProgramPortfolioRow,
        workflow: str,
        record_type: str,
        item: str,
        waiting_on: str | None,
        due_date: date | None,
        today: date,
        owner_user_id: str | None = None,
        owner_name: str | None = None,
        latest_update: str | None = None,
        target_section: str = "Program Workspace",
        target_record_id: str | None = None,
    ) -> WaitingOnRow:
        return WaitingOnRow(
            id=key,
            program_id=program.id,
            program_name=program.program_name,
            client_name=program.client_name,
            workflow=workflow,
            record_type=record_type,
            item=item,
            owner_user_id=owner_user_id or program.primary_owner_user_id,
            owner_name=owner_name or program.primary_owner_name,
            waiting_on=waiting_on,
            waiting_category=self.normalize_waiting_on_category(waiting_on),
            due_date=due_date,
            age=self.calculate_days_overdue(due_date, today),
            latest_update=latest_update or program.latest_update,
            target_section=target_section,
            target_record_id=target_record_id,
        )

    def _sort_attention(self, rows: list[NeedsAttentionRow]) -> list[NeedsAttentionRow]:
        severity_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        deduped = {f"{row.program_id}:{row.workflow}:{row.attention_reason}:{row.target_record_id or row.id}": row for row in rows}
        return sorted(deduped.values(), key=lambda row: (severity_rank.get(row.severity, 9), row.due_date or date.max, row.program_name))

    def prioritize_workflow_cards(self, cards: list[DashboardWorkflowCard], limit: int = 2) -> list[DashboardWorkflowCard]:
        return sorted(cards, key=lambda card: (not card.needs_attention, card.next_date or date.max, card.title))[:limit]

    def get_cross_team_dashboard_summary(self, actor: CampaignOpsUser | None, filters: dict[str, Any] | None = None) -> CrossTeamDashboardSummary:
        filters = self.validate_cross_team_filters(actor, filters)
        today = date.today()
        week_end = today + timedelta(days=6 - today.weekday())
        upcoming_end = today + timedelta(days=int(filters.get("upcoming_days", 14)))
        repository = self.repository or CampaignOpsRepository()
        permitted_user_id = None if can_access_admin(actor) else actor.id if actor else ""
        programs = [row for row in self._dashboard_visible_programs(actor, filters) if self._matches_dashboard_filters(row, filters)]
        program_ids = {row.id for row in programs}
        program_map = {row.id: row for row in programs}
        include_child_inactive = filters.get("active_state") in {"inactive", "all"}
        tasks = [row for row in repository.list_dashboard_task_rows(include_inactive=include_child_inactive, permitted_user_id=permitted_user_id) if row.program_id in program_ids]
        milestone_raw = [row for row in repository.list_dashboard_milestone_rows(include_inactive=include_child_inactive, permitted_user_id=permitted_user_id) if str(row["program_id"]) in program_ids]
        milestones = [self._milestone_row_from_dashboard_raw(row, today) for row in milestone_raw]
        resources = [row for row in repository.list_dashboard_resource_rows(include_inactive=include_child_inactive, permitted_user_id=permitted_user_id) if row.program_id in program_ids]
        influencer_planning = [row for row in self.list_influencer_campaigns(actor, include_inactive=True, stage=INFLUENCER_STAGE_PLANNING) if row.program_id in program_ids]
        influencer_live = [row for row in self.list_influencer_live_campaigns(actor, include_inactive=True) if row.program_id in program_ids]
        influencer_recap = [row for row in self.list_influencer_recap_campaigns(actor, include_inactive=True) if row.program_id in program_ids]
        retail_rows = [row for row in self.list_retail_media_campaigns(actor, include_inactive=True) if row.program_id in program_ids]
        content_rows = [row for row in self.list_content_programs(actor, include_inactive=True) if row.program_id in program_ids]
        insights_rows = [row for row in self.list_insights_projects(actor, include_inactive=True) if row.program_id in program_ids]
        request_rows = [row for row in self.list_reporting_requests(actor, include_inactive=True) if row.program_id in program_ids]

        def waiting_filter(value: str | None) -> bool:
            return not filters.get("waiting_on") or value == filters.get("waiting_on") or self.normalize_waiting_on_category(value) == self.normalize_waiting_on_category(filters.get("waiting_on"))

        attention: list[NeedsAttentionRow] = []
        for program in programs:
            if program.risk_level == RiskLevel.AT_RISK.value:
                attention.append(self._attention_row(f"risk-high-{program.id}", program, "Shared", "High Risk", program.target_end_date, today))
            if program.risk_level == RiskLevel.NEEDS_ATTENTION.value:
                attention.append(self._attention_row(f"risk-needs-{program.id}", program, "Shared", "Needs Attention Risk", program.target_end_date, today))
        for task in tasks:
            if task.status not in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value} and task.due_date and task.due_date < today:
                program = program_map[task.program_id]
                attention.append(self._attention_row(f"task-{task.id}", program, task.workstream_type or "Shared", "Overdue Task", task.due_date, today, assigned_user_id=task.assigned_user_id, assigned_name=task.assigned_user_name, waiting_on=task.waiting_on, hard_deadline=task.hard_deadline, target_record_id=task.id))
        for milestone in milestones:
            if milestone.status != TaskStatus.COMPLETED.value and milestone.best_available_date and milestone.best_available_date < today:
                program = program_map[milestone.program_id]
                attention.append(self._attention_row(f"milestone-{milestone.id}", program, milestone.workstream or "Shared", "Overdue Milestone", milestone.best_available_date, today, owner_user_id=milestone.owner_user_id, owner_name=milestone.owner_name, hard_deadline=milestone.hard_deadline, highlighted=milestone.highlighted, target_record_id=milestone.id))
        for resource in resources:
            if resource.is_required and not resource.url:
                program = program_map[resource.program_id]
                attention.append(self._attention_row(f"resource-{resource.id}", program, resource.workstream_type or "Shared", "Missing Required Resource", None, today, target_record_id=resource.id))

        waiting: list[WaitingOnRow] = []
        for task in tasks:
            if task.waiting_on and task.waiting_on != WaitingOn.NONE.value and waiting_filter(task.waiting_on):
                waiting.append(self._waiting_row(f"task-{task.id}", program_map[task.program_id], task.workstream_type or "Shared", "Task", task.title, task.waiting_on, task.due_date, today, owner_user_id=task.assigned_user_id, owner_name=task.assigned_user_name, target_record_id=task.id))

        influencer_cards: list[DashboardWorkflowCard] = []
        for row in [*influencer_planning, *influencer_live, *influencer_recap]:
            program = program_map[row.program_id]
            stage = getattr(row, "influencer_stage", None)
            status = getattr(row, "recap_status", None) or getattr(row, "live_status", None) or getattr(row, "planning_status", None)
            next_item = getattr(row, "next_planning_step", None) or getattr(row, "next_checkpoint", None)
            next_date = getattr(row, "next_planning_step_due_date", None) or getattr(row, "next_checkpoint_due_date", None) or getattr(row, "wrap_date", None)
            needs = bool(getattr(row, "is_on_hold", False) or getattr(row, "open_exception_count", 0) or getattr(row, "open_requirement_count", 0) or program.risk_level in {RiskLevel.AT_RISK.value, RiskLevel.NEEDS_ATTENTION.value})
            if getattr(row, "is_on_hold", False):
                attention.append(self._attention_row(f"influencer-hold-{row.id}", program, "Influencer", "Influencer On Hold", getattr(row, "launch_date", None), today, owner_user_id=row.manager_user_id, owner_name=row.manager_display_name, stage=stage, waiting_on=getattr(row, "waiting_on", None), latest_update=getattr(row, "latest_update", None), target_section="Influencer", target_record_id=row.id))
            if getattr(row, "open_exception_count", 0):
                attention.append(self._attention_row(f"influencer-exception-{row.id}", program, "Influencer", "Influencer Live Exception", next_date, today, owner_user_id=row.manager_user_id, owner_name=row.manager_display_name, stage=stage, waiting_on=getattr(row, "waiting_on", None), latest_update=getattr(row, "latest_update", None), target_section="Influencer", target_record_id=row.id))
            if getattr(row, "open_requirement_count", 0):
                attention.append(self._attention_row(f"influencer-recap-req-{row.id}", program, "Influencer", "Influencer Recap Requirement", getattr(row, "reporting_due_date", None), today, owner_user_id=row.manager_user_id, owner_name=row.manager_display_name, stage=stage, waiting_on=getattr(row, "waiting_on", None), latest_update=getattr(row, "latest_update", None), target_section="Influencer", target_record_id=row.id))
            if getattr(row, "waiting_on", None) and waiting_filter(getattr(row, "waiting_on", None)):
                waiting.append(self._waiting_row(f"influencer-{row.id}", program, "Influencer", "Influencer Campaign", row.campaign_title, getattr(row, "waiting_on", None), next_date, today, owner_user_id=row.manager_user_id, owner_name=row.manager_display_name, latest_update=getattr(row, "latest_update", None), target_section="Influencer", target_record_id=row.id))
            influencer_cards.append(DashboardWorkflowCard(row.id, row.program_id, row.campaign_title, row.client_name, "Influencer", row.manager_user_id, row.manager_display_name, stage, status, getattr(row, "latest_update", None), getattr(row, "waiting_on", None), next_item, next_date, row.program_risk, needs, f"Creators: {getattr(row, 'live_creator_count', getattr(row, 'approved_creator_count', 0)) or 0}; Exceptions: {getattr(row, 'open_exception_count', 0)}; Ready: {getattr(row, 'ready_to_close_state', '-')}", "Influencer"))

        retail_cards: list[DashboardWorkflowCard] = []
        for row in retail_rows:
            program = program_map[row.program_id]
            over_budget = bool((row.total_spend or row.channel_spend_total or 0) > (row.overall_budget or row.channel_budget_total or 0) > 0)
            needs = over_budget or row.is_paused or program.risk_level in {RiskLevel.AT_RISK.value, RiskLevel.NEEDS_ATTENTION.value}
            if over_budget:
                attention.append(self._attention_row(f"retail-budget-{row.id}", program, "Retail Media", "Retail Media Over Budget", row.wrap_date, today, owner_user_id=row.owner_user_id, owner_name=row.owner_display_name, stage=row.retail_media_status, waiting_on=row.waiting_on, latest_update=row.latest_update, target_section="Retail Media", target_record_id=row.id))
            if row.is_paused:
                attention.append(self._attention_row(f"retail-paused-{row.id}", program, "Retail Media", "Retail Media Paused", row.launch_date, today, owner_user_id=row.owner_user_id, owner_name=row.owner_display_name, stage=row.retail_media_status, waiting_on=row.waiting_on, latest_update=row.latest_update, target_section="Retail Media", target_record_id=row.id))
            if row.waiting_on and waiting_filter(row.waiting_on):
                waiting.append(self._waiting_row(f"retail-{row.id}", program, "Retail Media", "Retail Media Campaign", row.campaign_title, row.waiting_on, row.next_milestone_date, today, owner_user_id=row.owner_user_id, owner_name=row.owner_display_name, latest_update=row.latest_update, target_section="Retail Media", target_record_id=row.id))
            retail_cards.append(DashboardWorkflowCard(row.id, row.program_id, row.campaign_title, row.client_name, "Retail Media", row.owner_user_id, row.owner_display_name, None, row.retail_media_status, row.latest_update, row.waiting_on, row.next_milestone, row.next_milestone_date, row.program_risk, needs, f"Channels: {', '.join(row.channel_mix) or '-'}; Budget: {row.overall_budget or row.channel_budget_total or 0}; Spend: {row.total_spend or row.channel_spend_total or 0}", "Retail Media"))

        content_cards: list[DashboardWorkflowCard] = []
        for row in content_rows:
            program = program_map[row.program_id]
            needs = row.issue_count > 0 or program.risk_level in {RiskLevel.AT_RISK.value, RiskLevel.NEEDS_ATTENTION.value}
            if row.issue_count > 0:
                attention.append(self._attention_row(f"content-issue-{row.id}", program, "eCommerce / Content", "Content Publication Issue", row.next_milestone_date or row.maintenance_end_date, today, owner_user_id=row.owner_user_id, owner_name=row.owner_display_name, stage=row.content_status, waiting_on=row.waiting_on, latest_update=row.latest_update, target_section="eCommerce / Content", target_record_id=row.id))
            if row.waiting_on and waiting_filter(row.waiting_on):
                waiting.append(self._waiting_row(f"content-{row.id}", program, "eCommerce / Content", "Content Program", row.content_program_title, row.waiting_on, row.next_milestone_date, today, owner_user_id=row.owner_user_id, owner_name=row.owner_display_name, latest_update=row.latest_update, target_section="eCommerce / Content", target_record_id=row.id))
            content_cards.append(DashboardWorkflowCard(row.id, row.program_id, row.content_program_title, row.client_name, "eCommerce / Content", row.owner_user_id, row.owner_display_name, None, row.content_status, row.latest_update, row.waiting_on, row.next_milestone, row.next_milestone_date, row.program_risk, needs, f"SKUs: {row.total_sku_count or row.active_sku_count}; Live: {row.live_count}; Issues: {row.issue_count}", "eCommerce / Content"))

        insights_cards: list[DashboardWorkflowCard] = []
        for row in insights_rows:
            program = program_map[row.program_id]
            missing = not (row.tracksheet_url or row.results_deck_url or row.raw_data_url)
            if missing:
                attention.append(self._attention_row(f"insights-resource-{row.id}", program, "Insights", "Missing Required Resource", row.next_milestone_date, today, owner_user_id=row.owner_user_id, owner_name=row.owner_display_name, stage=row.insights_status, latest_update=row.latest_update, target_section="Insights", target_record_id=row.id))
            if row.next_milestone_date and row.next_milestone_date < today:
                attention.append(self._attention_row(f"insights-milestone-{row.id}", program, "Insights", "Insights Overdue Milestone", row.next_milestone_date, today, owner_user_id=row.owner_user_id, owner_name=row.owner_display_name, stage=row.insights_status, latest_update=row.latest_update, target_section="Insights", target_record_id=row.id))
            insights_cards.append(DashboardWorkflowCard(row.id, row.program_id, row.project_title, row.client_name, "Insights", row.owner_user_id, row.owner_display_name, None, row.insights_status, row.latest_update, None, row.next_milestone, row.next_milestone_date, row.program_risk, missing, f"Job: {row.job_number or '-'}; Sample: {row.sample_size or '-'}; Budget: {row.budget or '-'}", "Insights"))

        request_cards: list[DashboardWorkflowCard] = []
        for row in request_rows:
            program = program_map[row.program_id]
            reason = "Survey Request Overdue" if row.request_category == REQUEST_CATEGORY_SURVEY else "Reporting Request Overdue"
            if row.status != REQUEST_STATUS_COMPLETED and row.due_date and row.due_date < today:
                attention.append(self._attention_row(f"request-{row.id}", program, "Reporting & Survey Requests", reason, row.due_date, today, owner_user_id=row.am_user_id, owner_name=row.am_display_name, assigned_user_id=row.assigned_user_id, assigned_name=row.assigned_display_name, stage=row.status, waiting_on=row.waiting_on, target_section="Requests", target_record_id=row.id))
            if row.waiting_on and waiting_filter(row.waiting_on):
                waiting.append(self._waiting_row(f"request-{row.id}", program, "Reporting & Survey Requests", "Request", row.request_type, row.waiting_on, row.due_date, today, owner_user_id=row.am_user_id, owner_name=row.am_display_name, latest_update=None, target_section="Requests", target_record_id=row.id))
            label = "Survey Request" if row.request_category == REQUEST_CATEGORY_SURVEY else "Reporting Request"
            request_cards.append(DashboardWorkflowCard(row.id, row.program_id, f"{label}: {row.request_type}", row.client_name, "Reporting & Survey Requests", row.am_user_id, row.am_display_name, None, row.status, None, row.waiting_on, "Due", row.due_date, row.risk, bool(row.due_date and row.due_date < today), f"Delivered: {row.delivered}; Review: {row.review_complete}; Approval: {row.approved}", "Requests"))

        overdue_tasks = [self._dashboard_task_row(task, today) for task in tasks if task.status not in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value} and task.due_date and task.due_date < today]
        upcoming_milestones = [row for row in milestones if row.status != TaskStatus.COMPLETED.value and row.best_available_date and today <= row.best_available_date <= upcoming_end]
        attention = self._sort_attention(attention)
        if filters.get("needs_attention_only"):
            program_ids = {row.program_id for row in attention}
            programs = [row for row in programs if row.id in program_ids]
        waiting = sorted(waiting, key=lambda row: (row.due_date or date.max, row.program_name, row.item))

        active_program_ids = {row.id for row in programs if row.is_active}
        completed_recently = [
            row for row in programs
            if row.status == ProgramStatus.COMPLETE.value and row.updated_at and row.updated_at.date() >= today - timedelta(days=7)
        ]
        metrics = DashboardMetricSet(
            active_programs=len(active_program_ids),
            needs_attention=len({row.program_id for row in attention}),
            high_risk=len([row for row in programs if row.risk_level == RiskLevel.AT_RISK.value]),
            overdue_tasks=len(overdue_tasks),
            due_this_week=len([task for task in tasks if task.status not in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value} and task.due_date and today <= task.due_date <= week_end]),
            upcoming_milestones=len(upcoming_milestones),
            waiting_on_client=len([row for row in waiting if row.waiting_category == "Client"]),
            waiting_on_internal_team=len([row for row in waiting if row.waiting_category == "Internal Team"]),
            paused_on_hold=len([row for row in programs if row.status == ProgramStatus.ON_HOLD.value or row.cross_stage == CrossStage.ON_HOLD.value]) + len([row for row in influencer_planning + influencer_live + influencer_recap if getattr(row, "is_on_hold", False)]) + len([row for row in retail_rows if row.is_paused]),
            ready_for_recap=len([row for row in influencer_live if getattr(row, "planning_status", None) == "ready_for_recap" or getattr(row, "live_status", None) == "ready_for_recap"]),
            ready_to_close=len([row for row in influencer_recap if row.ready_to_close_state == "Ready to Close" or row.recap_status == RECAP_STATUS_READY_TO_CLOSE]),
            completed_recently=len(completed_recently),
        )

        user_rows = [user for user in self.list_active_users() if user.display_name in {"Bailey", "T", "L"}]
        workload: list[WorkloadByPersonRow] = []
        attention_programs_by_user = {user.id: {row.program_id for row in attention if row.owner_user_id == user.id or row.assigned_user_id == user.id} for user in user_rows}
        for user in user_rows:
            assigned_program_ids = {program.id for program in programs if user.id in program.assigned_user_ids}
            workload.append(WorkloadByPersonRow(
                user_id=user.id,
                display_name=user.display_name,
                owned_active_programs=len([program for program in programs if program.primary_owner_user_id == user.id and program.is_active]),
                assigned_active_programs=len(assigned_program_ids),
                open_tasks=len([task for task in tasks if task.assigned_user_id == user.id and task.status not in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value}]),
                overdue_tasks=len([task for task in overdue_tasks if task.assigned_user_id == user.id]),
                due_this_week=len([task for task in tasks if task.assigned_user_id == user.id and task.due_date and today <= task.due_date <= week_end and task.status not in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value}]),
                active_milestones_owned=len([m for m in milestones if m.owner_user_id == user.id and m.status != TaskStatus.COMPLETED.value]),
                needs_attention_programs=len(attention_programs_by_user[user.id]),
                waiting_items=len([row for row in waiting if row.owner_user_id == user.id]),
                influencer_planning=len([row for row in influencer_planning if row.manager_user_id == user.id]),
                influencer_live=len([row for row in influencer_live if row.manager_user_id == user.id]),
                influencer_recapping=len([row for row in influencer_recap if row.manager_user_id == user.id]),
                reporting_requests=len([row for row in request_rows if row.am_user_id == user.id or row.assigned_user_id == user.id]),
                insights_projects=len([row for row in insights_rows if row.owner_user_id == user.id]),
                retail_media_campaigns=len([row for row in retail_rows if row.owner_user_id == user.id]),
                content_programs=len([row for row in content_rows if row.owner_user_id == user.id]),
            ))

        next_milestone_by_program = {}
        for milestone in upcoming_milestones:
            next_milestone_by_program.setdefault(milestone.program_id, milestone)
        attention_reasons_by_program: dict[str, list[str]] = {}
        for row in attention:
            attention_reasons_by_program.setdefault(row.program_id, [])
            if row.attention_reason not in attention_reasons_by_program[row.program_id]:
                attention_reasons_by_program[row.program_id].append(row.attention_reason)
        all_influencer_rows = [*influencer_planning, *influencer_live, *influencer_recap]
        program_rows = [
            DashboardProgramRow(
                id=program.id,
                program_name=program.program_name,
                client_name=program.client_name,
                primary_workflow=program.primary_workstream_type,
                connected_workstreams=program.workstream_types,
                program_status=program.status,
                cross_stage=program.cross_stage,
                specialized_stage=self.derive_specialized_stage(program.id, all_influencer_rows, retail_rows, content_rows, insights_rows, request_rows),
                risk=program.risk_level,
                priority=program.priority,
                primary_owner_user_id=program.primary_owner_user_id,
                primary_owner_name=program.primary_owner_name,
                assigned_people=program.assigned_user_names,
                latest_update=program.latest_update,
                waiting_on=None,
                open_tasks=program.open_task_count,
                overdue_tasks=program.overdue_task_count,
                next_task_due=program.nearest_task_due_date,
                next_milestone=next_milestone_by_program.get(program.id).milestone if program.id in next_milestone_by_program else None,
                needs_attention_reasons=attention_reasons_by_program.get(program.id, []),
                start_date=program.start_date,
                target_end_date=program.target_end_date,
                updated_at=program.updated_at,
                active_state="Active" if program.is_active else "Inactive",
            )
            for program in programs
        ]

        return CrossTeamDashboardSummary(
            metrics=metrics,
            needs_attention=attention,
            waiting_on=waiting,
            overdue_tasks=sorted(overdue_tasks, key=lambda row: (not row.hard_deadline, row.due_date or date.max, row.program_name)),
            upcoming_milestones=sorted(upcoming_milestones, key=lambda row: (row.best_available_date or date.max, not row.hard_deadline, row.program_name)),
            workload=workload,
            influencer_cards=self.prioritize_workflow_cards(influencer_cards),
            retail_media_cards=self.prioritize_workflow_cards(retail_cards),
            content_cards=self.prioritize_workflow_cards(content_cards),
            insights_cards=self.prioritize_workflow_cards(insights_cards),
            request_cards=self.prioritize_workflow_cards(request_cards),
            programs=program_rows,
        )

    def validate_cross_team_drillthrough(self, actor: CampaignOpsUser | None, program_id: str) -> Program:
        repository = self.repository or CampaignOpsRepository()
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this dashboard target.")
        return program

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

    def create_milestone(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        title: str,
        **kwargs: Any,
    ) -> Milestone:
        cleaned_title = require_text(title, "Title")

        def operation(repository: CampaignOpsRepository) -> Milestone:
            program = self._require_program(repository, program_id)
            assignments = repository.list_assignments_by_program(program_id)
            temp = Milestone(
                id="00000000-0000-4000-8000-000000000000",
                program_id=program_id,
                title=cleaned_title,
                status=kwargs.get("status") or TaskStatus.NOT_STARTED.value,
                owner_user_id=kwargs.get("owner_user_id"),
                workstream_id=kwargs.get("workstream_id"),
            )
            if not can_edit_milestone(actor, program, temp, assignments):
                raise CampaignOpsPermissionError("You do not have permission to create this milestone.")
            if not program.is_active:
                raise CampaignOpsValidationError("Archived programs cannot have milestone changes.")
            self._validate_task_workstream(repository, program_id, kwargs.get("workstream_id"))
            self._validate_milestone_owner(repository, kwargs.get("owner_user_id"))
            self._validate_milestone_dates(
                kwargs.get("start_date"),
                kwargs.get("target_date"),
                kwargs.get("end_date"),
            )
            status = enum_value(TaskStatus, kwargs.get("status") or TaskStatus.NOT_STARTED.value, "status")
            completed_at = datetime.now(UTC) if status == TaskStatus.COMPLETED.value else None
            milestone = repository.create_milestone(
                program_id=program_id,
                title=cleaned_title,
                actor_user_id=actor.id if actor else None,
                workstream_id=kwargs.get("workstream_id"),
                milestone_type=(kwargs.get("milestone_type") or "").strip() or None,
                target_date=kwargs.get("target_date"),
                start_date=kwargs.get("start_date"),
                end_date=kwargs.get("end_date"),
                status=status,
                owner_user_id=kwargs.get("owner_user_id"),
                hard_deadline=bool(kwargs.get("hard_deadline", False)),
                completed_at=completed_at,
                is_highlighted=bool(kwargs.get("is_highlighted", False)),
            )
            repository.append_event(
                event_type="milestone_created",
                entity_type="milestone",
                entity_id=milestone.id,
                program_id=program_id,
                workstream_id=milestone.workstream_id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"title": milestone.title, "status": milestone.status},
                message=f"{actor.display_name if actor else 'System'} created milestone {milestone.title}.",
            )
            return milestone

        return self._transaction(operation)

    def update_milestone_details(
        self,
        actor: CampaignOpsUser | None,
        milestone_id: str,
        **kwargs: Any,
    ) -> Milestone:
        def operation(repository: CampaignOpsRepository) -> Milestone:
            before = self._require_milestone(repository, milestone_id)
            program = self._require_program(repository, before.program_id)
            assignments = repository.list_assignments_by_program(before.program_id)
            if not can_edit_milestone(actor, program, before, assignments):
                raise CampaignOpsPermissionError("You do not have permission to edit this milestone.")
            if not program.is_active:
                raise CampaignOpsValidationError("Archived programs cannot have milestone changes.")
            if "title" in kwargs:
                kwargs["title"] = require_text(kwargs["title"], "Title")
            if "workstream_id" in kwargs:
                self._validate_task_workstream(repository, before.program_id, kwargs.get("workstream_id"))
            if "owner_user_id" in kwargs:
                self._validate_milestone_owner(repository, kwargs.get("owner_user_id"))
                if not can_access_admin(actor) and kwargs.get("owner_user_id") != before.owner_user_id:
                    raise CampaignOpsPermissionError("Team Members cannot reassign milestone owners.")
            self._validate_milestone_dates(
                kwargs.get("start_date", before.start_date),
                kwargs.get("target_date", before.target_date),
                kwargs.get("end_date", before.end_date),
            )
            if "status" in kwargs and kwargs["status"] is not None:
                kwargs["status"] = enum_value(TaskStatus, kwargs["status"], "status")
                kwargs["completed_at"] = (
                    before.completed_at or datetime.now(UTC)
                    if kwargs["status"] == TaskStatus.COMPLETED.value
                    else None
                )
            editable = {
                "title",
                "workstream_id",
                "milestone_type",
                "target_date",
                "start_date",
                "end_date",
                "status",
                "owner_user_id",
                "hard_deadline",
                "completed_at",
                "is_highlighted",
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
                "workstream_id": before.workstream_id,
                "milestone_type": before.milestone_type,
                "target_date": before.target_date,
                "start_date": before.start_date,
                "end_date": before.end_date,
                "status": before.status,
                "owner_user_id": before.owner_user_id,
                "hard_deadline": before.hard_deadline,
                "completed_at": before.completed_at,
                "is_highlighted": before.is_highlighted,
            }
            merged.update(changes)
            updated = repository.update_milestone(
                milestone_id,
                actor_user_id=actor.id if actor else None,
                **merged,
            )
            for field, value in changes.items():
                self._append_change_activity(
                    repository,
                    actor,
                    before.program_id,
                    "milestone",
                    milestone_id,
                    field,
                    getattr(before, field),
                    value,
                    updated.workstream_id,
                )
            return updated

        return self._transaction(operation)

    def complete_milestone(self, actor: CampaignOpsUser | None, milestone_id: str) -> Milestone:
        return self.update_milestone_details(actor, milestone_id, status=TaskStatus.COMPLETED.value)

    def reopen_milestone(
        self,
        actor: CampaignOpsUser | None,
        milestone_id: str,
        reopened_status: str = TaskStatus.IN_PROGRESS.value,
    ) -> Milestone:
        def operation(repository: CampaignOpsRepository) -> Milestone:
            before = self._require_milestone(repository, milestone_id)
            program = self._require_program(repository, before.program_id)
            assignments = repository.list_assignments_by_program(before.program_id)
            if not can_edit_milestone(actor, program, before, assignments):
                raise CampaignOpsPermissionError("You do not have permission to reopen this milestone.")
            if before.status != TaskStatus.COMPLETED.value:
                raise CampaignOpsValidationError("Only completed milestones can be reopened.")
            status = enum_value(TaskStatus, reopened_status, "reopened_status")
            if status in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value}:
                raise CampaignOpsValidationError("Reopened status must be active.")
            updated = repository.update_milestone(
                milestone_id,
                actor_user_id=actor.id if actor else None,
                title=before.title,
                workstream_id=before.workstream_id,
                milestone_type=before.milestone_type,
                target_date=before.target_date,
                start_date=before.start_date,
                end_date=before.end_date,
                status=status,
                owner_user_id=before.owner_user_id,
                hard_deadline=before.hard_deadline,
                completed_at=None,
            )
            repository.append_event(
                event_type="milestone_reopened",
                entity_type="milestone",
                entity_id=milestone_id,
                program_id=before.program_id,
                workstream_id=before.workstream_id,
                actor_user_id=actor.id if actor else None,
                old_value_json={"status": before.status, "completed_at": self._activity_value(before.completed_at)},
                new_value_json={"status": status, "completed_at": None},
                message=f"{actor.display_name if actor else 'System'} reopened milestone {before.title}.",
            )
            return updated

        return self._transaction(operation)

    def deactivate_milestone(self, actor: CampaignOpsUser | None, milestone_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            milestone = self._require_milestone(repository, milestone_id)
            program = self._require_program(repository, milestone.program_id)
            assignments = repository.list_assignments_by_program(milestone.program_id)
            if not can_manage_milestone_state(actor, program, milestone, assignments):
                raise CampaignOpsPermissionError("You do not have permission to deactivate this milestone.")
            repository.deactivate_milestone(milestone_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="milestone_deactivated",
                entity_type="milestone",
                entity_id=milestone_id,
                program_id=milestone.program_id,
                workstream_id=milestone.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated milestone {milestone.title}.",
            )

        self._transaction(operation)

    def reactivate_milestone(self, actor: CampaignOpsUser | None, milestone_id: str) -> Milestone:
        def operation(repository: CampaignOpsRepository) -> Milestone:
            milestone = self._require_milestone(repository, milestone_id)
            program = self._require_program(repository, milestone.program_id)
            assignments = repository.list_assignments_by_program(milestone.program_id)
            if not can_manage_milestone_state(actor, program, milestone, assignments):
                raise CampaignOpsPermissionError("You do not have permission to reactivate this milestone.")
            self._validate_task_workstream(repository, milestone.program_id, milestone.workstream_id)
            updated = repository.reactivate_milestone(milestone_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="milestone_reactivated",
                entity_type="milestone",
                entity_id=milestone_id,
                program_id=milestone.program_id,
                workstream_id=milestone.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated milestone {milestone.title}.",
            )
            return updated

        return self._transaction(operation)

    def list_program_milestones(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[MilestoneListRow]:
        repository = self.repository or CampaignOpsRepository()
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have permission to view program milestones.")
        return repository.list_milestone_rows_by_program(program_id, include_inactive=include_inactive)

    def _require_insights_project(
        self,
        repository: CampaignOpsRepository,
        project_id: str,
    ) -> InsightsProjectRecord:
        project = repository.get_insights_project(project_id)
        if project is None:
            raise CampaignOpsNotFoundError("Insights project was not found.")
        return project

    def _validate_insights_project_access(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        program_id: str,
    ) -> Program:
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this Insights program.")
        if not program.is_active:
            raise CampaignOpsValidationError("Archived programs cannot have Insights changes.")
        return program

    def _validate_insights_payload(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        payload: dict[str, Any],
        before: InsightsProjectRecord | None = None,
    ) -> dict[str, Any]:
        program_id = payload.get("program_id") or (before.program_id if before else None)
        if not program_id:
            raise CampaignOpsValidationError("Program is required.")
        self._validate_insights_project_access(repository, actor, str(program_id))
        project_title = require_text(payload.get("project_title") or (before.project_title if before else None), "Project title")
        workstream_id = payload.get("workstream_id") if "workstream_id" in payload else (before.workstream_id if before else None)
        if workstream_id:
            workstream = self._require_workstream(repository, str(program_id), str(workstream_id))
            if not workstream.is_active:
                raise CampaignOpsValidationError("Inactive workstreams cannot receive active Insights changes.")
        owner_user_id = payload.get("owner_user_id") if "owner_user_id" in payload else (before.owner_user_id if before else None)
        if owner_user_id:
            self._require_active_user(repository, str(owner_user_id), "Owner")
        total_program_cost = self._non_negative_number(payload.get("total_program_cost") if "total_program_cost" in payload else (before.total_program_cost if before else None), "Total program cost")
        budget = self._non_negative_number(payload.get("budget") if "budget" in payload else (before.budget if before else None), "Budget")
        sample_size = self._non_negative_int(payload.get("sample_size") if "sample_size" in payload else (before.sample_size if before else None), "Sample size")
        return {
            "program_id": str(program_id),
            "workstream_id": str(workstream_id) if workstream_id else None,
            "job_number": self._clean_optional_text(payload.get("job_number") if "job_number" in payload else (before.job_number if before else None)),
            "project_title": project_title,
            "insights_status": validate_insights_status(payload.get("insights_status") or (before.insights_status if before else INSIGHTS_STATUS_NOT_STARTED)),
            "latest_update": self._clean_optional_text(payload.get("latest_update") if "latest_update" in payload else (before.latest_update if before else None)),
            "total_program_cost": total_program_cost,
            "sample_size": sample_size,
            "budget": budget,
            "owner_user_id": str(owner_user_id) if owner_user_id else None,
        }

    def _non_negative_number(self, value: Any, field_name: str) -> float | None:
        if value in (None, ""):
            return None
        number = float(value)
        if number < 0:
            raise CampaignOpsValidationError(f"{field_name} must be non-negative.")
        return number

    def _non_negative_int(self, value: Any, field_name: str) -> int | None:
        if value in (None, ""):
            return None
        number = int(value)
        if number < 0:
            raise CampaignOpsValidationError(f"{field_name} must be non-negative.")
        return number

    def create_insights_project(
        self,
        actor: CampaignOpsUser | None,
        **kwargs: Any,
    ) -> InsightsProjectRecord:
        def operation(repository: CampaignOpsRepository) -> InsightsProjectRecord:
            payload = self._validate_insights_payload(repository, actor, kwargs)
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in INSIGHTS_RESOURCE_TYPES and url:
                    self._validate_resource_url(str(url))
            workstream_id = payload.get("workstream_id")
            if not workstream_id:
                workstreams = repository.list_all_workstreams_by_program(payload["program_id"])
                existing_insights = next((w for w in workstreams if w.workstream_type == WorkstreamType.INSIGHTS.value and w.is_active), None)
                if existing_insights:
                    workstream_id = existing_insights.id
                else:
                    workstream = repository.create_workstream(
                        payload["program_id"],
                        WorkstreamType.INSIGHTS.value,
                        actor_user_id=actor.id if actor else None,
                        owner_user_id=payload.get("owner_user_id"),
                    )
                    workstream_id = workstream.id
            payload["workstream_id"] = workstream_id
            project = repository.create_insights_project(actor_user_id=actor.id if actor else None, **payload)
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in INSIGHTS_RESOURCE_TYPES and url:
                    resource = repository.create_resource(
                        program_id=project.program_id,
                        workstream_id=project.workstream_id,
                        resource_type=resource_type,
                        title=resource_type,
                        url=self._validate_resource_url(url),
                        actor_user_id=actor.id if actor else None,
                    )
                    repository.append_event(
                        event_type="resource_created",
                        entity_type="resource",
                        entity_id=resource.id,
                        program_id=project.program_id,
                        workstream_id=project.workstream_id,
                        actor_user_id=actor.id if actor else None,
                        new_value_json={"title": resource.title, "resource_type": resource.resource_type, "url": resource.url},
                        message=f"{actor.display_name if actor else 'System'} added {resource.resource_type} for Insights project {project.project_title}.",
                    )
            for index, objective in enumerate(kwargs.get("initial_objectives") or []):
                if self._clean_optional_text(objective):
                    objective_record = repository.create_insights_objective(project.id, str(objective), actor_user_id=actor.id if actor else None, sort_order=index)
                    repository.append_event(
                        event_type="insights_objective_created",
                        entity_type="insights_objective",
                        entity_id=objective_record.id,
                        program_id=project.program_id,
                        workstream_id=project.workstream_id,
                        actor_user_id=actor.id if actor else None,
                        new_value_json={"objective_text": objective_record.objective_text, "sort_order": objective_record.sort_order},
                        message=f"{actor.display_name if actor else 'System'} added an Insights research objective.",
                    )
            repository.append_event(
                event_type="insights_project_created",
                entity_type="insights_project",
                entity_id=project.id,
                program_id=project.program_id,
                workstream_id=project.workstream_id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"project_title": project.project_title},
                message=f"{actor.display_name if actor else 'System'} created Insights project {project.project_title}.",
            )
            return project

        return self._transaction(operation)

    def update_insights_project(
        self,
        actor: CampaignOpsUser | None,
        project_id: str,
        **kwargs: Any,
    ) -> InsightsProjectRecord:
        def operation(repository: CampaignOpsRepository) -> InsightsProjectRecord:
            before = self._require_insights_project(repository, project_id)
            payload = self._validate_insights_payload(repository, actor, kwargs, before)
            changes = {field: value for field, value in payload.items() if field != "program_id" and getattr(before, field) != value}
            if not changes:
                return before
            merged = {
                "workstream_id": before.workstream_id,
                "job_number": before.job_number,
                "project_title": before.project_title,
                "insights_status": before.insights_status,
                "latest_update": before.latest_update,
                "total_program_cost": before.total_program_cost,
                "sample_size": before.sample_size,
                "budget": before.budget,
                "owner_user_id": before.owner_user_id,
            }
            merged.update(changes)
            updated = repository.update_insights_project(project_id, **merged)
            for field, value in changes.items():
                repository.append_event(
                    event_type=f"insights_project_{field}_changed",
                    entity_type="insights_project",
                    entity_id=project_id,
                    program_id=updated.program_id,
                    workstream_id=updated.workstream_id,
                    actor_user_id=actor.id if actor else None,
                    old_value_json={field: self._activity_value(getattr(before, field))},
                    new_value_json={field: self._activity_value(value)},
                    message=f"{actor.display_name if actor else 'System'} changed {field.replace('_', ' ')} from {getattr(before, field) or '-'} to {value or '-'}.",
                )
            return updated

        return self._transaction(operation)

    def list_insights_projects(
        self,
        actor: CampaignOpsUser | None,
        include_inactive: bool = False,
    ) -> list[InsightsPortfolioRow]:
        repository = self.repository or CampaignOpsRepository()
        rows = repository.list_insights_projects(include_inactive=include_inactive)
        if can_access_admin(actor):
            return rows
        visible: list[InsightsPortfolioRow] = []
        for row in rows:
            program = self._require_program(repository, row.program_id)
            assignments = repository.list_assignments_by_program(row.program_id)
            if can_view_program(actor, program, assignments):
                visible.append(row)
        return visible

    def get_insights_baseline_board_data(self, actor: CampaignOpsUser | None, projects: list[InsightsPortfolioRow]) -> dict[str, Any]:
        repository = self.repository or CampaignOpsRepository()
        visible_ids = [project.id for project in projects]
        return {
            "milestones": repository.list_insights_milestone_rows_for_projects(visible_ids),
        }

    def get_insights_project_detail(
        self,
        actor: CampaignOpsUser | None,
        project_id: str,
    ) -> InsightsProjectDetail:
        repository = self.repository or CampaignOpsRepository()
        detail = repository.get_insights_project_detail(project_id)
        if detail is None:
            raise CampaignOpsNotFoundError("Insights project was not found.")
        program = self._require_program(repository, detail.program_id)
        assignments = repository.list_assignments_by_program(detail.program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this Insights project.")
        return detail

    def deactivate_insights_project(self, actor: CampaignOpsUser | None, project_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            project = self._require_insights_project(repository, project_id)
            self._validate_insights_project_access(repository, actor, project.program_id)
            repository.deactivate_insights_project(project_id)
            repository.append_event(
                event_type="insights_project_deactivated",
                entity_type="insights_project",
                entity_id=project_id,
                program_id=project.program_id,
                workstream_id=project.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated Insights project {project.project_title}.",
            )

        self._transaction(operation)

    def reactivate_insights_project(self, actor: CampaignOpsUser | None, project_id: str) -> InsightsProjectRecord:
        def operation(repository: CampaignOpsRepository) -> InsightsProjectRecord:
            project = self._require_insights_project(repository, project_id)
            self._validate_insights_project_access(repository, actor, project.program_id)
            updated = repository.reactivate_insights_project(project_id)
            repository.append_event(
                event_type="insights_project_reactivated",
                entity_type="insights_project",
                entity_id=project_id,
                program_id=project.program_id,
                workstream_id=project.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated Insights project {project.project_title}.",
            )
            return updated

        return self._transaction(operation)

    def list_insights_objectives(
        self,
        actor: CampaignOpsUser | None,
        project_id: str,
        include_inactive: bool = False,
    ) -> list[InsightsObjectiveRecord]:
        detail = self.get_insights_project_detail(actor, project_id)
        repository = self.repository or CampaignOpsRepository()
        return repository.list_insights_objectives(detail.id, include_inactive=include_inactive)

    def add_insights_objective(
        self,
        actor: CampaignOpsUser | None,
        project_id: str,
        objective_text: str,
        sort_order: int = 0,
    ) -> InsightsObjectiveRecord:
        def operation(repository: CampaignOpsRepository) -> InsightsObjectiveRecord:
            project = self._require_insights_project(repository, project_id)
            self._validate_insights_project_access(repository, actor, project.program_id)
            objective = repository.create_insights_objective(project_id, objective_text, actor_user_id=actor.id if actor else None, sort_order=sort_order)
            repository.append_event(
                event_type="insights_objective_created",
                entity_type="insights_objective",
                entity_id=objective.id,
                program_id=project.program_id,
                workstream_id=project.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} added research objective {objective.objective_text}.",
            )
            return objective

        return self._transaction(operation)

    def update_insights_objective(
        self,
        actor: CampaignOpsUser | None,
        project_id: str,
        objective_id: str,
        objective_text: str,
        sort_order: int,
    ) -> InsightsObjectiveRecord:
        def operation(repository: CampaignOpsRepository) -> InsightsObjectiveRecord:
            project = self._require_insights_project(repository, project_id)
            self._validate_insights_project_access(repository, actor, project.program_id)
            before = next((item for item in repository.list_insights_objectives(project_id, include_inactive=True) if item.id == objective_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Insights objective was not found.")
            if before.objective_text == require_text(objective_text, "Objective") and before.sort_order == sort_order:
                return before
            updated = repository.update_insights_objective(objective_id, objective_text, sort_order)
            repository.append_event(
                event_type="insights_objective_updated",
                entity_type="insights_objective",
                entity_id=objective_id,
                program_id=project.program_id,
                workstream_id=project.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} updated research objective {updated.objective_text}.",
            )
            return updated

        return self._transaction(operation)

    def reorder_insights_objectives(
        self,
        actor: CampaignOpsUser | None,
        project_id: str,
        ordered_ids: list[str],
    ) -> list[InsightsObjectiveRecord]:
        updated: list[InsightsObjectiveRecord] = []
        for index, objective_id in enumerate(ordered_ids):
            objective = next((item for item in self.list_insights_objectives(actor, project_id, include_inactive=True) if item.id == objective_id), None)
            if objective:
                updated.append(self.update_insights_objective(actor, project_id, objective.id, objective.objective_text, index))
        return updated

    def deactivate_insights_objective(self, actor: CampaignOpsUser | None, project_id: str, objective_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            project = self._require_insights_project(repository, project_id)
            self._validate_insights_project_access(repository, actor, project.program_id)
            repository.deactivate_insights_objective(objective_id)
            repository.append_event(
                event_type="insights_objective_deactivated",
                entity_type="insights_objective",
                entity_id=objective_id,
                program_id=project.program_id,
                workstream_id=project.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated a research objective.",
            )

        self._transaction(operation)

    def reactivate_insights_objective(self, actor: CampaignOpsUser | None, project_id: str, objective_id: str) -> InsightsObjectiveRecord:
        def operation(repository: CampaignOpsRepository) -> InsightsObjectiveRecord:
            project = self._require_insights_project(repository, project_id)
            self._validate_insights_project_access(repository, actor, project.program_id)
            objective = repository.reactivate_insights_objective(objective_id)
            repository.append_event(
                event_type="insights_objective_reactivated",
                entity_type="insights_objective",
                entity_id=objective_id,
                program_id=project.program_id,
                workstream_id=project.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated research objective {objective.objective_text}.",
            )
            return objective

        return self._transaction(operation)

    def _retail_media_actor_label(self, actor: CampaignOpsUser | None) -> str:
        return actor.display_name if actor else "System"

    def _validate_retail_media_access(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        program_id: str,
    ) -> Program:
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this Retail Media program.")
        if not program.is_active:
            raise CampaignOpsValidationError("Archived programs cannot have Retail Media changes.")
        return program

    def _require_retail_media_campaign(
        self,
        repository: CampaignOpsRepository,
        campaign_id: str,
    ) -> RetailMediaCampaignRecord:
        campaign = repository.get_retail_media_campaign(campaign_id)
        if campaign is None:
            raise CampaignOpsNotFoundError("Retail Media campaign was not found.")
        return campaign

    def _validate_retail_media_campaign_payload(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        payload: dict[str, Any],
        before: RetailMediaCampaignRecord | None = None,
    ) -> dict[str, Any]:
        program_id = payload.get("program_id") or (before.program_id if before else None)
        if not program_id:
            raise CampaignOpsValidationError("Program is required.")
        self._validate_retail_media_access(repository, actor, str(program_id))
        title = require_text(payload.get("campaign_title") or (before.campaign_title if before else None), "Retail Media campaign title")
        workstream_id = payload.get("workstream_id") if "workstream_id" in payload else (before.workstream_id if before else None)
        if workstream_id:
            workstream = self._require_workstream(repository, str(program_id), str(workstream_id))
            if not workstream.is_active:
                raise CampaignOpsValidationError("Inactive workstreams cannot receive active Retail Media changes.")
        owner_user_id = payload.get("owner_user_id") if "owner_user_id" in payload else (before.owner_user_id if before else None)
        if owner_user_id:
            self._require_active_user(repository, str(owner_user_id), "Owner")
        launch_date = payload.get("launch_date") if "launch_date" in payload else (before.launch_date if before else None)
        wrap_date = payload.get("wrap_date") if "wrap_date" in payload else (before.wrap_date if before else None)
        if launch_date and wrap_date and wrap_date < launch_date:
            raise CampaignOpsValidationError("Wrap date cannot precede launch date.")
        overall_budget = self._non_negative_number(payload.get("overall_budget") if "overall_budget" in payload else (before.overall_budget if before else None), "Overall budget")
        total_spend = self._non_negative_number(payload.get("total_spend") if "total_spend" in payload else (before.total_spend if before else None), "Total spend")
        is_paused = bool(payload.get("is_paused") if "is_paused" in payload else (before.is_paused if before else False))
        pause_reason = self._clean_optional_text(payload.get("pause_reason") if "pause_reason" in payload else (before.pause_reason if before else None))
        if is_paused and not pause_reason:
            raise CampaignOpsValidationError("Pause reason is required when a Retail Media campaign is paused.")
        return {
            "program_id": str(program_id),
            "workstream_id": str(workstream_id) if workstream_id else None,
            "campaign_title": title,
            "retail_media_status": normalize_retail_media_status(payload.get("retail_media_status") or (before.retail_media_status if before else RETAIL_MEDIA_STATUS_NOT_STARTED)),
            "latest_update": self._clean_optional_text(payload.get("latest_update") if "latest_update" in payload else (before.latest_update if before else None)),
            "waiting_on": self._clean_optional_text(payload.get("waiting_on") if "waiting_on" in payload else (before.waiting_on if before else None)),
            "owner_user_id": str(owner_user_id) if owner_user_id else None,
            "launch_date": launch_date,
            "wrap_date": wrap_date,
            "reporting_cadence": self._clean_optional_text(payload.get("reporting_cadence") if "reporting_cadence" in payload else (before.reporting_cadence if before else None)),
            "overall_budget": overall_budget,
            "total_spend": total_spend,
            "is_paused": is_paused,
            "pause_reason": pause_reason,
        }

    def create_retail_media_campaign(self, actor: CampaignOpsUser | None, **kwargs: Any) -> RetailMediaCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaCampaignRecord:
            payload = self._validate_retail_media_campaign_payload(repository, actor, kwargs)
            duplicate = repository.get_active_retail_media_campaign_by_title(payload["program_id"], payload["campaign_title"])
            if duplicate:
                raise CampaignOpsValidationError("An active Retail Media campaign with this title already exists for this program.")
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in RETAIL_MEDIA_RESOURCE_TYPES and url:
                    self._validate_resource_url(str(url))
            workstream_id = payload.get("workstream_id")
            if not workstream_id:
                existing = next((w for w in repository.list_all_workstreams_by_program(payload["program_id"]) if w.workstream_type == WorkstreamType.RETAIL_MEDIA.value and w.is_active), None)
                if existing:
                    workstream_id = existing.id
                else:
                    workstream = repository.create_workstream(
                        payload["program_id"],
                        WorkstreamType.RETAIL_MEDIA.value,
                        actor_user_id=actor.id if actor else None,
                        owner_user_id=payload.get("owner_user_id"),
                    )
                    workstream_id = workstream.id
            payload["workstream_id"] = workstream_id
            campaign = repository.create_retail_media_campaign(actor_user_id=actor.id if actor else None, **payload)
            seen_channels: set[str] = set()
            for channel in kwargs.get("initial_channels") or []:
                channel_type = require_text(str(channel.get("channel_type") if isinstance(channel, dict) else channel), "Channel type")
                normalized = channel_type.strip().lower()
                if normalized in seen_channels:
                    raise CampaignOpsValidationError("Duplicate active Retail Media channels are not allowed.")
                seen_channels.add(normalized)
                channel_payload = dict(channel) if isinstance(channel, dict) else {}
                channel_payload["channel_type"] = channel_type
                self._create_retail_media_channel(repository, actor, campaign, **channel_payload)
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in RETAIL_MEDIA_RESOURCE_TYPES:
                    resource = repository.create_resource(
                        program_id=campaign.program_id,
                        workstream_id=campaign.workstream_id,
                        resource_type=resource_type,
                        title=resource_type,
                        url=self._validate_resource_url(url) if url else None,
                        actor_user_id=actor.id if actor else None,
                    )
                    repository.append_event(
                        event_type="resource_created",
                        entity_type="resource",
                        entity_id=resource.id,
                        program_id=campaign.program_id,
                        workstream_id=campaign.workstream_id,
                        actor_user_id=actor.id if actor else None,
                        message=f"{self._retail_media_actor_label(actor)} added {resource.resource_type} for Retail Media campaign {campaign.campaign_title}.",
                    )
            repository.append_event(
                event_type="retail_media_campaign_created",
                entity_type="retail_media_campaign",
                entity_id=campaign.id,
                program_id=campaign.program_id,
                workstream_id=campaign.workstream_id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"campaign_title": campaign.campaign_title},
                message=f"{self._retail_media_actor_label(actor)} created Retail Media campaign {campaign.campaign_title}.",
            )
            return campaign

        return self._transaction(operation)

    def update_retail_media_campaign(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> RetailMediaCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaCampaignRecord:
            before = self._require_retail_media_campaign(repository, campaign_id)
            payload = self._validate_retail_media_campaign_payload(repository, actor, kwargs, before)
            duplicate = repository.get_active_retail_media_campaign_by_title(payload["program_id"], payload["campaign_title"])
            if duplicate and duplicate.id != campaign_id:
                raise CampaignOpsValidationError("An active Retail Media campaign with this title already exists for this program.")
            editable = {k: getattr(before, k) for k in payload if k != "program_id"}
            changes = {field: value for field, value in payload.items() if field != "program_id" and editable[field] != value}
            if not changes:
                return before
            merged = dict(editable)
            merged.update(changes)
            updated = repository.update_retail_media_campaign(campaign_id, **merged)
            for field, value in changes.items():
                repository.append_event(
                    event_type=f"retail_media_campaign_{field}_changed",
                    entity_type="retail_media_campaign",
                    entity_id=campaign_id,
                    program_id=updated.program_id,
                    workstream_id=updated.workstream_id,
                    actor_user_id=actor.id if actor else None,
                    old_value_json={field: self._activity_value(getattr(before, field))},
                    new_value_json={field: self._activity_value(value)},
                    message=f"{self._retail_media_actor_label(actor)} changed Retail Media {field.replace('_', ' ')} from {getattr(before, field) or '-'} to {value or '-'}.",
                )
            return updated

        return self._transaction(operation)

    def list_retail_media_campaigns(self, actor: CampaignOpsUser | None, include_inactive: bool = False) -> list[RetailMediaPortfolioRow]:
        repository = self.repository or CampaignOpsRepository()
        rows = repository.list_retail_media_campaigns(include_inactive=include_inactive)
        if can_access_admin(actor):
            return rows
        visible: list[RetailMediaPortfolioRow] = []
        for row in rows:
            program = self._require_program(repository, row.program_id)
            assignments = repository.list_assignments_by_program(row.program_id)
            if can_view_program(actor, program, assignments):
                visible.append(row)
        return visible

    def get_retail_media_baseline_board_data(self, actor: CampaignOpsUser | None, campaigns: list[RetailMediaPortfolioRow]) -> dict[str, Any]:
        repository = self.repository or CampaignOpsRepository()
        visible = {campaign.id: campaign for campaign in campaigns}
        campaign_ids = list(visible)
        program_ids = list({campaign.program_id for campaign in campaigns})
        resources_by_program = repository.list_resources_for_programs(program_ids)
        return {
            "channels": repository.list_retail_media_channels_for_campaigns(campaign_ids),
            "activations": repository.list_retail_media_activations_for_campaigns(campaign_ids),
            "creative": repository.list_retail_media_creative_for_campaigns(campaign_ids),
            "optimizations": repository.list_retail_media_optimizations_for_campaigns(campaign_ids),
            "milestones": repository.list_retail_media_milestone_rows_for_campaigns(campaign_ids),
            "resources": {
                campaign_id: resources_by_program.get(campaign.program_id, [])
                for campaign_id, campaign in visible.items()
            },
        }

    def get_retail_media_campaign_detail(self, actor: CampaignOpsUser | None, campaign_id: str) -> RetailMediaCampaignDetail:
        repository = self.repository or CampaignOpsRepository()
        detail = repository.get_retail_media_campaign_detail(campaign_id)
        if detail is None:
            raise CampaignOpsNotFoundError("Retail Media campaign was not found.")
        program = self._require_program(repository, detail.program_id)
        if not can_view_program(actor, program, repository.list_assignments_by_program(detail.program_id)):
            raise CampaignOpsPermissionError("You do not have access to this Retail Media campaign.")
        return detail

    def deactivate_retail_media_campaign(self, actor: CampaignOpsUser | None, campaign_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            repository.deactivate_retail_media_campaign(campaign_id)
            repository.append_event(event_type="retail_media_campaign_deactivated", entity_type="retail_media_campaign", entity_id=campaign_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} deactivated Retail Media campaign {campaign.campaign_title}.")

        self._transaction(operation)

    def reactivate_retail_media_campaign(self, actor: CampaignOpsUser | None, campaign_id: str) -> RetailMediaCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaCampaignRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            updated = repository.reactivate_retail_media_campaign(campaign_id)
            repository.append_event(event_type="retail_media_campaign_reactivated", entity_type="retail_media_campaign", entity_id=campaign_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} reactivated Retail Media campaign {campaign.campaign_title}.")
            return updated

        return self._transaction(operation)

    def _validate_retail_media_child_dates(self, start: Any, end: Any, start_label: str = "Start date", end_label: str = "End date") -> None:
        if start and end and end < start:
            raise CampaignOpsValidationError(f"{end_label} cannot precede {start_label.lower()}.")

    def _channel_payload(self, repository: CampaignOpsRepository, campaign: RetailMediaCampaignRecord, payload: dict[str, Any], before: RetailMediaChannelRecord | None = None) -> dict[str, Any]:
        channel_type = require_text(payload.get("channel_type") or (before.channel_type if before else None), "Channel type")
        launch = payload.get("launch_date") if "launch_date" in payload else (before.launch_date if before else None)
        end = payload.get("end_date") if "end_date" in payload else (before.end_date if before else None)
        self._validate_retail_media_child_dates(launch, end, "Launch date", "End date")
        return {
            "channel_type": channel_type,
            "platform_name": self._clean_optional_text(payload.get("platform_name") if "platform_name" in payload else (before.platform_name if before else None)),
            "status": self._clean_optional_text(payload.get("status") if "status" in payload else (before.status if before else None)),
            "budget": self._non_negative_number(payload.get("budget") if "budget" in payload else (before.budget if before else None), "Channel budget"),
            "spend_to_date": self._non_negative_number(payload.get("spend_to_date") if "spend_to_date" in payload else (before.spend_to_date if before else None), "Channel spend"),
            "launch_date": launch,
            "end_date": end,
            "reporting_requirement": self._clean_optional_text(payload.get("reporting_requirement") if "reporting_requirement" in payload else (before.reporting_requirement if before else None)),
        }

    def _create_retail_media_channel(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, campaign: RetailMediaCampaignRecord, **kwargs: Any) -> RetailMediaChannelRecord:
        payload = self._channel_payload(repository, campaign, kwargs)
        if any(c.channel_type.lower() == payload["channel_type"].lower() for c in repository.list_retail_media_channels(campaign.id)):
            raise CampaignOpsValidationError("Duplicate active Retail Media channels are not allowed.")
        channel = repository.create_retail_media_channel(campaign.id, **payload)
        repository.append_event(event_type="retail_media_channel_created", entity_type="retail_media_channel", entity_id=channel.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} added Retail Media channel {channel.channel_type}.")
        return channel

    def create_retail_media_channel(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> RetailMediaChannelRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaChannelRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            return self._create_retail_media_channel(repository, actor, campaign, **kwargs)

        return self._transaction(operation)

    def list_retail_media_channels(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[RetailMediaChannelRecord]:
        campaign = self.get_retail_media_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_retail_media_channels(campaign.id, include_inactive=include_inactive)

    def update_retail_media_channel(self, actor: CampaignOpsUser | None, campaign_id: str, channel_id: str, **kwargs: Any) -> RetailMediaChannelRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaChannelRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            before = next((c for c in repository.list_retail_media_channels(campaign_id, include_inactive=True) if c.id == channel_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Retail Media channel was not found.")
            payload = self._channel_payload(repository, campaign, kwargs, before)
            if any(c.id != channel_id and c.channel_type.lower() == payload["channel_type"].lower() for c in repository.list_retail_media_channels(campaign_id)):
                raise CampaignOpsValidationError("Duplicate active Retail Media channels are not allowed.")
            changes = {field: value for field, value in payload.items() if getattr(before, field) != value}
            if not changes:
                return before
            updated = repository.update_retail_media_channel(channel_id, **{**{k: getattr(before, k) for k in payload}, **changes})
            repository.append_event(event_type="retail_media_channel_updated", entity_type="retail_media_channel", entity_id=channel_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} updated Retail Media channel {updated.channel_type}.")
            return updated

        return self._transaction(operation)

    def deactivate_retail_media_channel(self, actor: CampaignOpsUser | None, campaign_id: str, channel_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            repository.deactivate_retail_media_channel(channel_id)
            repository.append_event(event_type="retail_media_channel_deactivated", entity_type="retail_media_channel", entity_id=channel_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} deactivated a Retail Media channel.")

        self._transaction(operation)

    def reactivate_retail_media_channel(self, actor: CampaignOpsUser | None, campaign_id: str, channel_id: str) -> RetailMediaChannelRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaChannelRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            channel = repository.reactivate_retail_media_channel(channel_id)
            repository.append_event(event_type="retail_media_channel_reactivated", entity_type="retail_media_channel", entity_id=channel_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} reactivated Retail Media channel {channel.channel_type}.")
            return channel

        return self._transaction(operation)

    def _validate_retail_media_channel_link(
        self,
        repository: CampaignOpsRepository,
        campaign_id: str,
        channel_id: str | None,
    ) -> None:
        if not channel_id:
            return
        if not any(channel.id == channel_id for channel in repository.list_retail_media_channels(campaign_id, include_inactive=True)):
            raise CampaignOpsValidationError("Selected channel must belong to the Retail Media campaign.")

    def _activation_payload(self, repository: CampaignOpsRepository, campaign: RetailMediaCampaignRecord, payload: dict[str, Any], before: RetailMediaActivationRecord | None = None) -> dict[str, Any]:
        channel_id = payload.get("channel_id") if "channel_id" in payload else (before.channel_id if before else None)
        self._validate_retail_media_channel_link(repository, campaign.id, str(channel_id) if channel_id else None)
        start = payload.get("start_date") if "start_date" in payload else (before.start_date if before else None)
        end = payload.get("end_date") if "end_date" in payload else (before.end_date if before else None)
        self._validate_retail_media_child_dates(start, end)
        return {
            "channel_id": str(channel_id) if channel_id else None,
            "activation_name": require_text(payload.get("activation_name") or (before.activation_name if before else None), "Activation name"),
            "activation_type": self._clean_optional_text(payload.get("activation_type") if "activation_type" in payload else (before.activation_type if before else None)),
            "status": self._clean_optional_text(payload.get("status") if "status" in payload else (before.status if before else None)),
            "start_date": start,
            "end_date": end,
            "hard_deadline": bool(payload.get("hard_deadline") if "hard_deadline" in payload else (before.hard_deadline if before else False)),
            "waiting_on": self._clean_optional_text(payload.get("waiting_on") if "waiting_on" in payload else (before.waiting_on if before else None)),
            "latest_update": self._clean_optional_text(payload.get("latest_update") if "latest_update" in payload else (before.latest_update if before else None)),
            "completed_at": payload.get("completed_at") if "completed_at" in payload else (before.completed_at if before else None),
        }

    def create_retail_media_activation(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> RetailMediaActivationRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaActivationRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            payload = self._activation_payload(repository, campaign, kwargs)
            activation = repository.create_retail_media_activation(campaign_id, **payload)
            repository.append_event(event_type="retail_media_activation_created", entity_type="retail_media_activation", entity_id=activation.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} added Retail Media activation {activation.activation_name}.")
            return activation

        return self._transaction(operation)

    def list_retail_media_activations(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[RetailMediaActivationRecord]:
        campaign = self.get_retail_media_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_retail_media_activations(campaign.id, include_inactive=include_inactive)

    def update_retail_media_activation(self, actor: CampaignOpsUser | None, campaign_id: str, activation_id: str, **kwargs: Any) -> RetailMediaActivationRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaActivationRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            before = next((item for item in repository.list_retail_media_activations(campaign_id, include_inactive=True) if item.id == activation_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Retail Media activation was not found.")
            payload = self._activation_payload(repository, campaign, kwargs, before)
            changes = {field: value for field, value in payload.items() if getattr(before, field) != value}
            if not changes:
                return before
            updated = repository.update_retail_media_activation(activation_id, **{**{k: getattr(before, k) for k in payload}, **changes})
            repository.append_event(event_type="retail_media_activation_updated", entity_type="retail_media_activation", entity_id=activation_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} updated Retail Media activation {updated.activation_name}.")
            return updated

        return self._transaction(operation)

    def complete_retail_media_activation(self, actor: CampaignOpsUser | None, campaign_id: str, activation_id: str) -> RetailMediaActivationRecord:
        return self.update_retail_media_activation(actor, campaign_id, activation_id, status=RETAIL_MEDIA_STATUS_COMPLETE, completed_at=datetime.now(UTC))

    def reopen_retail_media_activation(self, actor: CampaignOpsUser | None, campaign_id: str, activation_id: str) -> RetailMediaActivationRecord:
        return self.update_retail_media_activation(actor, campaign_id, activation_id, status="in_progress", completed_at=None)

    def deactivate_retail_media_activation(self, actor: CampaignOpsUser | None, campaign_id: str, activation_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            repository.deactivate_retail_media_activation(activation_id)
            repository.append_event(event_type="retail_media_activation_deactivated", entity_type="retail_media_activation", entity_id=activation_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} deactivated a Retail Media activation.")

        self._transaction(operation)

    def reactivate_retail_media_activation(self, actor: CampaignOpsUser | None, campaign_id: str, activation_id: str) -> RetailMediaActivationRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaActivationRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            activation = repository.reactivate_retail_media_activation(activation_id)
            repository.append_event(event_type="retail_media_activation_reactivated", entity_type="retail_media_activation", entity_id=activation_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} reactivated Retail Media activation {activation.activation_name}.")
            return activation

        return self._transaction(operation)

    def _creative_payload(self, repository: CampaignOpsRepository, campaign: RetailMediaCampaignRecord, payload: dict[str, Any], before: RetailMediaCreativeRecord | None = None) -> dict[str, Any]:
        channel_id = payload.get("channel_id") if "channel_id" in payload else (before.channel_id if before else None)
        self._validate_retail_media_channel_link(repository, campaign.id, str(channel_id) if channel_id else None)
        return {
            "channel_id": str(channel_id) if channel_id else None,
            "creative_name": require_text(payload.get("creative_name") or (before.creative_name if before else None), "Creative name"),
            "creative_type": self._clean_optional_text(payload.get("creative_type") if "creative_type" in payload else (before.creative_type if before else None)),
            "approval_status": normalize_approval_status(payload.get("approval_status") if "approval_status" in payload else (before.approval_status if before else None)),
            "submission_status": normalize_submission_status(payload.get("submission_status") if "submission_status" in payload else (before.submission_status if before else None)),
            "platform_status": self._clean_optional_text(payload.get("platform_status") if "platform_status" in payload else (before.platform_status if before else None)),
            "due_date": payload.get("due_date") if "due_date" in payload else (before.due_date if before else None),
            "submitted_date": payload.get("submitted_date") if "submitted_date" in payload else (before.submitted_date if before else None),
            "approved_date": payload.get("approved_date") if "approved_date" in payload else (before.approved_date if before else None),
            "notes": self._clean_optional_text(payload.get("notes") if "notes" in payload else (before.notes if before else None)),
        }

    def create_retail_media_creative(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> RetailMediaCreativeRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaCreativeRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            creative = repository.create_retail_media_creative(campaign_id, **self._creative_payload(repository, campaign, kwargs))
            repository.append_event(event_type="retail_media_creative_created", entity_type="retail_media_creative", entity_id=creative.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} added Retail Media creative {creative.creative_name}.")
            return creative

        return self._transaction(operation)

    def list_retail_media_creative(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[RetailMediaCreativeRecord]:
        campaign = self.get_retail_media_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_retail_media_creative(campaign.id, include_inactive=include_inactive)

    def update_retail_media_creative(self, actor: CampaignOpsUser | None, campaign_id: str, creative_id: str, **kwargs: Any) -> RetailMediaCreativeRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaCreativeRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            before = next((item for item in repository.list_retail_media_creative(campaign_id, include_inactive=True) if item.id == creative_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Retail Media creative item was not found.")
            payload = self._creative_payload(repository, campaign, kwargs, before)
            changes = {field: value for field, value in payload.items() if getattr(before, field) != value}
            if not changes:
                return before
            updated = repository.update_retail_media_creative(creative_id, **{**{k: getattr(before, k) for k in payload}, **changes})
            repository.append_event(event_type="retail_media_creative_updated", entity_type="retail_media_creative", entity_id=creative_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} updated Retail Media creative {updated.creative_name}.")
            return updated

        return self._transaction(operation)

    def mark_retail_media_creative_submitted(self, actor: CampaignOpsUser | None, campaign_id: str, creative_id: str, submitted_date: date | None = None) -> RetailMediaCreativeRecord:
        return self.update_retail_media_creative(actor, campaign_id, creative_id, submission_status="submitted", submitted_date=submitted_date or date.today())

    def mark_retail_media_creative_approved(self, actor: CampaignOpsUser | None, campaign_id: str, creative_id: str, approved_date: date | None = None) -> RetailMediaCreativeRecord:
        return self.update_retail_media_creative(actor, campaign_id, creative_id, approval_status="approved", approved_date=approved_date or date.today())

    def deactivate_retail_media_creative(self, actor: CampaignOpsUser | None, campaign_id: str, creative_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            repository.deactivate_retail_media_creative(creative_id)
            repository.append_event(event_type="retail_media_creative_deactivated", entity_type="retail_media_creative", entity_id=creative_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} deactivated a Retail Media creative item.")

        self._transaction(operation)

    def reactivate_retail_media_creative(self, actor: CampaignOpsUser | None, campaign_id: str, creative_id: str) -> RetailMediaCreativeRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaCreativeRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            creative = repository.reactivate_retail_media_creative(creative_id)
            repository.append_event(event_type="retail_media_creative_reactivated", entity_type="retail_media_creative", entity_id=creative_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} reactivated Retail Media creative {creative.creative_name}.")
            return creative

        return self._transaction(operation)

    def create_retail_media_optimization(self, actor: CampaignOpsUser | None, campaign_id: str, update_date: date, update_text: str, **kwargs: Any) -> RetailMediaOptimizationRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaOptimizationRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            channel_id = kwargs.get("channel_id")
            self._validate_retail_media_channel_link(repository, campaign_id, str(channel_id) if channel_id else None)
            optimization = repository.create_retail_media_optimization(campaign_id, update_date, update_text, actor_user_id=actor.id if actor else None, channel_id=channel_id, optimization_type=self._clean_optional_text(kwargs.get("optimization_type")))
            repository.append_event(event_type="retail_media_optimization_created", entity_type="retail_media_optimization", entity_id=optimization.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} added optimization update {optimization.update_text}.")
            return optimization

        return self._transaction(operation)

    def list_retail_media_optimizations(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[RetailMediaOptimizationRecord]:
        campaign = self.get_retail_media_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_retail_media_optimizations(campaign.id, include_inactive=include_inactive)

    def update_retail_media_optimization(self, actor: CampaignOpsUser | None, campaign_id: str, optimization_id: str, **kwargs: Any) -> RetailMediaOptimizationRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaOptimizationRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            before = next((item for item in repository.list_retail_media_optimizations(campaign_id, include_inactive=True) if item.id == optimization_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Retail Media optimization update was not found.")
            channel_id = kwargs.get("channel_id") if "channel_id" in kwargs else before.channel_id
            self._validate_retail_media_channel_link(repository, campaign_id, str(channel_id) if channel_id else None)
            payload = {
                "channel_id": str(channel_id) if channel_id else None,
                "update_date": kwargs.get("update_date") if "update_date" in kwargs else before.update_date,
                "update_text": require_text(kwargs.get("update_text") or before.update_text, "Optimization update"),
                "optimization_type": self._clean_optional_text(kwargs.get("optimization_type") if "optimization_type" in kwargs else before.optimization_type),
            }
            changes = {field: value for field, value in payload.items() if getattr(before, field) != value}
            if not changes:
                return before
            updated = repository.update_retail_media_optimization(optimization_id, **payload)
            repository.append_event(event_type="retail_media_optimization_updated", entity_type="retail_media_optimization", entity_id=optimization_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} updated optimization update {updated.update_text}.")
            return updated

        return self._transaction(operation)

    def deactivate_retail_media_optimization(self, actor: CampaignOpsUser | None, campaign_id: str, optimization_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            repository.deactivate_retail_media_optimization(optimization_id)
            repository.append_event(event_type="retail_media_optimization_deactivated", entity_type="retail_media_optimization", entity_id=optimization_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} deactivated a Retail Media optimization update.")

        self._transaction(operation)

    def reactivate_retail_media_optimization(self, actor: CampaignOpsUser | None, campaign_id: str, optimization_id: str) -> RetailMediaOptimizationRecord:
        def operation(repository: CampaignOpsRepository) -> RetailMediaOptimizationRecord:
            campaign = self._require_retail_media_campaign(repository, campaign_id)
            self._validate_retail_media_access(repository, actor, campaign.program_id)
            optimization = repository.reactivate_retail_media_optimization(optimization_id)
            repository.append_event(event_type="retail_media_optimization_reactivated", entity_type="retail_media_optimization", entity_id=optimization_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._retail_media_actor_label(actor)} reactivated Retail Media optimization update {optimization.update_text}.")
            return optimization

        return self._transaction(operation)

    def retail_media_budget_summary(self, campaign: RetailMediaCampaignDetail, channels: list[RetailMediaChannelRecord]) -> dict[str, float | bool | None]:
        budget = campaign.overall_budget
        spend = campaign.total_spend if campaign.total_spend is not None else sum(channel.spend_to_date or 0 for channel in channels)
        remaining = None if budget is None else budget - (spend or 0)
        percentage = None if not budget else ((spend or 0) / budget) * 100
        return {
            "budget": budget,
            "spend": spend,
            "remaining": remaining,
            "spend_percentage": percentage,
            "over_budget": bool(budget is not None and (spend or 0) > budget),
            "channel_budget_total": sum(channel.budget or 0 for channel in channels),
            "channel_spend_total": sum(channel.spend_to_date or 0 for channel in channels),
        }

    def _influencer_actor_label(self, actor: CampaignOpsUser | None) -> str:
        return actor.display_name if actor else "System"

    def _require_influencer_campaign(self, repository: CampaignOpsRepository, campaign_id: str) -> InfluencerCampaignRecord:
        campaign = repository.get_influencer_campaign(campaign_id)
        if campaign is None:
            raise CampaignOpsNotFoundError("Influencer campaign was not found.")
        return campaign

    def _validate_influencer_access(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, program_id: str) -> Program:
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this Influencer campaign.")
        if not program.is_active:
            raise CampaignOpsValidationError("Archived programs cannot have Influencer Planning changes.")
        return program

    def _non_negative_int(self, value: Any, label: str) -> int | None:
        if value in (None, ""):
            return None
        number = int(value)
        if number < 0:
            raise CampaignOpsValidationError(f"{label} must be non-negative.")
        return number

    def _non_negative_float(self, value: Any, label: str) -> float | None:
        if value in (None, ""):
            return None
        number = float(value)
        if number < 0:
            raise CampaignOpsValidationError(f"{label} must be non-negative.")
        return number

    def _validate_influencer_campaign_payload(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, payload: dict[str, Any], before: InfluencerCampaignRecord | None = None) -> dict[str, Any]:
        program_id = payload.get("program_id") or (before.program_id if before else None)
        if not program_id:
            raise CampaignOpsValidationError("Program is required.")
        self._validate_influencer_access(repository, actor, str(program_id))
        title = require_text(payload.get("campaign_title") or (before.campaign_title if before else None), "Influencer Campaign title")
        workstream_id = payload.get("workstream_id") if "workstream_id" in payload else (before.workstream_id if before else None)
        if workstream_id:
            workstream = self._require_workstream(repository, str(program_id), str(workstream_id))
            if workstream.workstream_type != WorkstreamType.INFLUENCER.value:
                raise CampaignOpsValidationError("Selected workstream must be an Influencer workstream.")
            if not workstream.is_active:
                raise CampaignOpsValidationError("Inactive workstreams cannot receive active Influencer Planning changes.")
        manager_user_id = payload.get("manager_user_id") if "manager_user_id" in payload else (before.manager_user_id if before else None)
        if manager_user_id:
            self._require_active_user(repository, str(manager_user_id), "Manager")
        launch = payload.get("launch_date") if "launch_date" in payload else (before.launch_date if before else None)
        wrap = payload.get("wrap_date") if "wrap_date" in payload else (before.wrap_date if before else None)
        if launch and wrap and wrap < launch:
            raise CampaignOpsValidationError("Wrap date cannot precede launch date.")
        is_on_hold = bool(payload.get("is_on_hold") if "is_on_hold" in payload else (before.is_on_hold if before else False))
        hold_reason = self._clean_optional_text(payload.get("hold_reason") if "hold_reason" in payload else (before.hold_reason if before else None))
        if is_on_hold and not hold_reason:
            raise CampaignOpsValidationError("Hold reason is required when an Influencer campaign is On Hold.")
        invoice_amount = self._non_negative_float(payload.get("invoice_amount") if "invoice_amount" in payload else (before.invoice_amount if before else None), "Invoice amount")
        target = self._non_negative_int(payload.get("target_creator_count") if "target_creator_count" in payload else (before.target_creator_count if before else None), "Target creator count")
        approved = self._non_negative_int(payload.get("approved_creator_count") if "approved_creator_count" in payload else (before.approved_creator_count if before else None), "Approved creator count")
        contracted = self._non_negative_int(payload.get("contracted_creator_count") if "contracted_creator_count" in payload else (before.contracted_creator_count if before else None), "Contracted creator count")
        stage = normalize_influencer_stage(payload.get("influencer_stage") if "influencer_stage" in payload else (before.influencer_stage if before else INFLUENCER_STAGE_PLANNING))
        status_value = payload.get("planning_status") if "planning_status" in payload else (before.planning_status if before else None)
        if stage == INFLUENCER_STAGE_LIVE:
            status = normalize_live_status(status_value)
        elif stage == INFLUENCER_STAGE_RECAPPING:
            status = normalize_recap_status(status_value)
        elif stage == INFLUENCER_STAGE_COMPLETE:
            status = RECAP_STATUS_COMPLETE
        else:
            status = normalize_planning_status(status_value)
        return {
            "program_id": str(program_id),
            "workstream_id": str(workstream_id) if workstream_id else None,
            "campaign_title": title,
            "manager_user_id": str(manager_user_id) if manager_user_id else None,
            "influencer_stage": stage,
            "planning_status": status,
            "latest_update": self._clean_optional_text(payload.get("latest_update") if "latest_update" in payload else (before.latest_update if before else None)),
            "waiting_on": self._clean_optional_text(payload.get("waiting_on") if "waiting_on" in payload else (before.waiting_on if before else None)),
            "is_on_hold": is_on_hold,
            "hold_reason": hold_reason,
            "application_open_date": payload.get("application_open_date") if "application_open_date" in payload else (before.application_open_date if before else None),
            "application_close_date": payload.get("application_close_date") if "application_close_date" in payload else (before.application_close_date if before else None),
            "influencer_approval_due_date": payload.get("influencer_approval_due_date") if "influencer_approval_due_date" in payload else (before.influencer_approval_due_date if before else None),
            "scripts_due_date": payload.get("scripts_due_date") if "scripts_due_date" in payload else (before.scripts_due_date if before else None),
            "first_content_due_date": payload.get("first_content_due_date") if "first_content_due_date" in payload else (before.first_content_due_date if before else None),
            "launch_date": launch,
            "wrap_date": wrap,
            "invoice_date": payload.get("invoice_date") if "invoice_date" in payload else (before.invoice_date if before else None),
            "invoice_status": self._clean_optional_text(payload.get("invoice_status") if "invoice_status" in payload else (before.invoice_status if before else None)),
            "invoice_amount": invoice_amount,
            "target_creator_count": target,
            "approved_creator_count": approved,
            "contracted_creator_count": contracted,
        }

    def create_influencer_campaign(self, actor: CampaignOpsUser | None, **kwargs: Any) -> InfluencerCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCampaignRecord:
            payload = self._validate_influencer_campaign_payload(repository, actor, kwargs)
            if repository.get_active_influencer_campaign_by_title(payload["program_id"], payload["campaign_title"]):
                raise CampaignOpsValidationError("An active Influencer campaign with this title already exists for this shared program.")
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in INFLUENCER_RESOURCE_TYPES and url:
                    self._validate_resource_url(str(url))
            if not payload.get("workstream_id"):
                existing = next((w for w in repository.list_all_workstreams_by_program(payload["program_id"]) if w.workstream_type == WorkstreamType.INFLUENCER.value and w.is_active), None)
                payload["workstream_id"] = existing.id if existing else repository.create_workstream(payload["program_id"], WorkstreamType.INFLUENCER.value, actor_user_id=actor.id if actor else None, owner_user_id=payload.get("manager_user_id")).id
            campaign = repository.create_influencer_campaign(actor_user_id=actor.id if actor else None, **payload)
            repository.create_or_update_influencer_creator_summary(
                campaign.id,
                target_creator_count=payload.get("target_creator_count"),
                approved_count=payload.get("approved_creator_count"),
                contracted_count=payload.get("contracted_creator_count"),
                is_active=True,
            )
            if kwargs.get("use_standard_template"):
                self._create_standard_influencer_steps(repository, actor, campaign)
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in INFLUENCER_RESOURCE_TYPES:
                    resource = repository.create_resource(program_id=campaign.program_id, workstream_id=campaign.workstream_id, resource_type=resource_type, title=resource_type, url=self._validate_resource_url(url) if url else None, actor_user_id=actor.id if actor else None)
                    repository.append_event(event_type="resource_created", entity_type="resource", entity_id=resource.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added {resource.resource_type} for Influencer campaign {campaign.campaign_title}.")
            repository.append_event(event_type="influencer_campaign_created", entity_type="influencer_campaign", entity_id=campaign.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} created Influencer campaign {campaign.campaign_title}.")
            return campaign

        return self._transaction(operation)

    def update_influencer_campaign(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> InfluencerCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCampaignRecord:
            before = self._require_influencer_campaign(repository, campaign_id)
            payload = self._validate_influencer_campaign_payload(repository, actor, kwargs, before)
            duplicate = repository.get_active_influencer_campaign_by_title(payload["program_id"], payload["campaign_title"])
            if duplicate and duplicate.id != campaign_id:
                raise CampaignOpsValidationError("An active Influencer campaign with this title already exists for this shared program.")
            changes = {field: value for field, value in payload.items() if field != "program_id" and getattr(before, field) != value}
            if not changes:
                return before
            merged = {field: getattr(before, field) for field in payload if field != "program_id"}
            merged.update(changes)
            updated = repository.update_influencer_campaign(campaign_id, **merged)
            for field, value in changes.items():
                event_type = f"influencer_campaign_{field}_changed"
                message = f"{self._influencer_actor_label(actor)} changed {field.replace('_', ' ')} from {getattr(before, field) or '-'} to {value or '-'}."
                if field == "is_on_hold":
                    event_type = "influencer_campaign_placed_on_hold" if value else "influencer_campaign_resumed"
                    message = f"{self._influencer_actor_label(actor)} {'placed ' + updated.campaign_title + ' on hold: ' + (updated.hold_reason or '-') if value else 'resumed ' + updated.campaign_title}."
                repository.append_event(event_type=event_type, entity_type="influencer_campaign", entity_id=campaign_id, program_id=updated.program_id, workstream_id=updated.workstream_id, actor_user_id=actor.id if actor else None, old_value_json={field: self._activity_value(getattr(before, field))}, new_value_json={field: self._activity_value(value)}, message=message)
            if any(field in changes for field in ("target_creator_count", "approved_creator_count", "contracted_creator_count")):
                repository.create_or_update_influencer_creator_summary(campaign_id, target_creator_count=updated.target_creator_count, approved_count=updated.approved_creator_count, contracted_count=updated.contracted_creator_count, is_active=True)
            return updated

        return self._transaction(operation)

    def place_influencer_campaign_on_hold(self, actor: CampaignOpsUser | None, campaign_id: str, hold_reason: str) -> InfluencerCampaignRecord:
        return self.update_influencer_campaign(actor, campaign_id, is_on_hold=True, hold_reason=hold_reason, planning_status=PLANNING_STATUS_ON_HOLD)

    def resume_influencer_campaign(self, actor: CampaignOpsUser | None, campaign_id: str, planning_status: str | None = None) -> InfluencerCampaignRecord:
        return self.update_influencer_campaign(actor, campaign_id, is_on_hold=False, planning_status=planning_status or PLANNING_STATUS_NOT_STARTED)

    def list_influencer_campaigns(self, actor: CampaignOpsUser | None, include_inactive: bool = False, manager_user_id: str | None = None, stage: str | None = INFLUENCER_STAGE_PLANNING) -> list[InfluencerPlanningPortfolioRow]:
        repository = self.repository or CampaignOpsRepository()
        rows = repository.list_influencer_campaigns(include_inactive=include_inactive, manager_user_id=manager_user_id, stage=stage)
        if can_access_admin(actor):
            return rows
        return [row for row in rows if can_view_program(actor, self._require_program(repository, row.program_id), repository.list_assignments_by_program(row.program_id)) or row.manager_user_id == (actor.id if actor else None)]

    def get_influencer_campaign_detail(self, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerCampaignDetail:
        repository = self.repository or CampaignOpsRepository()
        detail = repository.get_influencer_campaign_detail(campaign_id)
        if detail is None:
            raise CampaignOpsNotFoundError("Influencer campaign was not found.")
        if not (can_view_program(actor, self._require_program(repository, detail.program_id), repository.list_assignments_by_program(detail.program_id)) or detail.manager_user_id == (actor.id if actor else None) or can_access_admin(actor)):
            raise CampaignOpsPermissionError("You do not have access to this Influencer campaign.")
        return detail

    def deactivate_influencer_campaign(self, actor: CampaignOpsUser | None, campaign_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._require_influencer_campaign(repository, campaign_id)
            self._validate_influencer_access(repository, actor, campaign.program_id)
            repository.deactivate_influencer_campaign(campaign_id)
            repository.append_event(event_type="influencer_campaign_deactivated", entity_type="influencer_campaign", entity_id=campaign_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated Influencer campaign {campaign.campaign_title}.")
        self._transaction(operation)

    def reactivate_influencer_campaign(self, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCampaignRecord:
            campaign = self._require_influencer_campaign(repository, campaign_id)
            self._validate_influencer_access(repository, actor, campaign.program_id)
            updated = repository.reactivate_influencer_campaign(campaign_id)
            repository.append_event(event_type="influencer_campaign_reactivated", entity_type="influencer_campaign", entity_id=campaign_id, program_id=updated.program_id, workstream_id=updated.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated Influencer campaign {updated.campaign_title}.")
            return updated
        return self._transaction(operation)

    def _create_standard_influencer_steps(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, campaign: InfluencerCampaignRecord) -> list[InfluencerPlanningStepRecord]:
        existing = {step.step_title.lower() for step in repository.list_influencer_planning_steps(campaign.id, include_inactive=True)}
        created: list[InfluencerPlanningStepRecord] = []
        for index, title in enumerate(STANDARD_PLANNING_TEMPLATE, start=1):
            if title.lower() in existing:
                continue
            step = repository.create_influencer_planning_step(campaign.id, title, step_type="standard_template", sequence_order=index, status="not_started")
            repository.append_event(event_type="influencer_planning_step_created", entity_type="influencer_planning_step", entity_id=step.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added planning step {step.step_title}.")
            created.append(step)
        return created

    def create_standard_influencer_planning_template(self, actor: CampaignOpsUser | None, campaign_id: str) -> list[InfluencerPlanningStepRecord]:
        def operation(repository: CampaignOpsRepository) -> list[InfluencerPlanningStepRecord]:
            campaign = self._require_influencer_campaign(repository, campaign_id)
            self._validate_influencer_access(repository, actor, campaign.program_id)
            return self._create_standard_influencer_steps(repository, actor, campaign)
        return self._transaction(operation)

    def _influencer_child_context(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerCampaignRecord:
        campaign = self._require_influencer_campaign(repository, campaign_id)
        self._validate_influencer_access(repository, actor, campaign.program_id)
        return campaign

    def _planning_step_payload(self, repository: CampaignOpsRepository, campaign_id: str, kwargs: dict[str, Any], before: InfluencerPlanningStepRecord | None = None) -> dict[str, Any]:
        assigned_user_id = kwargs.get("assigned_user_id") if "assigned_user_id" in kwargs else (before.assigned_user_id if before else None)
        if assigned_user_id:
            self._require_active_user(repository, str(assigned_user_id), "Assigned user")
        start = kwargs.get("start_date") if "start_date" in kwargs else (before.start_date if before else None)
        due = kwargs.get("due_date") if "due_date" in kwargs else (before.due_date if before else None)
        if start and due and due < start:
            raise CampaignOpsValidationError("Due date cannot precede start date.")
        responsible = self._clean_optional_text(kwargs.get("responsible_party") if "responsible_party" in kwargs else (before.responsible_party if before else None))
        if responsible and responsible not in RESPONSIBLE_PARTIES:
            raise CampaignOpsValidationError("Responsible party is invalid.")
        return {"step_type": self._clean_optional_text(kwargs.get("step_type") if "step_type" in kwargs else (before.step_type if before else None)), "step_title": require_text(kwargs.get("step_title") or (before.step_title if before else None), "Planning step title"), "step_description": self._clean_optional_text(kwargs.get("step_description") if "step_description" in kwargs else (before.step_description if before else None)), "sequence_order": self._non_negative_int(kwargs.get("sequence_order") if "sequence_order" in kwargs else (before.sequence_order if before else 0), "Sequence order") or 0, "responsible_party": responsible, "assigned_user_id": str(assigned_user_id) if assigned_user_id else None, "start_date": start, "due_date": due, "completed_date": kwargs.get("completed_date") if "completed_date" in kwargs else (before.completed_date if before else None), "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), PLANNING_STEP_STATUSES, "Planning step status"), "hard_deadline": bool(kwargs.get("hard_deadline") if "hard_deadline" in kwargs else (before.hard_deadline if before else False)), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))}

    def create_influencer_planning_step(self, actor: CampaignOpsUser | None, campaign_id: str, step_title: str, **kwargs: Any) -> InfluencerPlanningStepRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerPlanningStepRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            payload = self._planning_step_payload(repository, campaign_id, {**kwargs, "step_title": step_title})
            step = repository.create_influencer_planning_step(campaign_id, **payload)
            repository.append_event(event_type="influencer_planning_step_created", entity_type="influencer_planning_step", entity_id=step.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added planning step {step.step_title}.")
            return step
        return self._transaction(operation)

    def list_influencer_planning_steps(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerPlanningStepRecord]:
        self.get_influencer_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_influencer_planning_steps(campaign_id, include_inactive=include_inactive)

    def update_influencer_planning_step(self, actor: CampaignOpsUser | None, campaign_id: str, step_id: str, **kwargs: Any) -> InfluencerPlanningStepRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerPlanningStepRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            before = next((step for step in repository.list_influencer_planning_steps(campaign_id, include_inactive=True) if step.id == step_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Planning step was not found.")
            payload = self._planning_step_payload(repository, campaign_id, kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            updated = repository.update_influencer_planning_step(step_id, **payload)
            repository.append_event(event_type="influencer_planning_step_updated", entity_type="influencer_planning_step", entity_id=step_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated planning step {updated.step_title}.")
            return updated
        return self._transaction(operation)

    def reorder_influencer_planning_steps(self, actor: CampaignOpsUser | None, campaign_id: str, ordered_ids: list[str]) -> list[InfluencerPlanningStepRecord]:
        updated: list[InfluencerPlanningStepRecord] = []
        for index, step_id in enumerate(ordered_ids, start=1):
            updated.append(self.update_influencer_planning_step(actor, campaign_id, step_id, sequence_order=index))
        return updated

    def complete_influencer_planning_step(self, actor: CampaignOpsUser | None, campaign_id: str, step_id: str, completed_date: date | None = None) -> InfluencerPlanningStepRecord:
        return self.update_influencer_planning_step(actor, campaign_id, step_id, status="complete", completed_date=completed_date or date.today())

    def reopen_influencer_planning_step(self, actor: CampaignOpsUser | None, campaign_id: str, step_id: str) -> InfluencerPlanningStepRecord:
        return self.update_influencer_planning_step(actor, campaign_id, step_id, status="in_progress", completed_date=None)

    def deactivate_influencer_planning_step(self, actor: CampaignOpsUser | None, campaign_id: str, step_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            repository.deactivate_influencer_planning_step(step_id)
            repository.append_event(event_type="influencer_planning_step_deactivated", entity_type="influencer_planning_step", entity_id=step_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a planning step.")
        self._transaction(operation)

    def reactivate_influencer_planning_step(self, actor: CampaignOpsUser | None, campaign_id: str, step_id: str) -> InfluencerPlanningStepRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerPlanningStepRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            step = repository.reactivate_influencer_planning_step(step_id)
            repository.append_event(event_type="influencer_planning_step_reactivated", entity_type="influencer_planning_step", entity_id=step_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated planning step {step.step_title}.")
            return step
        return self._transaction(operation)

    def _approval_payload(self, kwargs: dict[str, Any], before: InfluencerApprovalRoundRecord | None = None) -> dict[str, Any]:
        round_number = int(kwargs.get("round_number") if "round_number" in kwargs else (before.round_number if before else 1))
        if round_number <= 0:
            raise CampaignOpsValidationError("Approval round number must be positive.")
        requested = kwargs.get("requested_date") if "requested_date" in kwargs else (before.requested_date if before else None)
        feedback_due = kwargs.get("feedback_due_date") if "feedback_due_date" in kwargs else (before.feedback_due_date if before else None)
        feedback_received = kwargs.get("feedback_received_date") if "feedback_received_date" in kwargs else (before.feedback_received_date if before else None)
        approved = kwargs.get("approved_date") if "approved_date" in kwargs else (before.approved_date if before else None)
        if requested and any(item and item < requested for item in (feedback_due, feedback_received, approved)):
            raise CampaignOpsValidationError("Approval dates cannot precede requested date.")
        approval_type = require_text(kwargs.get("approval_type") or (before.approval_type if before else None), "Approval type")
        if approval_type not in APPROVAL_TYPES:
            raise CampaignOpsValidationError("Approval type is invalid.")
        return {"approval_type": approval_type, "round_number": round_number, "approval_scope": self._clean_optional_text(kwargs.get("approval_scope") if "approval_scope" in kwargs else (before.approval_scope if before else None)), "requested_date": requested, "feedback_due_date": feedback_due, "feedback_received_date": feedback_received, "approved_date": approved, "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), APPROVAL_STATUSES, "Approval status"), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))}

    def create_influencer_approval_round(self, actor: CampaignOpsUser | None, campaign_id: str, approval_type: str, **kwargs: Any) -> InfluencerApprovalRoundRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerApprovalRoundRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            approval = repository.create_influencer_approval_round(campaign_id, **self._approval_payload({**kwargs, "approval_type": approval_type}))
            repository.append_event(event_type="influencer_approval_round_created", entity_type="influencer_approval_round", entity_id=approval.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added {approval.approval_type} approval.")
            return approval
        return self._transaction(operation)

    def list_influencer_approval_rounds(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerApprovalRoundRecord]:
        self.get_influencer_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_influencer_approval_rounds(campaign_id, include_inactive=include_inactive)

    def update_influencer_approval_round(self, actor: CampaignOpsUser | None, campaign_id: str, approval_id: str, **kwargs: Any) -> InfluencerApprovalRoundRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerApprovalRoundRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            before = next((item for item in repository.list_influencer_approval_rounds(campaign_id, include_inactive=True) if item.id == approval_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Approval round was not found.")
            payload = self._approval_payload(kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            updated = repository.update_influencer_approval_round(approval_id, **payload)
            repository.append_event(event_type="influencer_approval_round_updated", entity_type="influencer_approval_round", entity_id=approval_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated {updated.approval_type} approval.")
            return updated
        return self._transaction(operation)

    def mark_influencer_approval_sent(self, actor: CampaignOpsUser | None, campaign_id: str, approval_id: str, requested_date: date | None = None) -> InfluencerApprovalRoundRecord:
        return self.update_influencer_approval_round(actor, campaign_id, approval_id, status="sent", requested_date=requested_date or date.today())

    def mark_influencer_approval_feedback_received(self, actor: CampaignOpsUser | None, campaign_id: str, approval_id: str, feedback_received_date: date | None = None) -> InfluencerApprovalRoundRecord:
        return self.update_influencer_approval_round(actor, campaign_id, approval_id, status="feedback_received", feedback_received_date=feedback_received_date or date.today())

    def mark_influencer_approval_approved(self, actor: CampaignOpsUser | None, campaign_id: str, approval_id: str, approved_date: date | None = None) -> InfluencerApprovalRoundRecord:
        return self.update_influencer_approval_round(actor, campaign_id, approval_id, status="approved", approved_date=approved_date or date.today())

    def reopen_influencer_approval_round(self, actor: CampaignOpsUser | None, campaign_id: str, approval_id: str) -> InfluencerApprovalRoundRecord:
        return self.update_influencer_approval_round(actor, campaign_id, approval_id, status="reopened", approved_date=None)

    def deactivate_influencer_approval_round(self, actor: CampaignOpsUser | None, campaign_id: str, approval_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            repository.deactivate_influencer_approval_round(approval_id)
            repository.append_event(event_type="influencer_approval_round_deactivated", entity_type="influencer_approval_round", entity_id=approval_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated an approval round.")
        self._transaction(operation)

    def reactivate_influencer_approval_round(self, actor: CampaignOpsUser | None, campaign_id: str, approval_id: str) -> InfluencerApprovalRoundRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerApprovalRoundRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            approval = repository.reactivate_influencer_approval_round(approval_id)
            repository.append_event(event_type="influencer_approval_round_reactivated", entity_type="influencer_approval_round", entity_id=approval_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated {approval.approval_type} approval.")
            return approval
        return self._transaction(operation)

    def _content_round_payload(self, kwargs: dict[str, Any], before: InfluencerContentRoundRecord | None = None) -> dict[str, Any]:
        round_number = int(kwargs.get("round_number") if "round_number" in kwargs else (before.round_number if before else 1))
        if round_number <= 0:
            raise CampaignOpsValidationError("Content round number must be positive.")
        content_type = self._clean_optional_text(kwargs.get("content_type") if "content_type" in kwargs else (before.content_type if before else None))
        if content_type and content_type not in CONTENT_ROUND_TYPES:
            raise CampaignOpsValidationError("Content type is invalid.")
        sent = kwargs.get("client_review_sent_date") if "client_review_sent_date" in kwargs else (before.client_review_sent_date if before else None)
        feedback_due = kwargs.get("client_feedback_due_date") if "client_feedback_due_date" in kwargs else (before.client_feedback_due_date if before else None)
        feedback_received = kwargs.get("feedback_received_date") if "feedback_received_date" in kwargs else (before.feedback_received_date if before else None)
        approved = kwargs.get("approved_date") if "approved_date" in kwargs else (before.approved_date if before else None)
        if sent and any(item and item < sent for item in (feedback_due, feedback_received, approved)):
            raise CampaignOpsValidationError("Content round dates cannot precede client review sent date.")
        return {"round_number": round_number, "content_type": content_type, "internal_review_due_date": kwargs.get("internal_review_due_date") if "internal_review_due_date" in kwargs else (before.internal_review_due_date if before else None), "client_review_sent_date": sent, "client_feedback_due_date": feedback_due, "feedback_received_date": feedback_received, "resubmission_due_date": kwargs.get("resubmission_due_date") if "resubmission_due_date" in kwargs else (before.resubmission_due_date if before else None), "approved_date": approved, "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), CONTENT_ROUND_STATUSES, "Content round status"), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))}

    def create_influencer_content_round(self, actor: CampaignOpsUser | None, campaign_id: str, round_number: int, **kwargs: Any) -> InfluencerContentRoundRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerContentRoundRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            content_round = repository.create_influencer_content_round(campaign_id, **self._content_round_payload({**kwargs, "round_number": round_number}))
            repository.append_event(event_type="influencer_content_round_created", entity_type="influencer_content_round", entity_id=content_round.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added content round {content_round.round_number}.")
            return content_round
        return self._transaction(operation)

    def list_influencer_content_rounds(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerContentRoundRecord]:
        self.get_influencer_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_influencer_content_rounds(campaign_id, include_inactive=include_inactive)

    def update_influencer_content_round(self, actor: CampaignOpsUser | None, campaign_id: str, content_round_id: str, **kwargs: Any) -> InfluencerContentRoundRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerContentRoundRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            before = next((item for item in repository.list_influencer_content_rounds(campaign_id, include_inactive=True) if item.id == content_round_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Content round was not found.")
            payload = self._content_round_payload(kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            updated = repository.update_influencer_content_round(content_round_id, **payload)
            repository.append_event(event_type="influencer_content_round_updated", entity_type="influencer_content_round", entity_id=content_round_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated content round {updated.round_number}.")
            return updated
        return self._transaction(operation)

    def mark_influencer_content_round_sent_for_review(self, actor: CampaignOpsUser | None, campaign_id: str, content_round_id: str, sent_date: date | None = None) -> InfluencerContentRoundRecord:
        return self.update_influencer_content_round(actor, campaign_id, content_round_id, status="sent_for_client_review", client_review_sent_date=sent_date or date.today())

    def mark_influencer_content_round_feedback_received(self, actor: CampaignOpsUser | None, campaign_id: str, content_round_id: str, feedback_received_date: date | None = None) -> InfluencerContentRoundRecord:
        return self.update_influencer_content_round(actor, campaign_id, content_round_id, status="feedback_received", feedback_received_date=feedback_received_date or date.today())

    def mark_influencer_content_round_approved(self, actor: CampaignOpsUser | None, campaign_id: str, content_round_id: str, approved_date: date | None = None) -> InfluencerContentRoundRecord:
        return self.update_influencer_content_round(actor, campaign_id, content_round_id, status="approved", approved_date=approved_date or date.today())

    def reopen_influencer_content_round(self, actor: CampaignOpsUser | None, campaign_id: str, content_round_id: str) -> InfluencerContentRoundRecord:
        return self.update_influencer_content_round(actor, campaign_id, content_round_id, status="reopened", approved_date=None)

    def deactivate_influencer_content_round(self, actor: CampaignOpsUser | None, campaign_id: str, content_round_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            repository.deactivate_influencer_content_round(content_round_id)
            repository.append_event(event_type="influencer_content_round_deactivated", entity_type="influencer_content_round", entity_id=content_round_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a content round.")
        self._transaction(operation)

    def reactivate_influencer_content_round(self, actor: CampaignOpsUser | None, campaign_id: str, content_round_id: str) -> InfluencerContentRoundRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerContentRoundRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            content_round = repository.reactivate_influencer_content_round(content_round_id)
            repository.append_event(event_type="influencer_content_round_reactivated", entity_type="influencer_content_round", entity_id=content_round_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated content round {content_round.round_number}.")
            return content_round
        return self._transaction(operation)

    def create_or_update_influencer_creator_summary(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> InfluencerCreatorSummaryRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCreatorSummaryRecord:
            campaign = self._influencer_child_context(repository, actor, campaign_id)
            before = repository.get_influencer_creator_summary(campaign_id)
            fields = ["target_creator_count", "applicants_count", "vetted_count", "submitted_for_approval_count", "approved_count", "contracted_count", "content_submitted_count", "content_approved_count"]
            payload = {field: self._non_negative_int(kwargs.get(field) if field in kwargs else (getattr(before, field) if before else None), field.replace("_", " ").title()) for field in fields}
            payload["notes"] = self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))
            payload["is_active"] = bool(kwargs.get("is_active") if "is_active" in kwargs else (before.is_active if before else True))
            if before and not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            summary = repository.create_or_update_influencer_creator_summary(campaign_id, **payload)
            repository.append_event(event_type="influencer_creator_summary_updated", entity_type="influencer_creator_summary", entity_id=summary.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated creator summary for {campaign.campaign_title}.")
            repository.update_influencer_campaign(campaign_id, workstream_id=campaign.workstream_id, campaign_title=campaign.campaign_title, manager_user_id=campaign.manager_user_id, influencer_stage=campaign.influencer_stage, planning_status=campaign.planning_status, latest_update=campaign.latest_update, waiting_on=campaign.waiting_on, is_on_hold=campaign.is_on_hold, hold_reason=campaign.hold_reason, application_open_date=campaign.application_open_date, application_close_date=campaign.application_close_date, influencer_approval_due_date=campaign.influencer_approval_due_date, scripts_due_date=campaign.scripts_due_date, first_content_due_date=campaign.first_content_due_date, launch_date=campaign.launch_date, wrap_date=campaign.wrap_date, invoice_date=campaign.invoice_date, invoice_status=campaign.invoice_status, invoice_amount=campaign.invoice_amount, target_creator_count=summary.target_creator_count, approved_creator_count=summary.approved_count, contracted_creator_count=summary.contracted_count)
            return summary
        return self._transaction(operation)

    def get_influencer_creator_summary(self, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerCreatorSummaryRecord | None:
        self.get_influencer_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).get_influencer_creator_summary(campaign_id)

    def transition_influencer_campaign_to_live(self, actor: CampaignOpsUser | None, campaign_id: str, live_status: str | None = None) -> InfluencerCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCampaignRecord:
            before = self._require_influencer_campaign(repository, campaign_id)
            self._validate_influencer_access(repository, actor, before.program_id)
            if not before.is_active:
                raise CampaignOpsValidationError("Inactive Influencer campaigns cannot be moved to Live.")
            if before.influencer_stage == INFLUENCER_STAGE_LIVE:
                return before
            updated = repository.update_influencer_campaign(
                campaign_id,
                workstream_id=before.workstream_id,
                campaign_title=before.campaign_title,
                manager_user_id=before.manager_user_id,
                influencer_stage=INFLUENCER_STAGE_LIVE,
                planning_status=normalize_live_status(live_status or LIVE_STATUS_READY_TO_LAUNCH),
                latest_update=before.latest_update,
                waiting_on=before.waiting_on,
                is_on_hold=before.is_on_hold,
                hold_reason=before.hold_reason,
                application_open_date=before.application_open_date,
                application_close_date=before.application_close_date,
                influencer_approval_due_date=before.influencer_approval_due_date,
                scripts_due_date=before.scripts_due_date,
                first_content_due_date=before.first_content_due_date,
                launch_date=before.launch_date,
                wrap_date=before.wrap_date,
                invoice_date=before.invoice_date,
                invoice_status=before.invoice_status,
                invoice_amount=before.invoice_amount,
                target_creator_count=before.target_creator_count,
                approved_creator_count=before.approved_creator_count,
                contracted_creator_count=before.contracted_creator_count,
            )
            repository.append_event(event_type="influencer_stage_moved_to_live", entity_type="influencer_campaign", entity_id=campaign_id, program_id=updated.program_id, workstream_id=updated.workstream_id, actor_user_id=actor.id if actor else None, old_value_json={"stage": before.influencer_stage}, new_value_json={"stage": updated.influencer_stage}, message=f"{self._influencer_actor_label(actor)} moved {updated.campaign_title} from Planning to Live.")
            return updated
        return self._transaction(operation)

    def list_influencer_live_campaigns(self, actor: CampaignOpsUser | None, include_inactive: bool = False, manager_user_id: str | None = None) -> list[InfluencerLivePortfolioRow]:
        repository = self.repository or CampaignOpsRepository()
        rows = repository.list_influencer_live_campaigns(include_inactive=include_inactive, manager_user_id=manager_user_id)
        if can_access_admin(actor):
            return rows
        return [row for row in rows if can_view_program(actor, self._require_program(repository, row.program_id), repository.list_assignments_by_program(row.program_id)) or row.manager_user_id == (actor.id if actor else None)]

    def get_influencer_live_campaign_detail(self, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerLivePortfolioRow:
        repository = self.repository or CampaignOpsRepository()
        detail = repository.get_influencer_live_campaign_detail(campaign_id)
        if detail is None:
            raise CampaignOpsNotFoundError("Influencer Live campaign was not found.")
        if not (can_access_admin(actor) or can_view_program(actor, self._require_program(repository, detail.program_id), repository.list_assignments_by_program(detail.program_id)) or detail.manager_user_id == (actor.id if actor else None)):
            raise CampaignOpsPermissionError("You do not have access to this Influencer Live campaign.")
        return detail

    def get_influencer_live_workspace_summary(self, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerLiveWorkspaceSummary:
        campaign = self.get_influencer_live_campaign_detail(actor, campaign_id)
        return InfluencerLiveWorkspaceSummary(
            campaign=campaign,
            planning_steps=self.list_influencer_planning_steps(actor, campaign_id, include_inactive=True),
            approval_rounds=self.list_influencer_approval_rounds(actor, campaign_id, include_inactive=True),
            content_rounds=self.list_influencer_content_rounds(actor, campaign_id, include_inactive=True),
            creator_summary=self.get_influencer_creator_summary(actor, campaign_id),
            checkpoints=self.list_influencer_live_checkpoints(actor, campaign_id, include_inactive=True),
            waves=self.list_influencer_creator_waves(actor, campaign_id, include_inactive=True),
            creators=self.list_influencer_live_creators(actor, campaign_id, include_inactive=True),
            exceptions=self.list_influencer_live_exceptions(actor, campaign_id, include_inactive=True),
            wrap_readiness=self.influencer_live_wrap_readiness(campaign, self.list_influencer_live_checkpoints(actor, campaign_id), self.list_influencer_creator_waves(actor, campaign_id), self.list_influencer_live_creators(actor, campaign_id), self.list_influencer_live_exceptions(actor, campaign_id)),
        )

    def get_influencer_live_manager_board_data(self, actor: CampaignOpsUser | None, campaigns: list[InfluencerLivePortfolioRow]) -> dict[str, dict[str, list[Any]]]:
        repository = self.repository or CampaignOpsRepository()
        campaign_ids = [campaign.id for campaign in campaigns]
        program_ids = list(dict.fromkeys(campaign.program_id for campaign in campaigns))
        if not campaign_ids:
            return {"planning_steps": {}, "checkpoints": {}, "waves": {}, "resources": {}}
        return {
            "planning_steps": repository.list_influencer_planning_steps_for_campaigns(campaign_ids),
            "checkpoints": repository.list_influencer_live_checkpoints_for_campaigns(campaign_ids),
            "waves": repository.list_influencer_creator_waves_for_campaigns(campaign_ids),
            "resources": repository.list_resources_for_programs(program_ids),
        }

    def _live_campaign_context(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerCampaignRecord:
        campaign = self._influencer_child_context(repository, actor, campaign_id)
        if campaign.influencer_stage != INFLUENCER_STAGE_LIVE:
            raise CampaignOpsValidationError("Campaign must be in Live stage for this action.")
        return campaign

    def update_influencer_live_overview(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> InfluencerCampaignRecord:
        kwargs["influencer_stage"] = INFLUENCER_STAGE_LIVE
        if "planning_status" in kwargs:
            kwargs["planning_status"] = normalize_live_status(kwargs["planning_status"])
        return self.update_influencer_campaign(actor, campaign_id, **kwargs)

    def _live_checkpoint_payload(self, repository: CampaignOpsRepository, kwargs: dict[str, Any], before: InfluencerLiveCheckpointRecord | None = None) -> dict[str, Any]:
        assigned_user_id = kwargs.get("assigned_user_id") if "assigned_user_id" in kwargs else (before.assigned_user_id if before else None)
        if assigned_user_id:
            self._require_active_user(repository, str(assigned_user_id), "Assigned user")
        start = kwargs.get("start_date") if "start_date" in kwargs else (before.start_date if before else None)
        due = kwargs.get("due_date") if "due_date" in kwargs else (before.due_date if before else None)
        if start and due and due < start:
            raise CampaignOpsValidationError("Due date cannot precede start date.")
        responsible = self._clean_optional_text(kwargs.get("responsible_party") if "responsible_party" in kwargs else (before.responsible_party if before else None))
        if responsible and responsible not in RESPONSIBLE_PARTIES:
            raise CampaignOpsValidationError("Responsible party is invalid.")
        return {"checkpoint_type": self._clean_optional_text(kwargs.get("checkpoint_type") if "checkpoint_type" in kwargs else (before.checkpoint_type if before else None)), "checkpoint_title": require_text(kwargs.get("checkpoint_title") or (before.checkpoint_title if before else None), "Checkpoint title"), "checkpoint_description": self._clean_optional_text(kwargs.get("checkpoint_description") if "checkpoint_description" in kwargs else (before.checkpoint_description if before else None)), "sequence_order": self._non_negative_int(kwargs.get("sequence_order") if "sequence_order" in kwargs else (before.sequence_order if before else 0), "Sequence order") or 0, "responsible_party": responsible, "assigned_user_id": str(assigned_user_id) if assigned_user_id else None, "start_date": start, "due_date": due, "completed_date": kwargs.get("completed_date") if "completed_date" in kwargs else (before.completed_date if before else None), "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), LIVE_CHECKPOINT_STATUSES, "Live checkpoint status"), "hard_deadline": bool(kwargs.get("hard_deadline") if "hard_deadline" in kwargs else (before.hard_deadline if before else False)), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))}

    def create_influencer_live_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_title: str, **kwargs: Any) -> InfluencerLiveCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveCheckpointRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            checkpoint = repository.create_influencer_live_checkpoint(campaign_id, **self._live_checkpoint_payload(repository, {**kwargs, "checkpoint_title": checkpoint_title}))
            repository.append_event(event_type="influencer_live_checkpoint_created", entity_type="influencer_live_checkpoint", entity_id=checkpoint.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added Live checkpoint {checkpoint.checkpoint_title}.")
            return checkpoint
        return self._transaction(operation)

    def create_standard_influencer_live_template(self, actor: CampaignOpsUser | None, campaign_id: str) -> list[InfluencerLiveCheckpointRecord]:
        def operation(repository: CampaignOpsRepository) -> list[InfluencerLiveCheckpointRecord]:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            existing = {item.checkpoint_title.lower() for item in repository.list_influencer_live_checkpoints(campaign_id, include_inactive=True)}
            created = []
            for index, title in enumerate(STANDARD_LIVE_CHECKPOINT_TEMPLATE, start=1):
                if title.lower() in existing:
                    continue
                checkpoint = repository.create_influencer_live_checkpoint(campaign_id, title, checkpoint_type="standard_template", sequence_order=index, status="not_started")
                repository.append_event(event_type="influencer_live_checkpoint_created", entity_type="influencer_live_checkpoint", entity_id=checkpoint.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added Live checkpoint {checkpoint.checkpoint_title}.")
                created.append(checkpoint)
            return created
        return self._transaction(operation)

    def list_influencer_live_checkpoints(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveCheckpointRecord]:
        repository = self.repository or CampaignOpsRepository()
        campaign = self._require_influencer_campaign(repository, campaign_id)
        self._validate_influencer_access(repository, actor, campaign.program_id)
        return repository.list_influencer_live_checkpoints(campaign_id, include_inactive=include_inactive)

    def update_influencer_live_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str, **kwargs: Any) -> InfluencerLiveCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveCheckpointRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            before = next((item for item in repository.list_influencer_live_checkpoints(campaign_id, include_inactive=True) if item.id == checkpoint_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Live checkpoint was not found.")
            payload = self._live_checkpoint_payload(repository, kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            updated = repository.update_influencer_live_checkpoint(checkpoint_id, **payload)
            repository.append_event(event_type="influencer_live_checkpoint_updated", entity_type="influencer_live_checkpoint", entity_id=checkpoint_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated Live checkpoint {updated.checkpoint_title}.")
            return updated
        return self._transaction(operation)

    def reorder_influencer_live_checkpoints(self, actor: CampaignOpsUser | None, campaign_id: str, ordered_ids: list[str]) -> list[InfluencerLiveCheckpointRecord]:
        return [self.update_influencer_live_checkpoint(actor, campaign_id, checkpoint_id, sequence_order=index) for index, checkpoint_id in enumerate(ordered_ids, start=1)]

    def complete_influencer_live_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str, completed_date: date | None = None) -> InfluencerLiveCheckpointRecord:
        return self.update_influencer_live_checkpoint(actor, campaign_id, checkpoint_id, status="complete", completed_date=completed_date or date.today())

    def reopen_influencer_live_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str) -> InfluencerLiveCheckpointRecord:
        return self.update_influencer_live_checkpoint(actor, campaign_id, checkpoint_id, status="in_progress", completed_date=None)

    def deactivate_influencer_live_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            repository.deactivate_influencer_live_checkpoint(checkpoint_id)
            repository.append_event(event_type="influencer_live_checkpoint_deactivated", entity_type="influencer_live_checkpoint", entity_id=checkpoint_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a Live checkpoint.")
        self._transaction(operation)

    def reactivate_influencer_live_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str) -> InfluencerLiveCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveCheckpointRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            checkpoint = repository.reactivate_influencer_live_checkpoint(checkpoint_id)
            repository.append_event(event_type="influencer_live_checkpoint_reactivated", entity_type="influencer_live_checkpoint", entity_id=checkpoint_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated Live checkpoint {checkpoint.checkpoint_title}.")
            return checkpoint
        return self._transaction(operation)

    def _wave_payload(self, repository: CampaignOpsRepository, campaign_id: str, kwargs: dict[str, Any], before: InfluencerCreatorWaveRecord | None = None) -> dict[str, Any]:
        wave_number = int(kwargs.get("wave_number") if "wave_number" in kwargs else (before.wave_number if before else 1))
        if wave_number <= 0:
            raise CampaignOpsValidationError("Wave number must be positive.")
        planned_start = kwargs.get("planned_start_date") if "planned_start_date" in kwargs else (before.planned_start_date if before else None)
        planned_end = kwargs.get("planned_end_date") if "planned_end_date" in kwargs else (before.planned_end_date if before else None)
        actual_start = kwargs.get("actual_start_date") if "actual_start_date" in kwargs else (before.actual_start_date if before else None)
        actual_end = kwargs.get("actual_end_date") if "actual_end_date" in kwargs else (before.actual_end_date if before else None)
        if planned_start and planned_end and planned_end < planned_start:
            raise CampaignOpsValidationError("Planned end date cannot precede planned start date.")
        if actual_start and actual_end and actual_end < actual_start:
            raise CampaignOpsValidationError("Actual end date cannot precede actual start date.")
        planned = self._non_negative_int(kwargs.get("planned_creator_count") if "planned_creator_count" in kwargs else (before.planned_creator_count if before else None), "Planned creator count")
        live = self._non_negative_int(kwargs.get("live_creator_count") if "live_creator_count" in kwargs else (before.live_creator_count if before else None), "Live creator count")
        completed = self._non_negative_int(kwargs.get("completed_creator_count") if "completed_creator_count" in kwargs else (before.completed_creator_count if before else None), "Completed creator count")
        if completed is not None and live is not None and completed > live:
            raise CampaignOpsValidationError("Completed creator count cannot exceed live creator count.")
        if live is not None and planned is not None and live > planned:
            raise CampaignOpsValidationError("Live creator count cannot exceed planned creator count.")
        return {"wave_number": wave_number, "wave_name": self._clean_optional_text(kwargs.get("wave_name") if "wave_name" in kwargs else (before.wave_name if before else None)), "planned_start_date": planned_start, "planned_end_date": planned_end, "actual_start_date": actual_start, "actual_end_date": actual_end, "planned_creator_count": planned, "live_creator_count": live, "completed_creator_count": completed, "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), WAVE_STATUSES, "Wave status"), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))}

    def create_influencer_creator_wave(self, actor: CampaignOpsUser | None, campaign_id: str, wave_number: int, **kwargs: Any) -> InfluencerCreatorWaveRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCreatorWaveRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            payload = self._wave_payload(repository, campaign_id, {**kwargs, "wave_number": wave_number})
            if any(w.wave_number == payload["wave_number"] and w.is_active for w in repository.list_influencer_creator_waves(campaign_id, include_inactive=True)):
                raise CampaignOpsValidationError("Duplicate active wave number is not allowed for one campaign.")
            wave = repository.create_influencer_creator_wave(campaign_id, **payload)
            repository.append_event(event_type="influencer_creator_wave_created", entity_type="influencer_creator_wave", entity_id=wave.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added Creator Wave {wave.wave_number}.")
            return wave
        return self._transaction(operation)

    def list_influencer_creator_waves(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerCreatorWaveRecord]:
        repository = self.repository or CampaignOpsRepository()
        campaign = self._require_influencer_campaign(repository, campaign_id)
        self._validate_influencer_access(repository, actor, campaign.program_id)
        return repository.list_influencer_creator_waves(campaign_id, include_inactive=include_inactive)

    def update_influencer_creator_wave(self, actor: CampaignOpsUser | None, campaign_id: str, wave_id: str, **kwargs: Any) -> InfluencerCreatorWaveRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCreatorWaveRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            before = next((w for w in repository.list_influencer_creator_waves(campaign_id, include_inactive=True) if w.id == wave_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Creator wave was not found.")
            payload = self._wave_payload(repository, campaign_id, kwargs, before)
            if payload["wave_number"] != before.wave_number and any(w.id != wave_id and w.wave_number == payload["wave_number"] and w.is_active for w in repository.list_influencer_creator_waves(campaign_id, include_inactive=True)):
                raise CampaignOpsValidationError("Duplicate active wave number is not allowed for one campaign.")
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            wave = repository.update_influencer_creator_wave(wave_id, **payload)
            repository.append_event(event_type="influencer_creator_wave_updated", entity_type="influencer_creator_wave", entity_id=wave_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated Creator Wave {wave.wave_number}.")
            return wave
        return self._transaction(operation)

    def start_influencer_creator_wave(self, actor: CampaignOpsUser | None, campaign_id: str, wave_id: str, actual_start_date: date | None = None) -> InfluencerCreatorWaveRecord:
        return self.update_influencer_creator_wave(actor, campaign_id, wave_id, status="in_progress", actual_start_date=actual_start_date or date.today())

    def complete_influencer_creator_wave(self, actor: CampaignOpsUser | None, campaign_id: str, wave_id: str, actual_end_date: date | None = None) -> InfluencerCreatorWaveRecord:
        return self.update_influencer_creator_wave(actor, campaign_id, wave_id, status="complete", actual_end_date=actual_end_date or date.today())

    def reopen_influencer_creator_wave(self, actor: CampaignOpsUser | None, campaign_id: str, wave_id: str) -> InfluencerCreatorWaveRecord:
        return self.update_influencer_creator_wave(actor, campaign_id, wave_id, status="reopened", actual_end_date=None)

    def deactivate_influencer_creator_wave(self, actor: CampaignOpsUser | None, campaign_id: str, wave_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            repository.deactivate_influencer_creator_wave(wave_id)
            repository.append_event(event_type="influencer_creator_wave_deactivated", entity_type="influencer_creator_wave", entity_id=wave_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a creator wave.")
        self._transaction(operation)

    def reactivate_influencer_creator_wave(self, actor: CampaignOpsUser | None, campaign_id: str, wave_id: str) -> InfluencerCreatorWaveRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCreatorWaveRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            wave = repository.reactivate_influencer_creator_wave(wave_id)
            repository.append_event(event_type="influencer_creator_wave_reactivated", entity_type="influencer_creator_wave", entity_id=wave_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated Creator Wave {wave.wave_number}.")
            return wave
        return self._transaction(operation)

    def _validate_live_wave(self, repository: CampaignOpsRepository, campaign_id: str, wave_id: str | None) -> None:
        if not wave_id:
            return
        if not any(w.id == wave_id for w in repository.list_influencer_creator_waves(campaign_id, include_inactive=True)):
            raise CampaignOpsValidationError("Selected creator wave is invalid.")

    def _live_creator_payload(self, repository: CampaignOpsRepository, campaign_id: str, kwargs: dict[str, Any], before: InfluencerLiveCreatorRecord | None = None) -> dict[str, Any]:
        wave_id = kwargs.get("wave_id") if "wave_id" in kwargs else (before.wave_id if before else None)
        self._validate_live_wave(repository, campaign_id, str(wave_id) if wave_id else None)
        def valid_url(field: str) -> str | None:
            value = kwargs.get(field) if field in kwargs else (getattr(before, field) if before else None)
            return self._validate_resource_url(value) if value else None
        impressions = self._non_negative_int(kwargs.get("latest_impressions") if "latest_impressions" in kwargs else (before.latest_impressions if before else None), "Latest impressions")
        return {"wave_id": str(wave_id) if wave_id else None, "creator_name": require_text(kwargs.get("creator_name") or (before.creator_name if before else None), "Creator name"), "creator_handle": self._clean_optional_text(kwargs.get("creator_handle") if "creator_handle" in kwargs else (before.creator_handle if before else None)), "platform": self._clean_optional_text(kwargs.get("platform") if "platform" in kwargs else (before.platform if before else None)), "live_status": normalize_influencer_optional_status(kwargs.get("live_status") if "live_status" in kwargs else (before.live_status if before else None), CREATOR_LIVE_STATUSES, "Creator live status"), "draft_status": normalize_influencer_optional_status(kwargs.get("draft_status") if "draft_status" in kwargs else (before.draft_status if before else None), CREATOR_DRAFT_STATUSES, "Creator draft status"), "approval_status": normalize_influencer_optional_status(kwargs.get("approval_status") if "approval_status" in kwargs else (before.approval_status if before else None), CREATOR_APPROVAL_STATUSES, "Creator approval status"), "scheduled_live_date": kwargs.get("scheduled_live_date") if "scheduled_live_date" in kwargs else (before.scheduled_live_date if before else None), "actual_live_date": kwargs.get("actual_live_date") if "actual_live_date" in kwargs else (before.actual_live_date if before else None), "paid_live_end_date": kwargs.get("paid_live_end_date") if "paid_live_end_date" in kwargs else (before.paid_live_end_date if before else None), "content_url": valid_url("content_url"), "click2cart_url": valid_url("click2cart_url"), "retailer_url": valid_url("retailer_url"), "impressions_reporting_required": bool(kwargs.get("impressions_reporting_required") if "impressions_reporting_required" in kwargs else (before.impressions_reporting_required if before else False)), "latest_impressions": impressions, "last_impressions_update_date": kwargs.get("last_impressions_update_date") if "last_impressions_update_date" in kwargs else (before.last_impressions_update_date if before else None), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "exception_status": self._clean_optional_text(kwargs.get("exception_status") if "exception_status" in kwargs else (before.exception_status if before else None)), "exception_notes": self._clean_optional_text(kwargs.get("exception_notes") if "exception_notes" in kwargs else (before.exception_notes if before else None))}

    def create_influencer_live_creator(self, actor: CampaignOpsUser | None, campaign_id: str, creator_name: str, **kwargs: Any) -> InfluencerLiveCreatorRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveCreatorRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            creator = repository.create_influencer_live_creator(campaign_id, **self._live_creator_payload(repository, campaign_id, {**kwargs, "creator_name": creator_name}))
            repository.append_event(event_type="influencer_live_creator_created", entity_type="influencer_live_creator", entity_id=creator.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added creator {creator.creator_name}.")
            return creator
        return self._transaction(operation)

    def list_influencer_live_creators(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveCreatorRecord]:
        repository = self.repository or CampaignOpsRepository()
        campaign = self._require_influencer_campaign(repository, campaign_id)
        self._validate_influencer_access(repository, actor, campaign.program_id)
        return repository.list_influencer_live_creators(campaign_id, include_inactive=include_inactive)

    def update_influencer_live_creator(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str, **kwargs: Any) -> InfluencerLiveCreatorRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveCreatorRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            before = next((c for c in repository.list_influencer_live_creators(campaign_id, include_inactive=True) if c.id == creator_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Live creator was not found.")
            payload = self._live_creator_payload(repository, campaign_id, kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            creator = repository.update_influencer_live_creator(creator_id, **payload)
            event_type = "influencer_live_creator_impressions_updated" if "latest_impressions" in kwargs else "influencer_live_creator_updated"
            repository.append_event(event_type=event_type, entity_type="influencer_live_creator", entity_id=creator_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated creator {creator.creator_name}.")
            return creator
        return self._transaction(operation)

    def mark_influencer_live_creator_draft_submitted(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str) -> InfluencerLiveCreatorRecord:
        return self.update_influencer_live_creator(actor, campaign_id, creator_id, draft_status="submitted")

    def mark_influencer_live_creator_approved(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str) -> InfluencerLiveCreatorRecord:
        return self.update_influencer_live_creator(actor, campaign_id, creator_id, approval_status="approved", live_status="approved")

    def mark_influencer_live_creator_scheduled(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str, scheduled_live_date: date | None = None) -> InfluencerLiveCreatorRecord:
        return self.update_influencer_live_creator(actor, campaign_id, creator_id, live_status="scheduled", scheduled_live_date=scheduled_live_date)

    def mark_influencer_live_creator_live(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str, actual_live_date: date | None = None) -> InfluencerLiveCreatorRecord:
        return self.update_influencer_live_creator(actor, campaign_id, creator_id, live_status="live", actual_live_date=actual_live_date or date.today())

    def mark_influencer_live_creator_paid_live_complete(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str, paid_live_end_date: date | None = None) -> InfluencerLiveCreatorRecord:
        return self.update_influencer_live_creator(actor, campaign_id, creator_id, live_status="paid_live_complete", paid_live_end_date=paid_live_end_date or date.today())

    def update_influencer_live_creator_impressions(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str, latest_impressions: int, update_date: date | None = None) -> InfluencerLiveCreatorRecord:
        return self.update_influencer_live_creator(actor, campaign_id, creator_id, impressions_reporting_required=True, latest_impressions=latest_impressions, last_impressions_update_date=update_date or date.today())

    def deactivate_influencer_live_creator(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            repository.deactivate_influencer_live_creator(creator_id)
            repository.append_event(event_type="influencer_live_creator_deactivated", entity_type="influencer_live_creator", entity_id=creator_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a Live creator.")
        self._transaction(operation)

    def reactivate_influencer_live_creator(self, actor: CampaignOpsUser | None, campaign_id: str, creator_id: str) -> InfluencerLiveCreatorRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveCreatorRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            creator = repository.reactivate_influencer_live_creator(creator_id)
            repository.append_event(event_type="influencer_live_creator_reactivated", entity_type="influencer_live_creator", entity_id=creator_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated creator {creator.creator_name}.")
            return creator
        return self._transaction(operation)

    def _validate_live_creator_link(self, repository: CampaignOpsRepository, campaign_id: str, creator_id: str | None) -> None:
        if not creator_id:
            return
        if not any(c.id == creator_id for c in repository.list_influencer_live_creators(campaign_id, include_inactive=True)):
            raise CampaignOpsValidationError("Selected Live creator is invalid.")

    def _live_exception_payload(self, repository: CampaignOpsRepository, campaign_id: str, kwargs: dict[str, Any], before: InfluencerLiveExceptionRecord | None = None) -> dict[str, Any]:
        creator_id = kwargs.get("live_creator_id") if "live_creator_id" in kwargs else (before.live_creator_id if before else None)
        self._validate_live_creator_link(repository, campaign_id, str(creator_id) if creator_id else None)
        owner_id = kwargs.get("owner_user_id") if "owner_user_id" in kwargs else (before.owner_user_id if before else None)
        if owner_id:
            self._require_active_user(repository, str(owner_id), "Owner")
        opened = kwargs.get("opened_date") if "opened_date" in kwargs else (before.opened_date if before else None)
        due = kwargs.get("due_date") if "due_date" in kwargs else (before.due_date if before else None)
        if opened and due and due < opened:
            raise CampaignOpsValidationError("Exception due date cannot precede opened date.")
        exception_type = self._clean_optional_text(kwargs.get("exception_type") if "exception_type" in kwargs else (before.exception_type if before else None))
        if exception_type and exception_type not in LIVE_EXCEPTION_TYPES:
            raise CampaignOpsValidationError("Exception type is invalid.")
        return {"live_creator_id": str(creator_id) if creator_id else None, "exception_type": exception_type, "exception_title": require_text(kwargs.get("exception_title") or (before.exception_title if before else None), "Exception title"), "description": self._clean_optional_text(kwargs.get("description") if "description" in kwargs else (before.description if before else None)), "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), LIVE_EXCEPTION_STATUSES, "Exception status"), "owner_user_id": str(owner_id) if owner_id else None, "opened_date": opened, "due_date": due, "resolved_date": kwargs.get("resolved_date") if "resolved_date" in kwargs else (before.resolved_date if before else None), "resolution_notes": self._clean_optional_text(kwargs.get("resolution_notes") if "resolution_notes" in kwargs else (before.resolution_notes if before else None)), "is_highlighted": bool(kwargs.get("is_highlighted") if "is_highlighted" in kwargs else (before.is_highlighted if before else False))}

    def create_influencer_live_exception(self, actor: CampaignOpsUser | None, campaign_id: str, exception_title: str, **kwargs: Any) -> InfluencerLiveExceptionRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveExceptionRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            exception = repository.create_influencer_live_exception(campaign_id, **self._live_exception_payload(repository, campaign_id, {**kwargs, "exception_title": exception_title}))
            repository.append_event(event_type="influencer_live_exception_created", entity_type="influencer_live_exception", entity_id=exception.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} opened exception {exception.exception_title}.")
            return exception
        return self._transaction(operation)

    def list_influencer_live_exceptions(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveExceptionRecord]:
        repository = self.repository or CampaignOpsRepository()
        campaign = self._require_influencer_campaign(repository, campaign_id)
        self._validate_influencer_access(repository, actor, campaign.program_id)
        return repository.list_influencer_live_exceptions(campaign_id, include_inactive=include_inactive)

    def update_influencer_live_exception(self, actor: CampaignOpsUser | None, campaign_id: str, exception_id: str, **kwargs: Any) -> InfluencerLiveExceptionRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveExceptionRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            before = next((e for e in repository.list_influencer_live_exceptions(campaign_id, include_inactive=True) if e.id == exception_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Live exception was not found.")
            payload = self._live_exception_payload(repository, campaign_id, kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            exception = repository.update_influencer_live_exception(exception_id, **payload)
            repository.append_event(event_type="influencer_live_exception_updated", entity_type="influencer_live_exception", entity_id=exception_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated exception {exception.exception_title}.")
            return exception
        return self._transaction(operation)

    def resolve_influencer_live_exception(self, actor: CampaignOpsUser | None, campaign_id: str, exception_id: str, resolution_notes: str | None = None) -> InfluencerLiveExceptionRecord:
        return self.update_influencer_live_exception(actor, campaign_id, exception_id, status="resolved", resolved_date=date.today(), resolution_notes=resolution_notes)

    def reopen_influencer_live_exception(self, actor: CampaignOpsUser | None, campaign_id: str, exception_id: str) -> InfluencerLiveExceptionRecord:
        return self.update_influencer_live_exception(actor, campaign_id, exception_id, status="reopened", resolved_date=None)

    def deactivate_influencer_live_exception(self, actor: CampaignOpsUser | None, campaign_id: str, exception_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            repository.deactivate_influencer_live_exception(exception_id)
            repository.append_event(event_type="influencer_live_exception_deactivated", entity_type="influencer_live_exception", entity_id=exception_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a Live exception.")
        self._transaction(operation)

    def reactivate_influencer_live_exception(self, actor: CampaignOpsUser | None, campaign_id: str, exception_id: str) -> InfluencerLiveExceptionRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerLiveExceptionRecord:
            campaign = self._live_campaign_context(repository, actor, campaign_id)
            exception = repository.reactivate_influencer_live_exception(exception_id)
            repository.append_event(event_type="influencer_live_exception_reactivated", entity_type="influencer_live_exception", entity_id=exception_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated exception {exception.exception_title}.")
            return exception
        return self._transaction(operation)

    def influencer_live_wrap_readiness(self, campaign: InfluencerLivePortfolioRow, checkpoints: list[InfluencerLiveCheckpointRecord], waves: list[InfluencerCreatorWaveRecord], creators: list[InfluencerLiveCreatorRecord], exceptions: list[InfluencerLiveExceptionRecord]) -> str:
        open_checkpoints = [c for c in checkpoints if c.is_active and c.status != "complete"]
        open_waves = [w for w in waves if w.is_active and w.status != "complete"]
        open_creators = [c for c in creators if c.is_active and c.live_status not in ("live", "paid_live_complete", "complete")]
        open_exceptions = [e for e in exceptions if e.is_active and e.status not in ("resolved", "cancelled")]
        if open_exceptions or any(e.is_highlighted and e.status not in ("resolved", "cancelled") for e in exceptions if e.is_active):
            return "Needs Attention"
        if open_checkpoints or open_waves or open_creators:
            return "Not Ready"
        if campaign.wrap_date and campaign.wrap_date <= date.today():
            return "Wrapped"
        return "Ready to Wrap"

    def transition_influencer_campaign_to_recapping(self, actor: CampaignOpsUser | None, campaign_id: str, recap_status: str | None = None, allow_override: bool = False) -> InfluencerCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCampaignRecord:
            before = self._require_influencer_campaign(repository, campaign_id)
            self._validate_influencer_access(repository, actor, before.program_id)
            if not before.is_active:
                raise CampaignOpsValidationError("Inactive Influencer campaigns cannot move to Recapping.")
            if before.influencer_stage == INFLUENCER_STAGE_RECAPPING:
                return before
            if before.influencer_stage != INFLUENCER_STAGE_LIVE:
                raise CampaignOpsValidationError("Only Live Influencer campaigns can move to Recapping.")
            live_detail = repository.get_influencer_live_campaign_detail(campaign_id)
            if live_detail is None:
                raise CampaignOpsNotFoundError("Live campaign was not found.")
            readiness = self.influencer_live_wrap_readiness(
                live_detail,
                repository.list_influencer_live_checkpoints(campaign_id),
                repository.list_influencer_creator_waves(campaign_id),
                repository.list_influencer_live_creators(campaign_id),
                repository.list_influencer_live_exceptions(campaign_id),
            )
            if readiness in ("Not Ready", "Needs Attention") and not (allow_override and can_access_admin(actor)):
                raise CampaignOpsValidationError("Live campaign is not ready for Recapping.")
            updated = repository.update_influencer_campaign(
                campaign_id,
                workstream_id=before.workstream_id,
                campaign_title=before.campaign_title,
                manager_user_id=before.manager_user_id,
                influencer_stage=INFLUENCER_STAGE_RECAPPING,
                planning_status=normalize_recap_status(recap_status or RECAP_STATUS_READY_TO_RECAP),
                latest_update=before.latest_update,
                waiting_on=before.waiting_on,
                is_on_hold=before.is_on_hold,
                hold_reason=before.hold_reason,
                application_open_date=before.application_open_date,
                application_close_date=before.application_close_date,
                influencer_approval_due_date=before.influencer_approval_due_date,
                scripts_due_date=before.scripts_due_date,
                first_content_due_date=before.first_content_due_date,
                launch_date=before.launch_date,
                wrap_date=before.wrap_date,
                invoice_date=before.invoice_date,
                invoice_status=before.invoice_status,
                invoice_amount=before.invoice_amount,
                target_creator_count=before.target_creator_count,
                approved_creator_count=before.approved_creator_count,
                contracted_creator_count=before.contracted_creator_count,
            )
            record = repository.get_influencer_recap_record(campaign_id)
            if record is None:
                repository.create_or_update_influencer_recap_record(
                    campaign_id,
                    recap_status=updated.planning_status,
                    latest_update=updated.latest_update,
                    waiting_on=updated.waiting_on,
                    invoice_status=updated.invoice_status,
                    is_active=True,
                )
            repository.append_event(
                event_type="influencer_stage_moved_to_recapping",
                entity_type="influencer_campaign",
                entity_id=campaign_id,
                program_id=updated.program_id,
                workstream_id=updated.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{self._influencer_actor_label(actor)} moved {updated.campaign_title} from Live to Recapping.",
                old_value_json={"stage": before.influencer_stage, "readiness": readiness},
                new_value_json={"stage": updated.influencer_stage, "recap_status": updated.planning_status},
            )
            return updated
        return self._transaction(operation)

    def _recap_campaign_context(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerCampaignRecord:
        campaign = self._require_influencer_campaign(repository, campaign_id)
        self._validate_influencer_access(repository, actor, campaign.program_id)
        if campaign.influencer_stage != INFLUENCER_STAGE_RECAPPING:
            raise CampaignOpsValidationError("Influencer campaign is not in Recapping.")
        return campaign

    def _recap_record_payload(self, kwargs: dict[str, Any], before: InfluencerRecapRecord | None = None) -> dict[str, Any]:
        final_close = kwargs.get("final_close_date") if "final_close_date" in kwargs else (before.final_close_date if before else None)
        delivered = kwargs.get("recap_delivered_date") if "recap_delivered_date" in kwargs else (before.recap_delivered_date if before else None)
        if final_close and delivered and final_close < delivered:
            raise CampaignOpsValidationError("Final close date cannot be before recap delivered date.")
        return {
            "recap_status": normalize_recap_status(kwargs.get("recap_status") if "recap_status" in kwargs else (before.recap_status if before else None)),
            "latest_update": self._clean_optional_text(kwargs.get("latest_update") if "latest_update" in kwargs else (before.latest_update if before else None)),
            "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)),
            "reporting_due_date": kwargs.get("reporting_due_date") if "reporting_due_date" in kwargs else (before.reporting_due_date if before else None),
            "draft_recap_due_date": kwargs.get("draft_recap_due_date") if "draft_recap_due_date" in kwargs else (before.draft_recap_due_date if before else None),
            "internal_review_date": kwargs.get("internal_review_date") if "internal_review_date" in kwargs else (before.internal_review_date if before else None),
            "client_review_date": kwargs.get("client_review_date") if "client_review_date" in kwargs else (before.client_review_date if before else None),
            "client_recap_date": kwargs.get("client_recap_date") if "client_recap_date" in kwargs else (before.client_recap_date if before else None),
            "recap_delivered_date": delivered,
            "final_close_date": final_close,
            "final_invoice_sent_date": kwargs.get("final_invoice_sent_date") if "final_invoice_sent_date" in kwargs else (before.final_invoice_sent_date if before else None),
            "sales_lift_analysis_required": bool(kwargs.get("sales_lift_analysis_required") if "sales_lift_analysis_required" in kwargs else (before.sales_lift_analysis_required if before else False)),
            "sales_lift_analysis_status": self._clean_optional_text(kwargs.get("sales_lift_analysis_status") if "sales_lift_analysis_status" in kwargs else (before.sales_lift_analysis_status if before else None)),
            "final_performance_data_status": self._clean_optional_text(kwargs.get("final_performance_data_status") if "final_performance_data_status" in kwargs else (before.final_performance_data_status if before else None)),
            "creator_closeout_status": self._clean_optional_text(kwargs.get("creator_closeout_status") if "creator_closeout_status" in kwargs else (before.creator_closeout_status if before else None)),
            "eop_survey_status": self._clean_optional_text(kwargs.get("eop_survey_status") if "eop_survey_status" in kwargs else (before.eop_survey_status if before else None)),
            "invoice_status": self._clean_optional_text(kwargs.get("invoice_status") if "invoice_status" in kwargs else (before.invoice_status if before else None)),
            "financial_close_status": self._clean_optional_text(kwargs.get("financial_close_status") if "financial_close_status" in kwargs else (before.financial_close_status if before else None)),
            "lessons_learned": self._clean_optional_text(kwargs.get("lessons_learned") if "lessons_learned" in kwargs else (before.lessons_learned if before else None)),
            "is_active": bool(kwargs.get("is_active") if "is_active" in kwargs else (before.is_active if before else True)),
        }

    def create_or_update_influencer_recap_record(self, actor: CampaignOpsUser | None, campaign_id: str, **kwargs: Any) -> InfluencerRecapRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            before = repository.get_influencer_recap_record(campaign_id)
            payload = self._recap_record_payload(kwargs, before)
            if before and not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            record = repository.update_influencer_recap_record(before.id, **payload) if before else repository.create_or_update_influencer_recap_record(campaign_id, **payload)
            repository.update_influencer_campaign(
                campaign_id,
                workstream_id=campaign.workstream_id,
                campaign_title=campaign.campaign_title,
                manager_user_id=campaign.manager_user_id,
                influencer_stage=campaign.influencer_stage,
                planning_status=record.recap_status,
                latest_update=record.latest_update,
                waiting_on=record.waiting_on,
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
                target_creator_count=campaign.target_creator_count,
                approved_creator_count=campaign.approved_creator_count,
                contracted_creator_count=campaign.contracted_creator_count,
            )
            event_type = "influencer_recap_record_updated" if before else "influencer_recap_record_created"
            repository.append_event(event_type=event_type, entity_type="influencer_recap_record", entity_id=record.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated Recapping overview for {campaign.campaign_title}.")
            return record
        return self._transaction(operation)

    def list_influencer_recap_campaigns(self, actor: CampaignOpsUser | None, include_inactive: bool = False, manager_user_id: str | None = None) -> list[InfluencerRecapPortfolioRow]:
        repository = self.repository or CampaignOpsRepository()
        rows = repository.list_influencer_recap_campaigns(include_inactive=include_inactive, manager_user_id=manager_user_id)
        return [row for row in rows if can_view_program(actor, repository.get_program(row.program_id), repository.list_assignments_by_program(row.program_id))]

    def get_influencer_recap_campaign_detail(self, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerRecapPortfolioRow:
        repository = self.repository or CampaignOpsRepository()
        detail = repository.get_influencer_recap_campaign_detail(campaign_id)
        if detail is None:
            raise CampaignOpsNotFoundError("Recapping campaign was not found.")
        self._validate_influencer_access(repository, actor, detail.program_id)
        return detail

    def get_influencer_recap_manager_board_data(self, actor: CampaignOpsUser | None, campaigns: list[InfluencerRecapPortfolioRow]) -> dict[str, dict[str, list[Any]]]:
        repository = self.repository or CampaignOpsRepository()
        campaign_ids = [campaign.id for campaign in campaigns]
        program_ids = list(dict.fromkeys(campaign.program_id for campaign in campaigns))
        if not campaign_ids:
            return {"launch_items": {}, "resources": {}}
        return {
            "launch_items": repository.list_influencer_recap_launch_items_for_campaigns(campaign_ids),
            "resources": repository.list_resources_for_programs(program_ids),
        }

    def creator_closeout_summary(self, recap_record: InfluencerRecapRecord | None, creators: list[InfluencerLiveCreatorRecord], exceptions: list[InfluencerLiveExceptionRecord]) -> InfluencerCreatorCloseoutSummary:
        active = [c for c in creators if c.is_active]
        return InfluencerCreatorCloseoutSummary(
            total_creators=len(active),
            live_creators=len([c for c in active if c.live_status in ("live", "paid_live_complete", "complete")]),
            completed_creators=len([c for c in active if c.live_status in ("paid_live_complete", "complete")]),
            missing_final_links=len([c for c in active if not c.content_url]),
            missing_final_impressions=len([c for c in active if c.impressions_reporting_required and c.latest_impressions is None]),
            open_creator_exceptions=len([e for e in exceptions if e.is_active and e.status not in ("resolved", "cancelled")]),
            paid_live_incomplete=len([c for c in active if c.live_status not in ("paid_live_complete", "complete", "cancelled")]),
            creator_closeout_status=recap_record.creator_closeout_status if recap_record else None,
        )

    def influencer_recap_ready_to_close_state(self, recap_record: InfluencerRecapRecord | None, checkpoints: list[InfluencerRecapCheckpointRecord], requirements: list[InfluencerRecapRequirementRecord], closeout: InfluencerCreatorCloseoutSummary, exceptions: list[InfluencerLiveExceptionRecord]) -> str:
        if any(e.is_active and e.status not in ("resolved", "cancelled") for e in exceptions):
            return "Needs Attention"
        if any(c.is_active and c.status != "complete" for c in checkpoints):
            return "Not Ready"
        if any(r.is_active and r.required and r.status not in ("complete", "not_required", "cancelled") for r in requirements):
            return "Not Ready"
        if closeout.open_creator_exceptions or closeout.paid_live_incomplete or closeout.missing_final_links or closeout.missing_final_impressions:
            return "Not Ready"
        if recap_record and recap_record.recap_status == RECAP_STATUS_COMPLETE:
            return "Complete"
        return "Ready to Close"

    def get_influencer_recap_workspace_summary(self, actor: CampaignOpsUser | None, campaign_id: str) -> InfluencerRecapWorkspaceSummary:
        campaign = self.get_influencer_recap_campaign_detail(actor, campaign_id)
        repository = self.repository or CampaignOpsRepository()
        recap_record = repository.get_influencer_recap_record(campaign_id)
        creators = self.list_influencer_live_creators(actor, campaign_id, include_inactive=True)
        exceptions = self.list_influencer_live_exceptions(actor, campaign_id, include_inactive=True)
        checkpoints = self.list_influencer_recap_checkpoints(actor, campaign_id, include_inactive=True)
        requirements = self.list_influencer_recap_requirements(actor, campaign_id, include_inactive=True)
        closeout = self.creator_closeout_summary(recap_record, creators, exceptions)
        ready = self.influencer_recap_ready_to_close_state(recap_record, checkpoints, requirements, closeout, exceptions)
        return InfluencerRecapWorkspaceSummary(
            campaign=campaign,
            recap_record=recap_record,
            planning_steps=self.list_influencer_planning_steps(actor, campaign_id, include_inactive=True),
            approval_rounds=self.list_influencer_approval_rounds(actor, campaign_id, include_inactive=True),
            content_rounds=self.list_influencer_content_rounds(actor, campaign_id, include_inactive=True),
            live_checkpoints=self.list_influencer_live_checkpoints(actor, campaign_id, include_inactive=True),
            waves=self.list_influencer_creator_waves(actor, campaign_id, include_inactive=True),
            creators=creators,
            exceptions=exceptions,
            checkpoints=checkpoints,
            requirements=requirements,
            launch_items=self.list_influencer_recap_launch_items(actor, campaign_id, include_inactive=True),
            creator_closeout=closeout,
            ready_to_close_state=ready,
        )

    def _recap_checkpoint_payload(self, repository: CampaignOpsRepository, kwargs: dict[str, Any], before: InfluencerRecapCheckpointRecord | None = None) -> dict[str, Any]:
        assigned = kwargs.get("assigned_user_id") if "assigned_user_id" in kwargs else (before.assigned_user_id if before else None)
        if assigned:
            self._require_active_user(repository, str(assigned), "Assigned user")
        return {"checkpoint_type": self._clean_optional_text(kwargs.get("checkpoint_type") if "checkpoint_type" in kwargs else (before.checkpoint_type if before else None)), "checkpoint_title": require_text(kwargs.get("checkpoint_title") or (before.checkpoint_title if before else None), "Checkpoint title"), "sequence_order": self._non_negative_int(kwargs.get("sequence_order") if "sequence_order" in kwargs else (before.sequence_order if before else 0), "Sequence order") or 0, "responsible_party": self._clean_optional_text(kwargs.get("responsible_party") if "responsible_party" in kwargs else (before.responsible_party if before else None)), "assigned_user_id": str(assigned) if assigned else None, "due_date": kwargs.get("due_date") if "due_date" in kwargs else (before.due_date if before else None), "completed_date": kwargs.get("completed_date") if "completed_date" in kwargs else (before.completed_date if before else None), "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), RECAP_CHECKPOINT_STATUSES, "Recap checkpoint status"), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None)), "hard_deadline": bool(kwargs.get("hard_deadline") if "hard_deadline" in kwargs else (before.hard_deadline if before else False))}

    def create_standard_influencer_recap_template(self, actor: CampaignOpsUser | None, campaign_id: str) -> list[InfluencerRecapCheckpointRecord]:
        def operation(repository: CampaignOpsRepository) -> list[InfluencerRecapCheckpointRecord]:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            existing = {item.checkpoint_title.lower() for item in repository.list_influencer_recap_checkpoints(campaign_id, include_inactive=True)}
            created = []
            for index, title in enumerate(STANDARD_RECAP_CHECKLIST_TEMPLATE, start=1):
                if title.lower() in existing:
                    continue
                checkpoint = repository.create_influencer_recap_checkpoint(campaign_id, title, checkpoint_type="standard_template", sequence_order=index, status="not_started")
                repository.append_event(event_type="influencer_recap_checkpoint_created", entity_type="influencer_recap_checkpoint", entity_id=checkpoint.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added Recap checkpoint {checkpoint.checkpoint_title}.")
                created.append(checkpoint)
            return created
        return self._transaction(operation)

    def create_influencer_recap_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_title: str, **kwargs: Any) -> InfluencerRecapCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapCheckpointRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            checkpoint = repository.create_influencer_recap_checkpoint(campaign_id, **self._recap_checkpoint_payload(repository, {**kwargs, "checkpoint_title": checkpoint_title}))
            repository.append_event(event_type="influencer_recap_checkpoint_created", entity_type="influencer_recap_checkpoint", entity_id=checkpoint.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added Recap checkpoint {checkpoint.checkpoint_title}.")
            return checkpoint
        return self._transaction(operation)

    def list_influencer_recap_checkpoints(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapCheckpointRecord]:
        self.get_influencer_recap_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_influencer_recap_checkpoints(campaign_id, include_inactive=include_inactive)

    def update_influencer_recap_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str, **kwargs: Any) -> InfluencerRecapCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapCheckpointRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            before = next((item for item in repository.list_influencer_recap_checkpoints(campaign_id, include_inactive=True) if item.id == checkpoint_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Recap checkpoint was not found.")
            payload = self._recap_checkpoint_payload(repository, kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            updated = repository.update_influencer_recap_checkpoint(checkpoint_id, **payload)
            event_type = "influencer_recap_checkpoint_completed" if payload.get("status") == "complete" else "influencer_recap_checkpoint_updated"
            repository.append_event(event_type=event_type, entity_type="influencer_recap_checkpoint", entity_id=checkpoint_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated Recap checkpoint {updated.checkpoint_title}.")
            return updated
        return self._transaction(operation)

    def reorder_influencer_recap_checkpoints(self, actor: CampaignOpsUser | None, campaign_id: str, ordered_ids: list[str]) -> list[InfluencerRecapCheckpointRecord]:
        return [self.update_influencer_recap_checkpoint(actor, campaign_id, checkpoint_id, sequence_order=index) for index, checkpoint_id in enumerate(ordered_ids, start=1)]

    def complete_influencer_recap_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str, completed_date: date | None = None) -> InfluencerRecapCheckpointRecord:
        return self.update_influencer_recap_checkpoint(actor, campaign_id, checkpoint_id, status="complete", completed_date=completed_date or date.today())

    def reopen_influencer_recap_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str) -> InfluencerRecapCheckpointRecord:
        return self.update_influencer_recap_checkpoint(actor, campaign_id, checkpoint_id, status="reopened", completed_date=None)

    def deactivate_influencer_recap_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            repository.deactivate_influencer_recap_checkpoint(checkpoint_id)
            repository.append_event(event_type="influencer_recap_checkpoint_deactivated", entity_type="influencer_recap_checkpoint", entity_id=checkpoint_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a Recap checkpoint.")
        self._transaction(operation)

    def reactivate_influencer_recap_checkpoint(self, actor: CampaignOpsUser | None, campaign_id: str, checkpoint_id: str) -> InfluencerRecapCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapCheckpointRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            checkpoint = repository.reactivate_influencer_recap_checkpoint(checkpoint_id)
            repository.append_event(event_type="influencer_recap_checkpoint_reactivated", entity_type="influencer_recap_checkpoint", entity_id=checkpoint_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated Recap checkpoint {checkpoint.checkpoint_title}.")
            return checkpoint
        return self._transaction(operation)

    def _recap_requirement_payload(self, repository: CampaignOpsRepository, campaign_id: str, kwargs: dict[str, Any], before: InfluencerRecapRequirementRecord | None = None) -> dict[str, Any]:
        requirement_type = require_text(kwargs.get("requirement_type") or (before.requirement_type if before else None), "Requirement type")
        if requirement_type not in RECAP_REQUIREMENT_TYPES:
            raise CampaignOpsValidationError("Requirement type is invalid.")
        resource_id = kwargs.get("resource_id") if "resource_id" in kwargs else (before.resource_id if before else None)
        if resource_id:
            resource = repository.get_resource(str(resource_id))
            campaign = self._require_influencer_campaign(repository, campaign_id)
            if resource is None or resource.program_id != campaign.program_id:
                raise CampaignOpsValidationError("Linked resource must belong to the same program.")
        request_id = kwargs.get("reporting_request_id") if "reporting_request_id" in kwargs else (before.reporting_request_id if before else None)
        if request_id:
            request = repository.get_reporting_request(str(request_id))
            campaign = self._require_influencer_campaign(repository, campaign_id)
            if request is None or request.program_id != campaign.program_id:
                raise CampaignOpsValidationError("Linked request must belong to the same program.")
        received = kwargs.get("received_date") if "received_date" in kwargs else (before.received_date if before else None)
        completed = kwargs.get("completed_date") if "completed_date" in kwargs else (before.completed_date if before else None)
        if completed and received and completed < received:
            raise CampaignOpsValidationError("Completed date cannot be before received date.")
        return {"requirement_type": requirement_type, "requirement_title": require_text(kwargs.get("requirement_title") or (before.requirement_title if before else None), "Requirement title"), "status": normalize_influencer_optional_status(kwargs.get("status") if "status" in kwargs else (before.status if before else None), RECAP_REQUIREMENT_STATUSES, "Requirement status"), "required": bool(kwargs.get("required") if "required" in kwargs else (before.required if before else True)), "due_date": kwargs.get("due_date") if "due_date" in kwargs else (before.due_date if before else None), "received_date": received, "completed_date": completed, "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "resource_id": str(resource_id) if resource_id else None, "reporting_request_id": str(request_id) if request_id else None, "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))}

    def create_influencer_recap_requirement(self, actor: CampaignOpsUser | None, campaign_id: str, requirement_type: str, requirement_title: str, **kwargs: Any) -> InfluencerRecapRequirementRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapRequirementRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            req = repository.create_influencer_recap_requirement(campaign_id, **self._recap_requirement_payload(repository, campaign_id, {**kwargs, "requirement_type": requirement_type, "requirement_title": requirement_title}))
            repository.append_event(event_type="influencer_recap_requirement_created", entity_type="influencer_recap_requirement", entity_id=req.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added {req.requirement_type} requirement {req.requirement_title}.")
            return req
        return self._transaction(operation)

    def list_influencer_recap_requirements(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapRequirementRecord]:
        self.get_influencer_recap_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_influencer_recap_requirements(campaign_id, include_inactive=include_inactive)

    def update_influencer_recap_requirement(self, actor: CampaignOpsUser | None, campaign_id: str, requirement_id: str, **kwargs: Any) -> InfluencerRecapRequirementRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapRequirementRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            before = next((item for item in repository.list_influencer_recap_requirements(campaign_id, include_inactive=True) if item.id == requirement_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Recap requirement was not found.")
            payload = self._recap_requirement_payload(repository, campaign_id, kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            req = repository.update_influencer_recap_requirement(requirement_id, **payload)
            if "reporting_request_id" in kwargs:
                event_type = "influencer_recap_reporting_request_linked"
            elif req.requirement_type == "EOP Survey":
                event_type = "influencer_recap_eop_survey_updated"
            elif payload.get("status") == "received":
                event_type = "influencer_recap_requirement_received"
            elif payload.get("status") == "complete":
                event_type = "influencer_recap_requirement_completed"
            else:
                event_type = "influencer_recap_requirement_updated"
            repository.append_event(event_type=event_type, entity_type="influencer_recap_requirement", entity_id=requirement_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated {req.requirement_type} requirement {req.requirement_title}.")
            return req
        return self._transaction(operation)

    def mark_influencer_recap_requirement_received(self, actor: CampaignOpsUser | None, campaign_id: str, requirement_id: str, received_date: date | None = None) -> InfluencerRecapRequirementRecord:
        return self.update_influencer_recap_requirement(actor, campaign_id, requirement_id, status="received", received_date=received_date or date.today())

    def complete_influencer_recap_requirement(self, actor: CampaignOpsUser | None, campaign_id: str, requirement_id: str, completed_date: date | None = None) -> InfluencerRecapRequirementRecord:
        return self.update_influencer_recap_requirement(actor, campaign_id, requirement_id, status="complete", completed_date=completed_date or date.today())

    def reopen_influencer_recap_requirement(self, actor: CampaignOpsUser | None, campaign_id: str, requirement_id: str) -> InfluencerRecapRequirementRecord:
        return self.update_influencer_recap_requirement(actor, campaign_id, requirement_id, status="reopened", completed_date=None)

    def deactivate_influencer_recap_requirement(self, actor: CampaignOpsUser | None, campaign_id: str, requirement_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            repository.deactivate_influencer_recap_requirement(requirement_id)
            repository.append_event(event_type="influencer_recap_requirement_deactivated", entity_type="influencer_recap_requirement", entity_id=requirement_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a Recap requirement.")
        self._transaction(operation)

    def reactivate_influencer_recap_requirement(self, actor: CampaignOpsUser | None, campaign_id: str, requirement_id: str) -> InfluencerRecapRequirementRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapRequirementRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            req = repository.reactivate_influencer_recap_requirement(requirement_id)
            repository.append_event(event_type="influencer_recap_requirement_reactivated", entity_type="influencer_recap_requirement", entity_id=requirement_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated Recap requirement {req.requirement_title}.")
            return req
        return self._transaction(operation)

    def _recap_launch_payload(self, kwargs: dict[str, Any], before: InfluencerRecapLaunchItemRecord | None = None) -> dict[str, Any]:
        product_url = kwargs.get("product_url") if "product_url" in kwargs else (before.product_url if before else None)
        retailer_url = kwargs.get("retailer_url") if "retailer_url" in kwargs else (before.retailer_url if before else None)
        return {"group_name": self._clean_optional_text(kwargs.get("group_name") if "group_name" in kwargs else (before.group_name if before else None)), "product_name": require_text(kwargs.get("product_name") or (before.product_name if before else None), "Product name"), "retailer_name": self._clean_optional_text(kwargs.get("retailer_name") if "retailer_name" in kwargs else (before.retailer_name if before else None)), "online_launch_date": kwargs.get("online_launch_date") if "online_launch_date" in kwargs else (before.online_launch_date if before else None), "in_store_launch_date": kwargs.get("in_store_launch_date") if "in_store_launch_date" in kwargs else (before.in_store_launch_date if before else None), "launch_status": normalize_influencer_optional_status(kwargs.get("launch_status") if "launch_status" in kwargs else (before.launch_status if before else None), RECAP_LAUNCH_STATUSES, "Launch status"), "product_url": self._validate_resource_url(product_url) if product_url else None, "retailer_url": self._validate_resource_url(retailer_url) if retailer_url else None, "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None)), "sort_order": self._non_negative_int(kwargs.get("sort_order") if "sort_order" in kwargs else (before.sort_order if before else 0), "Sort order") or 0}

    def create_influencer_recap_launch_item(self, actor: CampaignOpsUser | None, campaign_id: str, product_name: str, **kwargs: Any) -> InfluencerRecapLaunchItemRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapLaunchItemRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            item = repository.create_influencer_recap_launch_item(campaign_id, **self._recap_launch_payload({**kwargs, "product_name": product_name}))
            repository.append_event(event_type="influencer_recap_launch_item_created", entity_type="influencer_recap_launch_item", entity_id=item.id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} added product launch item {item.product_name}.")
            return item
        return self._transaction(operation)

    def list_influencer_recap_launch_items(self, actor: CampaignOpsUser | None, campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapLaunchItemRecord]:
        self.get_influencer_recap_campaign_detail(actor, campaign_id)
        return (self.repository or CampaignOpsRepository()).list_influencer_recap_launch_items(campaign_id, include_inactive=include_inactive)

    def update_influencer_recap_launch_item(self, actor: CampaignOpsUser | None, campaign_id: str, launch_item_id: str, **kwargs: Any) -> InfluencerRecapLaunchItemRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapLaunchItemRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            before = next((item for item in repository.list_influencer_recap_launch_items(campaign_id, include_inactive=True) if item.id == launch_item_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Recap launch item was not found.")
            payload = self._recap_launch_payload(kwargs, before)
            if not any(getattr(before, field) != value for field, value in payload.items()):
                return before
            item = repository.update_influencer_recap_launch_item(launch_item_id, **payload)
            repository.append_event(event_type="influencer_recap_launch_item_updated", entity_type="influencer_recap_launch_item", entity_id=launch_item_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} updated product launch item {item.product_name}.")
            return item
        return self._transaction(operation)

    def mark_influencer_recap_launch_online(self, actor: CampaignOpsUser | None, campaign_id: str, launch_item_id: str, online_launch_date: date | None = None) -> InfluencerRecapLaunchItemRecord:
        return self.update_influencer_recap_launch_item(actor, campaign_id, launch_item_id, launch_status="online_live", online_launch_date=online_launch_date or date.today())

    def mark_influencer_recap_launch_in_store(self, actor: CampaignOpsUser | None, campaign_id: str, launch_item_id: str, in_store_launch_date: date | None = None) -> InfluencerRecapLaunchItemRecord:
        return self.update_influencer_recap_launch_item(actor, campaign_id, launch_item_id, launch_status="in_store_live", in_store_launch_date=in_store_launch_date or date.today())

    def reorder_influencer_recap_launch_items(self, actor: CampaignOpsUser | None, campaign_id: str, ordered_ids: list[str]) -> list[InfluencerRecapLaunchItemRecord]:
        return [self.update_influencer_recap_launch_item(actor, campaign_id, item_id, sort_order=index) for index, item_id in enumerate(ordered_ids, start=1)]

    def deactivate_influencer_recap_launch_item(self, actor: CampaignOpsUser | None, campaign_id: str, launch_item_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            repository.deactivate_influencer_recap_launch_item(launch_item_id)
            repository.append_event(event_type="influencer_recap_launch_item_deactivated", entity_type="influencer_recap_launch_item", entity_id=launch_item_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} deactivated a Recap launch item.")
        self._transaction(operation)

    def reactivate_influencer_recap_launch_item(self, actor: CampaignOpsUser | None, campaign_id: str, launch_item_id: str) -> InfluencerRecapLaunchItemRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerRecapLaunchItemRecord:
            campaign = self._recap_campaign_context(repository, actor, campaign_id)
            item = repository.reactivate_influencer_recap_launch_item(launch_item_id)
            repository.append_event(event_type="influencer_recap_launch_item_reactivated", entity_type="influencer_recap_launch_item", entity_id=launch_item_id, program_id=campaign.program_id, workstream_id=campaign.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} reactivated Recap launch item {item.product_name}.")
            return item
        return self._transaction(operation)

    def complete_influencer_campaign_from_recapping(self, actor: CampaignOpsUser | None, campaign_id: str, allow_override: bool = False) -> InfluencerCampaignRecord:
        def operation(repository: CampaignOpsRepository) -> InfluencerCampaignRecord:
            before = self._recap_campaign_context(repository, actor, campaign_id)
            recap_record = repository.get_influencer_recap_record(campaign_id)
            creators = repository.list_influencer_live_creators(campaign_id)
            exceptions = repository.list_influencer_live_exceptions(campaign_id)
            checkpoints = repository.list_influencer_recap_checkpoints(campaign_id)
            requirements = repository.list_influencer_recap_requirements(campaign_id)
            ready_state = self.influencer_recap_ready_to_close_state(recap_record, checkpoints, requirements, self.creator_closeout_summary(recap_record, creators, exceptions), exceptions)
            if ready_state not in ("Ready to Close", "Complete") and not (allow_override and can_access_admin(actor)):
                raise CampaignOpsValidationError("Recapping campaign is not ready to complete.")
            updated = repository.update_influencer_campaign(
                campaign_id,
                workstream_id=before.workstream_id,
                campaign_title=before.campaign_title,
                manager_user_id=before.manager_user_id,
                influencer_stage=INFLUENCER_STAGE_COMPLETE,
                planning_status=RECAP_STATUS_COMPLETE,
                latest_update=before.latest_update,
                waiting_on=before.waiting_on,
                is_on_hold=before.is_on_hold,
                hold_reason=before.hold_reason,
                application_open_date=before.application_open_date,
                application_close_date=before.application_close_date,
                influencer_approval_due_date=before.influencer_approval_due_date,
                scripts_due_date=before.scripts_due_date,
                first_content_due_date=before.first_content_due_date,
                launch_date=before.launch_date,
                wrap_date=before.wrap_date,
                invoice_date=before.invoice_date,
                invoice_status=before.invoice_status,
                invoice_amount=before.invoice_amount,
                target_creator_count=before.target_creator_count,
                approved_creator_count=before.approved_creator_count,
                contracted_creator_count=before.contracted_creator_count,
            )
            if recap_record:
                close_date = recap_record.final_close_date or date.today()
                if recap_record.recap_delivered_date and close_date < recap_record.recap_delivered_date:
                    close_date = recap_record.recap_delivered_date
                repository.update_influencer_recap_record(
                    recap_record.id,
                    **self._recap_record_payload(
                        {"recap_status": RECAP_STATUS_COMPLETE, "final_close_date": close_date},
                        recap_record,
                    ),
                )
            repository.append_event(event_type="influencer_stage_completed", entity_type="influencer_campaign", entity_id=campaign_id, program_id=updated.program_id, workstream_id=updated.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._influencer_actor_label(actor)} completed the Influencer campaign.", old_value_json={"stage": before.influencer_stage, "ready_to_close_state": ready_state}, new_value_json={"stage": updated.influencer_stage})
            return updated
        return self._transaction(operation)

    def _content_actor_label(self, actor: CampaignOpsUser | None) -> str:
        return actor.display_name if actor else "System"

    def _require_content_program(self, repository: CampaignOpsRepository, content_program_id: str) -> ContentProgramRecord:
        program = repository.get_content_program(content_program_id)
        if program is None:
            raise CampaignOpsNotFoundError("Content Program was not found.")
        return program

    def _validate_content_access(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, program_id: str) -> Program:
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this Content Management program.")
        if not program.is_active:
            raise CampaignOpsValidationError("Archived programs cannot have Content Management changes.")
        return program

    def _non_negative_optional(self, value: Any, label: str) -> int | None:
        if value in (None, ""):
            return None
        number = int(value)
        if number < 0:
            raise CampaignOpsValidationError(f"{label} must be non-negative.")
        return number

    def _validate_content_program_payload(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, payload: dict[str, Any], before: ContentProgramRecord | None = None) -> dict[str, Any]:
        program_id = payload.get("program_id") or (before.program_id if before else None)
        if not program_id:
            raise CampaignOpsValidationError("Program is required.")
        self._validate_content_access(repository, actor, str(program_id))
        title = require_text(payload.get("content_program_title") or (before.content_program_title if before else None), "Content Program title")
        workstream_id = payload.get("workstream_id") if "workstream_id" in payload else (before.workstream_id if before else None)
        if workstream_id:
            workstream = self._require_workstream(repository, str(program_id), str(workstream_id))
            if not workstream.is_active:
                raise CampaignOpsValidationError("Inactive workstreams cannot receive active Content Management changes.")
        owner_user_id = payload.get("owner_user_id") if "owner_user_id" in payload else (before.owner_user_id if before else None)
        if owner_user_id:
            self._require_active_user(repository, str(owner_user_id), "Owner")
        monitoring_start = payload.get("monitoring_start_date") if "monitoring_start_date" in payload else (before.monitoring_start_date if before else None)
        maintenance_end = payload.get("maintenance_end_date") if "maintenance_end_date" in payload else (before.maintenance_end_date if before else None)
        if monitoring_start and maintenance_end and maintenance_end < monitoring_start:
            raise CampaignOpsValidationError("Maintenance end date cannot precede monitoring start date.")
        return {
            "program_id": str(program_id),
            "workstream_id": str(workstream_id) if workstream_id else None,
            "content_program_title": title,
            "content_status": normalize_content_status(payload.get("content_status") or (before.content_status if before else CONTENT_STATUS_NOT_STARTED)),
            "latest_update": self._clean_optional_text(payload.get("latest_update") if "latest_update" in payload else (before.latest_update if before else None)),
            "waiting_on": self._clean_optional_text(payload.get("waiting_on") if "waiting_on" in payload else (before.waiting_on if before else None)),
            "owner_user_id": str(owner_user_id) if owner_user_id else None,
            "total_sku_count": self._non_negative_optional(payload.get("total_sku_count") if "total_sku_count" in payload else (before.total_sku_count if before else None), "Total SKU count"),
            "default_graphics_per_sku": self._non_negative_optional(payload.get("default_graphics_per_sku") if "default_graphics_per_sku" in payload else (before.default_graphics_per_sku if before else None), "Graphics per SKU"),
            "monitoring_start_date": monitoring_start,
            "maintenance_end_date": maintenance_end,
            "reporting_cadence": self._clean_optional_text(payload.get("reporting_cadence") if "reporting_cadence" in payload else (before.reporting_cadence if before else None)),
            "is_invoiced": bool(payload.get("is_invoiced") if "is_invoiced" in payload else (before.is_invoiced if before else False)),
            "invoice_status": self._clean_optional_text(payload.get("invoice_status") if "invoice_status" in payload else (before.invoice_status if before else None)),
        }

    def create_content_program(self, actor: CampaignOpsUser | None, **kwargs: Any) -> ContentProgramRecord:
        def operation(repository: CampaignOpsRepository) -> ContentProgramRecord:
            payload = self._validate_content_program_payload(repository, actor, kwargs)
            if repository.get_active_content_program_by_title(payload["program_id"], payload["content_program_title"]):
                raise CampaignOpsValidationError("An active Content Program with this title already exists for this shared program.")
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in CONTENT_RESOURCE_TYPES and url:
                    self._validate_resource_url(str(url))
            workstream_id = payload.get("workstream_id")
            if not workstream_id:
                existing = next((w for w in repository.list_all_workstreams_by_program(payload["program_id"]) if w.workstream_type == WorkstreamType.ECOMMERCE.value and w.is_active), None)
                workstream_id = existing.id if existing else repository.create_workstream(payload["program_id"], WorkstreamType.ECOMMERCE.value, actor_user_id=actor.id if actor else None, owner_user_id=payload.get("owner_user_id")).id
            payload["workstream_id"] = workstream_id
            groups = kwargs.get("initial_sku_groups") or []
            group_total = sum(int(g.get("expected_sku_count") or 0) for g in groups if isinstance(g, dict))
            if payload.get("total_sku_count") is not None and group_total > payload["total_sku_count"]:
                raise CampaignOpsValidationError("Initial SKU group counts cannot exceed total SKU count.")
            seen_groups: set[str] = set()
            content = repository.create_content_program(actor_user_id=actor.id if actor else None, **payload)
            for index, group in enumerate(groups):
                group_name = require_text(str(group.get("group_name") if isinstance(group, dict) else group), "SKU group name")
                if group_name.lower() in seen_groups:
                    raise CampaignOpsValidationError("Duplicate active SKU groups are not allowed.")
                seen_groups.add(group_name.lower())
                data = dict(group) if isinstance(group, dict) else {}
                data.pop("group_name", None)
                data["sort_order"] = data.get("sort_order", index)
                repository.create_content_sku_group(content.id, group_name, **data)
                repository.append_event(event_type="content_sku_group_created", entity_type="content_sku_group", entity_id=content.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added SKU group {group_name}.")
            for resource_type, url in (kwargs.get("initial_resources") or {}).items():
                if resource_type in CONTENT_RESOURCE_TYPES:
                    resource = repository.create_resource(program_id=content.program_id, workstream_id=content.workstream_id, resource_type=resource_type, title=resource_type, url=self._validate_resource_url(url) if url else None, actor_user_id=actor.id if actor else None)
                    repository.append_event(event_type="resource_created", entity_type="resource", entity_id=resource.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added {resource.resource_type} for Content Program {content.content_program_title}.")
            repository.append_event(event_type="content_program_created", entity_type="content_program", entity_id=content.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, new_value_json={"content_program_title": content.content_program_title}, message=f"{self._content_actor_label(actor)} created Content Program {content.content_program_title}.")
            return content

        return self._transaction(operation)

    def update_content_program(self, actor: CampaignOpsUser | None, content_program_id: str, **kwargs: Any) -> ContentProgramRecord:
        def operation(repository: CampaignOpsRepository) -> ContentProgramRecord:
            before = self._require_content_program(repository, content_program_id)
            payload = self._validate_content_program_payload(repository, actor, kwargs, before)
            duplicate = repository.get_active_content_program_by_title(payload["program_id"], payload["content_program_title"])
            if duplicate and duplicate.id != content_program_id:
                raise CampaignOpsValidationError("An active Content Program with this title already exists for this shared program.")
            changes = {f: v for f, v in payload.items() if f != "program_id" and getattr(before, f) != v}
            if not changes:
                return before
            merged = {f: getattr(before, f) for f in payload if f != "program_id"}
            merged.update(changes)
            updated = repository.update_content_program(content_program_id, **merged)
            for field, value in changes.items():
                repository.append_event(event_type=f"content_program_{field}_changed", entity_type="content_program", entity_id=content_program_id, program_id=updated.program_id, workstream_id=updated.workstream_id, actor_user_id=actor.id if actor else None, old_value_json={field: self._activity_value(getattr(before, field))}, new_value_json={field: self._activity_value(value)}, message=f"{self._content_actor_label(actor)} changed Content {field.replace('_', ' ')} from {getattr(before, field) or '-'} to {value or '-'}.")
            return updated

        return self._transaction(operation)

    def list_content_programs(self, actor: CampaignOpsUser | None, include_inactive: bool = False) -> list[ContentPortfolioRow]:
        repository = self.repository or CampaignOpsRepository()
        rows = repository.list_content_programs(include_inactive=include_inactive)
        if can_access_admin(actor):
            return rows
        return [row for row in rows if can_view_program(actor, self._require_program(repository, row.program_id), repository.list_assignments_by_program(row.program_id))]

    def get_content_baseline_board_data(self, actor: CampaignOpsUser | None, programs: list[ContentPortfolioRow]) -> dict[str, Any]:
        repository = self.repository or CampaignOpsRepository()
        visible = {program.id: program for program in programs}
        content_program_ids = list(visible)
        program_ids = list({program.program_id for program in programs})
        resources_by_program = repository.list_resources_for_programs(program_ids)
        return {
            "groups": repository.list_content_sku_groups_for_programs(content_program_ids),
            "deliverables": repository.list_content_deliverables_for_programs(content_program_ids),
            "submissions": repository.list_content_submissions_for_programs(content_program_ids),
            "monitoring": repository.list_content_monitoring_updates_for_programs(content_program_ids),
            "milestones": repository.list_content_milestone_rows_for_programs(content_program_ids),
            "resources": {
                content_id: resources_by_program.get(program.program_id, [])
                for content_id, program in visible.items()
            },
        }

    def get_content_program_detail(self, actor: CampaignOpsUser | None, content_program_id: str) -> ContentProgramDetail:
        repository = self.repository or CampaignOpsRepository()
        detail = repository.get_content_program_detail(content_program_id)
        if detail is None:
            raise CampaignOpsNotFoundError("Content Program was not found.")
        if not can_view_program(actor, self._require_program(repository, detail.program_id), repository.list_assignments_by_program(detail.program_id)):
            raise CampaignOpsPermissionError("You do not have access to this Content Program.")
        return detail

    def deactivate_content_program(self, actor: CampaignOpsUser | None, content_program_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            content = self._require_content_program(repository, content_program_id)
            self._validate_content_access(repository, actor, content.program_id)
            repository.deactivate_content_program(content_program_id)
            repository.append_event(event_type="content_program_deactivated", entity_type="content_program", entity_id=content_program_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} deactivated Content Program {content.content_program_title}.")

        self._transaction(operation)

    def reactivate_content_program(self, actor: CampaignOpsUser | None, content_program_id: str) -> ContentProgramRecord:
        def operation(repository: CampaignOpsRepository) -> ContentProgramRecord:
            content = self._require_content_program(repository, content_program_id)
            self._validate_content_access(repository, actor, content.program_id)
            updated = repository.reactivate_content_program(content_program_id)
            repository.append_event(event_type="content_program_reactivated", entity_type="content_program", entity_id=content_program_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} reactivated Content Program {content.content_program_title}.")
            return updated

        return self._transaction(operation)

    def _content_child_context(self, repository: CampaignOpsRepository, actor: CampaignOpsUser | None, content_program_id: str) -> ContentProgramRecord:
        content = self._require_content_program(repository, content_program_id)
        self._validate_content_access(repository, actor, content.program_id)
        return content

    def _validate_content_group(self, repository: CampaignOpsRepository, content_program_id: str, group_id: str | None) -> None:
        if group_id and not any(g.id == group_id for g in repository.list_content_sku_groups(content_program_id, include_inactive=True)):
            raise CampaignOpsValidationError("Selected SKU group must belong to this Content Program.")

    def _validate_content_sku_link(self, repository: CampaignOpsRepository, content_program_id: str, sku_id: str | None) -> None:
        if sku_id and not any(s.id == sku_id for s in repository.list_content_skus(content_program_id, include_inactive=True)):
            raise CampaignOpsValidationError("Selected SKU must belong to this Content Program.")

    def create_content_sku_group(self, actor: CampaignOpsUser | None, content_program_id: str, group_name: str, **kwargs: Any) -> ContentSkuGroupRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSkuGroupRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            if any(g.group_name.lower() == group_name.strip().lower() for g in repository.list_content_sku_groups(content_program_id)):
                raise CampaignOpsValidationError("Duplicate active SKU groups are not allowed.")
            expected = self._non_negative_optional(kwargs.get("expected_sku_count"), "Expected SKU count")
            graphics = self._non_negative_optional(kwargs.get("graphics_per_sku"), "Graphics per SKU")
            group = repository.create_content_sku_group(content_program_id, group_name, brand_name=self._clean_optional_text(kwargs.get("brand_name")), expected_sku_count=expected, graphics_per_sku=graphics, status=self._clean_optional_text(kwargs.get("status")), latest_update=self._clean_optional_text(kwargs.get("latest_update")), waiting_on=self._clean_optional_text(kwargs.get("waiting_on")), sort_order=int(kwargs.get("sort_order") or 0))
            repository.append_event(event_type="content_sku_group_created", entity_type="content_sku_group", entity_id=group.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added SKU group {group.group_name}.")
            return group

        return self._transaction(operation)

    def list_content_sku_groups(self, actor: CampaignOpsUser | None, content_program_id: str, include_inactive: bool = False) -> list[ContentSkuGroupRecord]:
        self.get_content_program_detail(actor, content_program_id)
        return (self.repository or CampaignOpsRepository()).list_content_sku_groups(content_program_id, include_inactive=include_inactive)

    def update_content_sku_group(self, actor: CampaignOpsUser | None, content_program_id: str, group_id: str, **kwargs: Any) -> ContentSkuGroupRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSkuGroupRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            before = next((g for g in repository.list_content_sku_groups(content_program_id, include_inactive=True) if g.id == group_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("SKU group was not found.")
            group_name = require_text(kwargs.get("group_name") or before.group_name, "SKU group")
            if any(g.id != group_id and g.group_name.lower() == group_name.lower() for g in repository.list_content_sku_groups(content_program_id)):
                raise CampaignOpsValidationError("Duplicate active SKU groups are not allowed.")
            payload = {"group_name": group_name, "brand_name": self._clean_optional_text(kwargs.get("brand_name") if "brand_name" in kwargs else before.brand_name), "expected_sku_count": self._non_negative_optional(kwargs.get("expected_sku_count") if "expected_sku_count" in kwargs else before.expected_sku_count, "Expected SKU count"), "graphics_per_sku": self._non_negative_optional(kwargs.get("graphics_per_sku") if "graphics_per_sku" in kwargs else before.graphics_per_sku, "Graphics per SKU"), "status": self._clean_optional_text(kwargs.get("status") if "status" in kwargs else before.status), "latest_update": self._clean_optional_text(kwargs.get("latest_update") if "latest_update" in kwargs else before.latest_update), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else before.waiting_on), "sort_order": int(kwargs.get("sort_order") if "sort_order" in kwargs else before.sort_order)}
            if not any(getattr(before, f) != v for f, v in payload.items()):
                return before
            updated = repository.update_content_sku_group(group_id, **payload)
            repository.append_event(event_type="content_sku_group_updated", entity_type="content_sku_group", entity_id=group_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} updated SKU group {updated.group_name}.")
            return updated

        return self._transaction(operation)

    def reorder_content_sku_groups(self, actor: CampaignOpsUser | None, content_program_id: str, ordered_ids: list[str]) -> list[ContentSkuGroupRecord]:
        return [self.update_content_sku_group(actor, content_program_id, group_id, sort_order=index) for index, group_id in enumerate(ordered_ids)]

    def deactivate_content_sku_group(self, actor: CampaignOpsUser | None, content_program_id: str, group_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            content = self._content_child_context(repository, actor, content_program_id)
            repository.deactivate_content_sku_group(group_id)
            repository.append_event(event_type="content_sku_group_deactivated", entity_type="content_sku_group", entity_id=group_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} deactivated a SKU group.")
        self._transaction(operation)

    def reactivate_content_sku_group(self, actor: CampaignOpsUser | None, content_program_id: str, group_id: str) -> ContentSkuGroupRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSkuGroupRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            group = repository.reactivate_content_sku_group(group_id)
            repository.append_event(event_type="content_sku_group_reactivated", entity_type="content_sku_group", entity_id=group_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} reactivated SKU group {group.group_name}.")
            return group
        return self._transaction(operation)

    def _sku_payload(self, repository: CampaignOpsRepository, content_program_id: str, kwargs: dict[str, Any], before: ContentSkuRecord | None = None) -> dict[str, Any]:
        group_id = kwargs.get("sku_group_id") if "sku_group_id" in kwargs else (before.sku_group_id if before else None)
        self._validate_content_group(repository, content_program_id, str(group_id) if group_id else None)
        live_url = kwargs.get("live_url") if "live_url" in kwargs else (before.live_url if before else None)
        return {"sku_group_id": str(group_id) if group_id else None, "sku_code": self._clean_optional_text(kwargs.get("sku_code") if "sku_code" in kwargs else (before.sku_code if before else None)), "product_name": require_text(kwargs.get("product_name") or (before.product_name if before else None), "Product name"), "retailer_sku": self._clean_optional_text(kwargs.get("retailer_sku") if "retailer_sku" in kwargs else (before.retailer_sku if before else None)), "upc": self._clean_optional_text(kwargs.get("upc") if "upc" in kwargs else (before.upc if before else None)), "variant": self._clean_optional_text(kwargs.get("variant") if "variant" in kwargs else (before.variant if before else None)), "content_status": normalize_content_status(kwargs.get("content_status") or (before.content_status if before else CONTENT_STATUS_NOT_STARTED)), "copy_status": normalize_optional_status(kwargs.get("copy_status") if "copy_status" in kwargs else (before.copy_status if before else None), COPY_STATUSES, "Copy status"), "attribute_status": self._clean_optional_text(kwargs.get("attribute_status") if "attribute_status" in kwargs else (before.attribute_status if before else None)), "graphics_status": normalize_optional_status(kwargs.get("graphics_status") if "graphics_status" in kwargs else (before.graphics_status if before else None), GRAPHICS_STATUSES, "Graphics status"), "submission_status": normalize_optional_status(kwargs.get("submission_status") if "submission_status" in kwargs else (before.submission_status if before else None), SUBMISSION_STATUSES, "Submission status"), "publication_status": normalize_optional_status(kwargs.get("publication_status") if "publication_status" in kwargs else (before.publication_status if before else None), PUBLICATION_STATUSES, "Publication status"), "live_url": self._validate_resource_url(live_url) if live_url else None, "last_checked_at": kwargs.get("last_checked_at") if "last_checked_at" in kwargs else (before.last_checked_at if before else None), "issue_status": self._clean_optional_text(kwargs.get("issue_status") if "issue_status" in kwargs else (before.issue_status if before else None)), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "maintenance_required": bool(kwargs.get("maintenance_required") if "maintenance_required" in kwargs else (before.maintenance_required if before else False))}

    def create_content_sku(self, actor: CampaignOpsUser | None, content_program_id: str, **kwargs: Any) -> ContentSkuRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSkuRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            payload = self._sku_payload(repository, content_program_id, kwargs)
            if payload["sku_code"] and any(s.sku_code == payload["sku_code"] and s.is_active for s in repository.list_content_skus(content_program_id, include_inactive=True)):
                raise CampaignOpsValidationError("Duplicate active SKU code is not allowed in one Content Program.")
            sku = repository.create_content_sku(content_program_id, **payload)
            repository.append_event(event_type="content_sku_created", entity_type="content_sku", entity_id=sku.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added SKU {sku.product_name}.")
            return sku
        return self._transaction(operation)

    def list_content_skus(self, actor: CampaignOpsUser | None, content_program_id: str, include_inactive: bool = False) -> list[ContentSkuRecord]:
        self.get_content_program_detail(actor, content_program_id)
        return (self.repository or CampaignOpsRepository()).list_content_skus(content_program_id, include_inactive=include_inactive)

    def update_content_sku(self, actor: CampaignOpsUser | None, content_program_id: str, sku_id: str, **kwargs: Any) -> ContentSkuRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSkuRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            before = repository.get_content_sku(sku_id)
            if before is None or before.content_program_id != content_program_id:
                raise CampaignOpsNotFoundError("SKU was not found.")
            payload = self._sku_payload(repository, content_program_id, kwargs, before)
            if payload["sku_code"] and any(s.id != sku_id and s.sku_code == payload["sku_code"] and s.is_active for s in repository.list_content_skus(content_program_id, include_inactive=True)):
                raise CampaignOpsValidationError("Duplicate active SKU code is not allowed in one Content Program.")
            if not any(getattr(before, f) != v for f, v in payload.items()):
                return before
            updated = repository.update_content_sku(sku_id, **payload)
            repository.append_event(event_type="content_sku_updated", entity_type="content_sku", entity_id=sku_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} updated SKU {updated.product_name}.")
            return updated
        return self._transaction(operation)

    def mark_content_sku_live(self, actor: CampaignOpsUser | None, content_program_id: str, sku_id: str, live_url: str | None = None) -> ContentSkuRecord:
        return self.update_content_sku(actor, content_program_id, sku_id, publication_status="live", content_status=CONTENT_STATUS_LIVE, live_url=live_url, last_checked_at=datetime.now(UTC))

    def mark_content_sku_issue_found(self, actor: CampaignOpsUser | None, content_program_id: str, sku_id: str, issue_status: str = "issue_found") -> ContentSkuRecord:
        return self.update_content_sku(actor, content_program_id, sku_id, publication_status="issue_found", issue_status=issue_status, last_checked_at=datetime.now(UTC))

    def clear_content_sku_issue(self, actor: CampaignOpsUser | None, content_program_id: str, sku_id: str) -> ContentSkuRecord:
        return self.update_content_sku(actor, content_program_id, sku_id, issue_status=None, publication_status="monitoring", last_checked_at=datetime.now(UTC))

    def deactivate_content_sku(self, actor: CampaignOpsUser | None, content_program_id: str, sku_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            content = self._content_child_context(repository, actor, content_program_id)
            repository.deactivate_content_sku(sku_id)
            repository.append_event(event_type="content_sku_deactivated", entity_type="content_sku", entity_id=sku_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} deactivated a SKU.")
        self._transaction(operation)

    def reactivate_content_sku(self, actor: CampaignOpsUser | None, content_program_id: str, sku_id: str) -> ContentSkuRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSkuRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            sku = repository.reactivate_content_sku(sku_id)
            repository.append_event(event_type="content_sku_reactivated", entity_type="content_sku", entity_id=sku_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} reactivated SKU {sku.product_name}.")
            return sku
        return self._transaction(operation)

    def _validate_content_quantities(self, required: Any, completed: Any) -> tuple[int | None, int | None]:
        req = self._non_negative_optional(required, "Required quantity")
        comp = self._non_negative_optional(completed, "Completed quantity")
        if req is not None and comp is not None and comp > req:
            raise CampaignOpsValidationError("Completed quantity cannot exceed required quantity in this baseline.")
        return req, comp

    def _deliverable_payload(self, repository: CampaignOpsRepository, content_program_id: str, kwargs: dict[str, Any], before: ContentDeliverableRecord | None = None) -> dict[str, Any]:
        group_id = kwargs.get("sku_group_id") if "sku_group_id" in kwargs else (before.sku_group_id if before else None)
        sku_id = kwargs.get("sku_id") if "sku_id" in kwargs else (before.sku_id if before else None)
        self._validate_content_group(repository, content_program_id, str(group_id) if group_id else None)
        self._validate_content_sku_link(repository, content_program_id, str(sku_id) if sku_id else None)
        req, comp = self._validate_content_quantities(kwargs.get("required_quantity") if "required_quantity" in kwargs else (before.required_quantity if before else None), kwargs.get("completed_quantity") if "completed_quantity" in kwargs else (before.completed_quantity if before else None))
        return {"sku_group_id": str(group_id) if group_id else None, "sku_id": str(sku_id) if sku_id else None, "deliverable_name": require_text(kwargs.get("deliverable_name") or (before.deliverable_name if before else None), "Deliverable name"), "deliverable_type": self._clean_optional_text(kwargs.get("deliverable_type") if "deliverable_type" in kwargs else (before.deliverable_type if before else None)), "status": self._clean_optional_text(kwargs.get("status") if "status" in kwargs else (before.status if before else None)), "approval_status": self._clean_optional_text(kwargs.get("approval_status") if "approval_status" in kwargs else (before.approval_status if before else None)), "due_date": kwargs.get("due_date") if "due_date" in kwargs else (before.due_date if before else None), "delivered_date": kwargs.get("delivered_date") if "delivered_date" in kwargs else (before.delivered_date if before else None), "approved_date": kwargs.get("approved_date") if "approved_date" in kwargs else (before.approved_date if before else None), "required_quantity": req, "completed_quantity": comp, "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None)), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else (before.notes if before else None))}

    def create_content_deliverable(self, actor: CampaignOpsUser | None, content_program_id: str, **kwargs: Any) -> ContentDeliverableRecord:
        def operation(repository: CampaignOpsRepository) -> ContentDeliverableRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            deliverable = repository.create_content_deliverable(content_program_id, **self._deliverable_payload(repository, content_program_id, kwargs))
            repository.append_event(event_type="content_deliverable_created", entity_type="content_deliverable", entity_id=deliverable.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added deliverable {deliverable.deliverable_name}.")
            return deliverable
        return self._transaction(operation)

    def list_content_deliverables(self, actor: CampaignOpsUser | None, content_program_id: str, include_inactive: bool = False) -> list[ContentDeliverableRecord]:
        self.get_content_program_detail(actor, content_program_id)
        return (self.repository or CampaignOpsRepository()).list_content_deliverables(content_program_id, include_inactive=include_inactive)

    def update_content_deliverable(self, actor: CampaignOpsUser | None, content_program_id: str, deliverable_id: str, **kwargs: Any) -> ContentDeliverableRecord:
        def operation(repository: CampaignOpsRepository) -> ContentDeliverableRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            before = next((d for d in repository.list_content_deliverables(content_program_id, include_inactive=True) if d.id == deliverable_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Deliverable was not found.")
            payload = self._deliverable_payload(repository, content_program_id, kwargs, before)
            if not any(getattr(before, f) != v for f, v in payload.items()):
                return before
            updated = repository.update_content_deliverable(deliverable_id, **payload)
            repository.append_event(event_type="content_deliverable_updated", entity_type="content_deliverable", entity_id=deliverable_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} updated deliverable {updated.deliverable_name}.")
            return updated
        return self._transaction(operation)

    def mark_content_deliverable_delivered(self, actor: CampaignOpsUser | None, content_program_id: str, deliverable_id: str, delivered_date: date | None = None) -> ContentDeliverableRecord:
        return self.update_content_deliverable(actor, content_program_id, deliverable_id, status="delivered", delivered_date=delivered_date or date.today())

    def mark_content_deliverable_approved(self, actor: CampaignOpsUser | None, content_program_id: str, deliverable_id: str, approved_date: date | None = None) -> ContentDeliverableRecord:
        return self.update_content_deliverable(actor, content_program_id, deliverable_id, status="approved", approval_status="approved", approved_date=approved_date or date.today())

    def reopen_content_deliverable(self, actor: CampaignOpsUser | None, content_program_id: str, deliverable_id: str) -> ContentDeliverableRecord:
        return self.update_content_deliverable(actor, content_program_id, deliverable_id, status="in_progress", approval_status=None, delivered_date=None, approved_date=None)

    def deactivate_content_deliverable(self, actor: CampaignOpsUser | None, content_program_id: str, deliverable_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            content = self._content_child_context(repository, actor, content_program_id)
            repository.deactivate_content_deliverable(deliverable_id)
            repository.append_event(event_type="content_deliverable_deactivated", entity_type="content_deliverable", entity_id=deliverable_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} deactivated a deliverable.")
        self._transaction(operation)

    def reactivate_content_deliverable(self, actor: CampaignOpsUser | None, content_program_id: str, deliverable_id: str) -> ContentDeliverableRecord:
        def operation(repository: CampaignOpsRepository) -> ContentDeliverableRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            deliverable = repository.reactivate_content_deliverable(deliverable_id)
            repository.append_event(event_type="content_deliverable_reactivated", entity_type="content_deliverable", entity_id=deliverable_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} reactivated deliverable {deliverable.deliverable_name}.")
            return deliverable
        return self._transaction(operation)

    def _submission_payload(self, repository: CampaignOpsRepository, content_program_id: str, kwargs: dict[str, Any], before: ContentSubmissionRecord | None = None) -> dict[str, Any]:
        group_id = kwargs.get("sku_group_id") if "sku_group_id" in kwargs else (before.sku_group_id if before else None)
        sku_id = kwargs.get("sku_id") if "sku_id" in kwargs else (before.sku_id if before else None)
        self._validate_content_group(repository, content_program_id, str(group_id) if group_id else None)
        self._validate_content_sku_link(repository, content_program_id, str(sku_id) if sku_id else None)
        live_url = kwargs.get("live_url") if "live_url" in kwargs else (before.live_url if before else None)
        return {"sku_group_id": str(group_id) if group_id else None, "sku_id": str(sku_id) if sku_id else None, "retailer_or_platform": self._clean_optional_text(kwargs.get("retailer_or_platform") if "retailer_or_platform" in kwargs else (before.retailer_or_platform if before else None)), "submission_type": self._clean_optional_text(kwargs.get("submission_type") if "submission_type" in kwargs else (before.submission_type if before else None)), "status": self._clean_optional_text(kwargs.get("status") if "status" in kwargs else (before.status if before else None)), "submitted_date": kwargs.get("submitted_date") if "submitted_date" in kwargs else (before.submitted_date if before else None), "approved_date": kwargs.get("approved_date") if "approved_date" in kwargs else (before.approved_date if before else None), "published_date": kwargs.get("published_date") if "published_date" in kwargs else (before.published_date if before else None), "expected_live_date": kwargs.get("expected_live_date") if "expected_live_date" in kwargs else (before.expected_live_date if before else None), "live_url": self._validate_resource_url(live_url) if live_url else None, "issue_text": self._clean_optional_text(kwargs.get("issue_text") if "issue_text" in kwargs else (before.issue_text if before else None)), "waiting_on": self._clean_optional_text(kwargs.get("waiting_on") if "waiting_on" in kwargs else (before.waiting_on if before else None))}

    def create_content_submission(self, actor: CampaignOpsUser | None, content_program_id: str, **kwargs: Any) -> ContentSubmissionRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSubmissionRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            sub = repository.create_content_submission(content_program_id, **self._submission_payload(repository, content_program_id, kwargs))
            repository.append_event(event_type="content_submission_created", entity_type="content_submission", entity_id=sub.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added a content submission.")
            return sub
        return self._transaction(operation)

    def list_content_submissions(self, actor: CampaignOpsUser | None, content_program_id: str, include_inactive: bool = False) -> list[ContentSubmissionRecord]:
        self.get_content_program_detail(actor, content_program_id)
        return (self.repository or CampaignOpsRepository()).list_content_submissions(content_program_id, include_inactive=include_inactive)

    def update_content_submission(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str, **kwargs: Any) -> ContentSubmissionRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSubmissionRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            before = next((s for s in repository.list_content_submissions(content_program_id, include_inactive=True) if s.id == submission_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Submission was not found.")
            payload = self._submission_payload(repository, content_program_id, kwargs, before)
            if not any(getattr(before, f) != v for f, v in payload.items()):
                return before
            updated = repository.update_content_submission(submission_id, **payload)
            repository.append_event(event_type="content_submission_updated", entity_type="content_submission", entity_id=submission_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} updated a content submission.")
            return updated
        return self._transaction(operation)

    def mark_content_submission_submitted(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str, submitted_date: date | None = None) -> ContentSubmissionRecord:
        return self.update_content_submission(actor, content_program_id, submission_id, status="submitted", submitted_date=submitted_date or date.today())

    def mark_content_submission_approved(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str, approved_date: date | None = None) -> ContentSubmissionRecord:
        return self.update_content_submission(actor, content_program_id, submission_id, status="approved", approved_date=approved_date or date.today())

    def mark_content_submission_published(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str, published_date: date | None = None, live_url: str | None = None) -> ContentSubmissionRecord:
        return self.update_content_submission(actor, content_program_id, submission_id, status="live", published_date=published_date or date.today(), live_url=live_url)

    def mark_content_submission_issue(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str, issue_text: str) -> ContentSubmissionRecord:
        return self.update_content_submission(actor, content_program_id, submission_id, status="issue_found", issue_text=require_text(issue_text, "Issue"))

    def resolve_content_submission_issue(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str) -> ContentSubmissionRecord:
        return self.update_content_submission(actor, content_program_id, submission_id, status="monitoring", issue_text=None)

    def deactivate_content_submission(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            content = self._content_child_context(repository, actor, content_program_id)
            repository.deactivate_content_submission(submission_id)
            repository.append_event(event_type="content_submission_deactivated", entity_type="content_submission", entity_id=submission_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} deactivated a content submission.")
        self._transaction(operation)

    def reactivate_content_submission(self, actor: CampaignOpsUser | None, content_program_id: str, submission_id: str) -> ContentSubmissionRecord:
        def operation(repository: CampaignOpsRepository) -> ContentSubmissionRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            sub = repository.reactivate_content_submission(submission_id)
            repository.append_event(event_type="content_submission_reactivated", entity_type="content_submission", entity_id=submission_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} reactivated a content submission.")
            return sub
        return self._transaction(operation)

    def create_content_monitoring_update(self, actor: CampaignOpsUser | None, content_program_id: str, update_date: date, update_text: str, **kwargs: Any) -> ContentMonitoringUpdateRecord:
        def operation(repository: CampaignOpsRepository) -> ContentMonitoringUpdateRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            self._validate_content_group(repository, content_program_id, kwargs.get("sku_group_id"))
            self._validate_content_sku_link(repository, content_program_id, kwargs.get("sku_id"))
            live_reviews = self._non_negative_optional(kwargs.get("live_review_count"), "Live review count")
            update = repository.create_content_monitoring_update(content_program_id, update_date, update_text, actor_user_id=actor.id if actor else None, sku_group_id=kwargs.get("sku_group_id"), sku_id=kwargs.get("sku_id"), update_type=self._clean_optional_text(kwargs.get("update_type")), live_review_count=live_reviews, publication_state=self._clean_optional_text(kwargs.get("publication_state")))
            repository.append_event(event_type="content_monitoring_update_created", entity_type="content_monitoring_update", entity_id=update.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added monitoring update {update.update_text}.")
            return update
        return self._transaction(operation)

    def list_content_monitoring_updates(self, actor: CampaignOpsUser | None, content_program_id: str, include_inactive: bool = False) -> list[ContentMonitoringUpdateRecord]:
        self.get_content_program_detail(actor, content_program_id)
        return (self.repository or CampaignOpsRepository()).list_content_monitoring_updates(content_program_id, include_inactive=include_inactive)

    def update_content_monitoring_update(self, actor: CampaignOpsUser | None, content_program_id: str, update_id: str, **kwargs: Any) -> ContentMonitoringUpdateRecord:
        def operation(repository: CampaignOpsRepository) -> ContentMonitoringUpdateRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            before = next((u for u in repository.list_content_monitoring_updates(content_program_id, include_inactive=True) if u.id == update_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Monitoring update was not found.")
            self._validate_content_group(repository, content_program_id, kwargs.get("sku_group_id") if "sku_group_id" in kwargs else before.sku_group_id)
            self._validate_content_sku_link(repository, content_program_id, kwargs.get("sku_id") if "sku_id" in kwargs else before.sku_id)
            payload = {"sku_group_id": kwargs.get("sku_group_id") if "sku_group_id" in kwargs else before.sku_group_id, "sku_id": kwargs.get("sku_id") if "sku_id" in kwargs else before.sku_id, "update_date": kwargs.get("update_date") if "update_date" in kwargs else before.update_date, "update_type": self._clean_optional_text(kwargs.get("update_type") if "update_type" in kwargs else before.update_type), "update_text": require_text(kwargs.get("update_text") or before.update_text, "Monitoring update"), "live_review_count": self._non_negative_optional(kwargs.get("live_review_count") if "live_review_count" in kwargs else before.live_review_count, "Live review count"), "publication_state": self._clean_optional_text(kwargs.get("publication_state") if "publication_state" in kwargs else before.publication_state)}
            updated = repository.update_content_monitoring_update(update_id, **payload)
            repository.append_event(event_type="content_monitoring_update_updated", entity_type="content_monitoring_update", entity_id=update_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} updated monitoring update {updated.update_text}.")
            return updated
        return self._transaction(operation)

    def deactivate_content_monitoring_update(self, actor: CampaignOpsUser | None, content_program_id: str, update_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            content = self._content_child_context(repository, actor, content_program_id)
            repository.deactivate_content_monitoring_update(update_id)
            repository.append_event(event_type="content_monitoring_update_deactivated", entity_type="content_monitoring_update", entity_id=update_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} deactivated a monitoring update.")
        self._transaction(operation)

    def reactivate_content_monitoring_update(self, actor: CampaignOpsUser | None, content_program_id: str, update_id: str) -> ContentMonitoringUpdateRecord:
        def operation(repository: CampaignOpsRepository) -> ContentMonitoringUpdateRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            update = repository.reactivate_content_monitoring_update(update_id)
            repository.append_event(event_type="content_monitoring_update_reactivated", entity_type="content_monitoring_update", entity_id=update_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} reactivated monitoring update {update.update_text}.")
            return update
        return self._transaction(operation)

    def create_content_invoice_checkpoint(self, actor: CampaignOpsUser | None, content_program_id: str, checkpoint_name: str, **kwargs: Any) -> ContentInvoiceCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> ContentInvoiceCheckpointRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            amount = self._non_negative_number(kwargs.get("amount"), "Invoice amount")
            checkpoint = repository.create_content_invoice_checkpoint(content_program_id, checkpoint_name, invoice_date=kwargs.get("invoice_date"), due_date=kwargs.get("due_date"), status=self._clean_optional_text(kwargs.get("status")), amount=amount, notes=self._clean_optional_text(kwargs.get("notes")))
            repository.append_event(event_type="content_invoice_checkpoint_created", entity_type="content_invoice_checkpoint", entity_id=checkpoint.id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} added invoice checkpoint {checkpoint.checkpoint_name}.")
            return checkpoint
        return self._transaction(operation)

    def list_content_invoice_checkpoints(self, actor: CampaignOpsUser | None, content_program_id: str, include_inactive: bool = False) -> list[ContentInvoiceCheckpointRecord]:
        self.get_content_program_detail(actor, content_program_id)
        return (self.repository or CampaignOpsRepository()).list_content_invoice_checkpoints(content_program_id, include_inactive=include_inactive)

    def update_content_invoice_checkpoint(self, actor: CampaignOpsUser | None, content_program_id: str, checkpoint_id: str, **kwargs: Any) -> ContentInvoiceCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> ContentInvoiceCheckpointRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            before = next((c for c in repository.list_content_invoice_checkpoints(content_program_id, include_inactive=True) if c.id == checkpoint_id), None)
            if before is None:
                raise CampaignOpsNotFoundError("Invoice checkpoint was not found.")
            payload = {"checkpoint_name": require_text(kwargs.get("checkpoint_name") or before.checkpoint_name, "Checkpoint name"), "invoice_date": kwargs.get("invoice_date") if "invoice_date" in kwargs else before.invoice_date, "due_date": kwargs.get("due_date") if "due_date" in kwargs else before.due_date, "status": self._clean_optional_text(kwargs.get("status") if "status" in kwargs else before.status), "amount": self._non_negative_number(kwargs.get("amount") if "amount" in kwargs else before.amount, "Invoice amount"), "notes": self._clean_optional_text(kwargs.get("notes") if "notes" in kwargs else before.notes)}
            updated = repository.update_content_invoice_checkpoint(checkpoint_id, **payload)
            repository.append_event(event_type="content_invoice_checkpoint_updated", entity_type="content_invoice_checkpoint", entity_id=checkpoint_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} updated invoice checkpoint {updated.checkpoint_name}.")
            return updated
        return self._transaction(operation)

    def mark_content_invoice_sent(self, actor: CampaignOpsUser | None, content_program_id: str, checkpoint_id: str, invoice_date: date | None = None) -> ContentInvoiceCheckpointRecord:
        return self.update_content_invoice_checkpoint(actor, content_program_id, checkpoint_id, status="sent", invoice_date=invoice_date or date.today())

    def mark_content_invoice_paid(self, actor: CampaignOpsUser | None, content_program_id: str, checkpoint_id: str) -> ContentInvoiceCheckpointRecord:
        return self.update_content_invoice_checkpoint(actor, content_program_id, checkpoint_id, status="paid")

    def deactivate_content_invoice_checkpoint(self, actor: CampaignOpsUser | None, content_program_id: str, checkpoint_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            content = self._content_child_context(repository, actor, content_program_id)
            repository.deactivate_content_invoice_checkpoint(checkpoint_id)
            repository.append_event(event_type="content_invoice_checkpoint_deactivated", entity_type="content_invoice_checkpoint", entity_id=checkpoint_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} deactivated an invoice checkpoint.")
        self._transaction(operation)

    def reactivate_content_invoice_checkpoint(self, actor: CampaignOpsUser | None, content_program_id: str, checkpoint_id: str) -> ContentInvoiceCheckpointRecord:
        def operation(repository: CampaignOpsRepository) -> ContentInvoiceCheckpointRecord:
            content = self._content_child_context(repository, actor, content_program_id)
            checkpoint = repository.reactivate_content_invoice_checkpoint(checkpoint_id)
            repository.append_event(event_type="content_invoice_checkpoint_reactivated", entity_type="content_invoice_checkpoint", entity_id=checkpoint_id, program_id=content.program_id, workstream_id=content.workstream_id, actor_user_id=actor.id if actor else None, message=f"{self._content_actor_label(actor)} reactivated invoice checkpoint {checkpoint.checkpoint_name}.")
            return checkpoint
        return self._transaction(operation)

    def create_resource(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        title: str,
        resource_type: str,
        **kwargs: Any,
    ) -> Resource:
        cleaned_title = require_text(title, "Title")
        cleaned_type = self._validate_resource_type(resource_type)
        cleaned_url = self._validate_resource_url(kwargs.get("url"))

        def operation(repository: CampaignOpsRepository) -> Resource:
            program = self._require_program(repository, program_id)
            assignments = repository.list_assignments_by_program(program_id)
            temp = Resource(
                id="00000000-0000-4000-8000-000000000000",
                program_id=program_id,
                title=cleaned_title,
                resource_type=cleaned_type,
                workstream_id=kwargs.get("workstream_id"),
            )
            if not can_edit_resource(actor, program, temp, assignments):
                raise CampaignOpsPermissionError("You do not have permission to create this resource.")
            if not program.is_active:
                raise CampaignOpsValidationError("Archived programs cannot have resource changes.")
            self._validate_task_workstream(repository, program_id, kwargs.get("workstream_id"))
            resource = repository.create_resource(
                program_id=program_id,
                resource_type=cleaned_type,
                title=cleaned_title,
                actor_user_id=actor.id if actor else None,
                workstream_id=kwargs.get("workstream_id"),
                url=cleaned_url,
                notes=(kwargs.get("notes") or "").strip() or None,
                is_required=bool(kwargs.get("is_required", False)),
            )
            repository.append_event(
                event_type="resource_created",
                entity_type="resource",
                entity_id=resource.id,
                program_id=program_id,
                workstream_id=resource.workstream_id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"title": resource.title, "is_required": resource.is_required},
                message=f"{actor.display_name if actor else 'System'} added {'required ' if resource.is_required else ''}resource {resource.title}.",
            )
            return resource

        return self._transaction(operation)

    def update_resource_details(
        self,
        actor: CampaignOpsUser | None,
        resource_id: str,
        **kwargs: Any,
    ) -> Resource:
        def operation(repository: CampaignOpsRepository) -> Resource:
            before = self._require_resource(repository, resource_id)
            program = self._require_program(repository, before.program_id)
            assignments = repository.list_assignments_by_program(before.program_id)
            if not can_edit_resource(actor, program, before, assignments):
                raise CampaignOpsPermissionError("You do not have permission to edit this resource.")
            if not program.is_active:
                raise CampaignOpsValidationError("Archived programs cannot have resource changes.")
            if "title" in kwargs:
                kwargs["title"] = require_text(kwargs["title"], "Title")
            if "resource_type" in kwargs:
                kwargs["resource_type"] = self._validate_resource_type(kwargs["resource_type"])
            if "workstream_id" in kwargs:
                self._validate_task_workstream(repository, before.program_id, kwargs.get("workstream_id"))
            if "url" in kwargs:
                kwargs["url"] = self._validate_resource_url(kwargs.get("url"))
            if "notes" in kwargs:
                kwargs["notes"] = (kwargs.get("notes") or "").strip() or None
            editable = {"title", "resource_type", "workstream_id", "url", "notes", "is_required"}
            changes = {
                field: value
                for field, value in kwargs.items()
                if field in editable and getattr(before, field) != value
            }
            if not changes:
                return before
            merged = {
                "title": before.title,
                "resource_type": before.resource_type,
                "workstream_id": before.workstream_id,
                "url": before.url,
                "notes": before.notes,
                "is_required": before.is_required,
            }
            merged.update(changes)
            updated = repository.update_resource(
                resource_id,
                actor_user_id=actor.id if actor else None,
                **merged,
            )
            for field, value in changes.items():
                self._append_change_activity(
                    repository,
                    actor,
                    before.program_id,
                    "resource",
                    resource_id,
                    field,
                    getattr(before, field),
                    value,
                    updated.workstream_id,
                )
            return updated

        return self._transaction(operation)

    def deactivate_resource(self, actor: CampaignOpsUser | None, resource_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            resource = self._require_resource(repository, resource_id)
            program = self._require_program(repository, resource.program_id)
            assignments = repository.list_assignments_by_program(resource.program_id)
            if not can_manage_resource_state(actor, program, resource, assignments):
                raise CampaignOpsPermissionError("You do not have permission to deactivate this resource.")
            repository.deactivate_resource(resource_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="resource_deactivated",
                entity_type="resource",
                entity_id=resource_id,
                program_id=resource.program_id,
                workstream_id=resource.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated resource {resource.title}.",
            )

        self._transaction(operation)

    def reactivate_resource(self, actor: CampaignOpsUser | None, resource_id: str) -> Resource:
        def operation(repository: CampaignOpsRepository) -> Resource:
            resource = self._require_resource(repository, resource_id)
            program = self._require_program(repository, resource.program_id)
            assignments = repository.list_assignments_by_program(resource.program_id)
            if not can_manage_resource_state(actor, program, resource, assignments):
                raise CampaignOpsPermissionError("You do not have permission to reactivate this resource.")
            self._validate_task_workstream(repository, resource.program_id, resource.workstream_id)
            updated = repository.reactivate_resource(resource_id, actor_user_id=actor.id if actor else None)
            repository.append_event(
                event_type="resource_reactivated",
                entity_type="resource",
                entity_id=resource_id,
                program_id=resource.program_id,
                workstream_id=resource.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated resource {resource.title}.",
            )
            return updated

        return self._transaction(operation)

    def list_program_resources(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[ResourceListRow]:
        repository = self.repository or CampaignOpsRepository()
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have permission to view program resources.")
        return repository.list_resource_rows_by_program(program_id, include_inactive=include_inactive)

    def append_program_note(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        note_text: str,
        **kwargs: Any,
    ) -> ProgramNote:
        cleaned_note = require_text(note_text, "Note")

        def operation(repository: CampaignOpsRepository) -> ProgramNote:
            program = self._require_program(repository, program_id)
            assignments = repository.list_assignments_by_program(program_id)
            if not can_add_note(actor, program, assignments):
                raise CampaignOpsPermissionError("You do not have permission to add a note to this program.")
            self._validate_note_scope(
                repository,
                program_id,
                kwargs.get("workstream_id"),
                kwargs.get("task_id"),
            )
            note = repository.append_note(
                program_id=program_id,
                note_text=cleaned_note,
                author_user_id=actor.id if actor else None,
                workstream_id=kwargs.get("workstream_id"),
                task_id=kwargs.get("task_id"),
                note_type=kwargs.get("note_type"),
                is_internal=bool(kwargs.get("is_internal", False)),
            )
            preview = cleaned_note[:80] + ("..." if len(cleaned_note) > 80 else "")
            repository.append_event(
                event_type="internal_note_added" if note.is_internal else "note_added",
                entity_type="note",
                entity_id=note.id,
                program_id=program_id,
                workstream_id=note.workstream_id,
                task_id=note.task_id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"is_internal": note.is_internal, "preview": preview},
                message=f"{actor.display_name if actor else 'System'} added {'an internal ' if note.is_internal else 'a '}note.",
            )
            return note

        return self._transaction(operation)

    def list_program_notes(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        newest_first: bool = True,
        limit: int = 100,
    ) -> list[NoteListRow]:
        repository = self.repository or CampaignOpsRepository()
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have permission to view program notes.")
        return repository.list_note_rows_by_program(
            program_id,
            include_internal=can_view_internal_notes(actor, program, assignments),
            newest_first=newest_first,
            limit=limit,
        )

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

    def resolve_reporting_request_am(
        self,
        repository: CampaignOpsRepository,
        am_name: str | None,
    ) -> CampaignOpsUser:
        display_name = normalize_am_name(am_name)
        user = repository.get_user_by_display_name(display_name)
        if user is None or not user.is_active:
            raise CampaignOpsValidationError("AM must resolve to an active Campaign Operations user.")
        return user

    def _require_reporting_request(
        self,
        repository: CampaignOpsRepository,
        request_id: str,
    ) -> ReportingRequestRecord:
        request = repository.get_reporting_request(request_id)
        if request is None:
            raise CampaignOpsNotFoundError("Reporting request was not found.")
        return request

    def _validate_reporting_request_access(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        program_id: str,
    ) -> Program:
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this request program.")
        if not program.is_active:
            raise CampaignOpsValidationError("Archived programs cannot have request changes.")
        return program

    def _normalize_reporting_request_payload(
        self,
        repository: CampaignOpsRepository,
        actor: CampaignOpsUser | None,
        payload: dict[str, Any],
        before: ReportingRequestRecord | None = None,
    ) -> dict[str, Any]:
        program_id = payload.get("program_id") or (before.program_id if before else None)
        if not program_id:
            raise CampaignOpsValidationError("Program is required.")
        self._validate_reporting_request_access(repository, actor, str(program_id))
        category = validate_request_category(payload.get("request_category") or (before.request_category if before else None))
        request_type = require_text(payload.get("request_type") or (before.request_type if before else None), "Request type")
        if payload.get("am_user_id"):
            am_user = self._require_active_user(repository, str(payload["am_user_id"]), "AM")
        else:
            am_user = self.resolve_reporting_request_am(
                repository,
                payload.get("am_name") or (None if before is None else before.am_user_id),
            ) if before is None or payload.get("am_name") else self._require_active_user(repository, before.am_user_id, "AM")
        assigned_user_id = payload.get("assigned_user_id") if "assigned_user_id" in payload else (before.assigned_user_id if before else None)
        if assigned_user_id:
            self._require_active_user(repository, str(assigned_user_id), "Assigned reporting owner")
        workstream_id = payload.get("workstream_id") if "workstream_id" in payload else (before.workstream_id if before else None)
        if workstream_id:
            self._require_workstream(repository, str(program_id), str(workstream_id))
        brief_url = payload.get("brief_url") if "brief_url" in payload else (before.brief_url if before else None)
        brief_url = self._validate_resource_url(brief_url)
        status = validate_request_status(payload.get("status") or (before.status if before else REQUEST_STATUS_REQUESTED))
        risk = enum_value(RiskLevel, payload.get("risk") or (before.risk if before else RiskLevel.UNRATED.value), "risk")
        waiting_on = payload.get("waiting_on") if "waiting_on" in payload else (before.waiting_on if before else None)
        if waiting_on:
            waiting_on = enum_value(WaitingOn, waiting_on, "waiting_on")
        delivered = bool(payload.get("delivered", before.delivered if before else False))
        review_required = bool(payload.get("review_required", before.review_required if before else False))
        review_complete = bool(payload.get("review_complete", before.review_complete if before else False))
        approval_required = bool(payload.get("approval_required", before.approval_required if before else False))
        approved = bool(payload.get("approved", before.approved if before else False))
        if review_complete and not review_required:
            raise CampaignOpsValidationError("Review complete requires review required.")
        if approved and not approval_required:
            raise CampaignOpsValidationError("Approved requires approval required.")
        if category == REQUEST_CATEGORY_SURVEY:
            approval_required = False
            approved = False
        if category == REQUEST_CATEGORY_REPORT:
            review_required = False
            review_complete = False
        if delivered and status == REQUEST_STATUS_REQUESTED:
            status = REQUEST_STATUS_DELIVERED
        if review_required and not review_complete and status == REQUEST_STATUS_REQUESTED:
            status = REQUEST_STATUS_READY_FOR_REVIEW
        if approval_required and not approved and status == REQUEST_STATUS_REQUESTED:
            status = REQUEST_STATUS_WAITING_FOR_APPROVAL
        completed_at = payload.get("completed_at") if "completed_at" in payload else (before.completed_at if before else None)
        if status == REQUEST_STATUS_COMPLETED and completed_at is None:
            completed_at = datetime.now(UTC)
        if status != REQUEST_STATUS_COMPLETED:
            completed_at = None
        return {
            "program_id": str(program_id),
            "workstream_id": str(workstream_id) if workstream_id else None,
            "request_category": category,
            "request_type": request_type,
            "am_user_id": am_user.id,
            "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
            "due_date": payload.get("due_date") if "due_date" in payload else (before.due_date if before else None),
            "recap_date_with_client": payload.get("recap_date_with_client") if "recap_date_with_client" in payload else (before.recap_date_with_client if before else None),
            "recap_date_text": self._clean_optional_text(payload.get("recap_date_text") if "recap_date_text" in payload else (before.recap_date_text if before else None)),
            "brief_url": brief_url,
            "brief_status_text": self._clean_optional_text(payload.get("brief_status_text") if "brief_status_text" in payload else (before.brief_status_text if before else None)),
            "delivered": delivered,
            "review_required": review_required,
            "review_complete": review_complete,
            "approval_required": approval_required,
            "approved": approved,
            "questions_requested": self._clean_optional_text(payload.get("questions_requested") if "questions_requested" in payload else (before.questions_requested if before else None)),
            "special_requests": self._clean_optional_text(payload.get("special_requests") if "special_requests" in payload else (before.special_requests if before else None)),
            "status": status,
            "risk": risk,
            "waiting_on": waiting_on,
            "completed_at": completed_at,
        }

    def _clean_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    def _request_activity_message(
        self,
        actor: CampaignOpsUser | None,
        field: str,
        before: Any,
        after: Any,
        request: ReportingRequestRecord,
    ) -> str:
        actor_name = actor.display_name if actor else "System"
        if field == "delivered":
            return f"{actor_name} marked {request.request_type} as {'delivered' if after else 'not delivered'}."
        if field == "approved":
            return f"{actor_name} {'approved' if after else 'unapproved'} {request.request_type}."
        if field == "due_date":
            return f"{actor_name} changed the due date from {before or '-'} to {after or '-'}."
        if field == "questions_requested":
            return f"{actor_name} changed questions for {request.request_type}."
        if field == "special_requests":
            return f"{actor_name} changed special requests for {request.request_type}."
        return f"{actor_name} changed {field.replace('_', ' ')} from {before or '-'} to {after or '-'}."

    def create_reporting_request(
        self,
        actor: CampaignOpsUser | None,
        **kwargs: Any,
    ) -> ReportingRequestRecord:
        def operation(repository: CampaignOpsRepository) -> ReportingRequestRecord:
            payload = self._normalize_reporting_request_payload(repository, actor, kwargs)
            request = repository.create_reporting_request(actor_user_id=actor.id if actor else None, **payload)
            program = self._require_program(repository, request.program_id)
            repository.append_event(
                event_type="reporting_request_created",
                entity_type="reporting_request",
                entity_id=request.id,
                program_id=request.program_id,
                workstream_id=request.workstream_id,
                actor_user_id=actor.id if actor else None,
                new_value_json={"request_type": request.request_type, "request_category": request.request_category},
                message=f"{actor.display_name if actor else 'System'} created {request.request_type} request for {program.program_name}.",
            )
            return request

        return self._transaction(operation)

    def update_reporting_request(
        self,
        actor: CampaignOpsUser | None,
        request_id: str,
        **kwargs: Any,
    ) -> ReportingRequestRecord:
        def operation(repository: CampaignOpsRepository) -> ReportingRequestRecord:
            before = self._require_reporting_request(repository, request_id)
            payload = self._normalize_reporting_request_payload(repository, actor, kwargs, before)
            changes = {
                field: value
                for field, value in payload.items()
                if field in REPORTING_REQUEST_EDITABLE_FIELDS and getattr(before, field) != value
            }
            if not changes:
                return before
            merged = {field: getattr(before, field) for field in REPORTING_REQUEST_EDITABLE_FIELDS}
            merged.update(changes)
            updated = repository.update_reporting_request(request_id, actor_user_id=actor.id if actor else None, **merged)
            for field, value in changes.items():
                repository.append_event(
                    event_type=f"reporting_request_{field}_changed",
                    entity_type="reporting_request",
                    entity_id=request_id,
                    program_id=updated.program_id,
                    workstream_id=updated.workstream_id,
                    actor_user_id=actor.id if actor else None,
                    old_value_json={field: self._activity_value(getattr(before, field))},
                    new_value_json={field: self._activity_value(value)},
                    message=self._request_activity_message(actor, field, getattr(before, field), value, updated),
                )
            return updated

        return self._transaction(operation)

    def set_request_delivered(
        self,
        actor: CampaignOpsUser | None,
        request_id: str,
        delivered: bool,
    ) -> ReportingRequestRecord:
        status = REQUEST_STATUS_DELIVERED if delivered else REQUEST_STATUS_REQUESTED
        return self.update_reporting_request(actor, request_id, delivered=delivered, status=status)

    def set_request_review_state(
        self,
        actor: CampaignOpsUser | None,
        request_id: str,
        review_required: bool,
        review_complete: bool,
    ) -> ReportingRequestRecord:
        status = REQUEST_STATUS_READY_FOR_REVIEW if review_required and not review_complete else None
        payload: dict[str, Any] = {"review_required": review_required, "review_complete": review_complete}
        if status:
            payload["status"] = status
        return self.update_reporting_request(actor, request_id, **payload)

    def set_request_approval_state(
        self,
        actor: CampaignOpsUser | None,
        request_id: str,
        approval_required: bool,
        approved: bool,
    ) -> ReportingRequestRecord:
        status = REQUEST_STATUS_WAITING_FOR_APPROVAL if approval_required and not approved else None
        payload: dict[str, Any] = {"approval_required": approval_required, "approved": approved}
        if status:
            payload["status"] = status
        return self.update_reporting_request(actor, request_id, **payload)

    def deactivate_reporting_request(self, actor: CampaignOpsUser | None, request_id: str) -> None:
        def operation(repository: CampaignOpsRepository) -> None:
            request = self._require_reporting_request(repository, request_id)
            self._validate_reporting_request_access(repository, actor, request.program_id)
            repository.deactivate_reporting_request(request_id)
            repository.append_event(
                event_type="reporting_request_deactivated",
                entity_type="reporting_request",
                entity_id=request_id,
                program_id=request.program_id,
                workstream_id=request.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} deactivated {request.request_type} request.",
            )

        self._transaction(operation)

    def reactivate_reporting_request(
        self,
        actor: CampaignOpsUser | None,
        request_id: str,
    ) -> ReportingRequestRecord:
        def operation(repository: CampaignOpsRepository) -> ReportingRequestRecord:
            request = self._require_reporting_request(repository, request_id)
            self._validate_reporting_request_access(repository, actor, request.program_id)
            updated = repository.reactivate_reporting_request(request_id)
            repository.append_event(
                event_type="reporting_request_reactivated",
                entity_type="reporting_request",
                entity_id=request_id,
                program_id=request.program_id,
                workstream_id=request.workstream_id,
                actor_user_id=actor.id if actor else None,
                message=f"{actor.display_name if actor else 'System'} reactivated {request.request_type} request.",
            )
            return updated

        return self._transaction(operation)

    def list_reporting_requests(
        self,
        actor: CampaignOpsUser | None,
        include_inactive: bool = False,
    ) -> list[ReportingRequestListRow]:
        repository = self.repository or CampaignOpsRepository()
        rows = repository.list_reporting_requests(include_inactive=include_inactive)
        if can_access_admin(actor):
            return rows
        visible: list[ReportingRequestListRow] = []
        for row in rows:
            program = self._require_program(repository, row.program_id)
            assignments = repository.list_assignments_by_program(row.program_id)
            if can_view_program(actor, program, assignments):
                visible.append(row)
        return visible

    def list_requests_by_program(
        self,
        actor: CampaignOpsUser | None,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[ReportingRequestListRow]:
        repository = self.repository or CampaignOpsRepository()
        program = self._require_program(repository, program_id)
        assignments = repository.list_assignments_by_program(program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this program requests.")
        return repository.list_requests_by_program(program_id, include_inactive=include_inactive)

    def get_reporting_request_detail(
        self,
        actor: CampaignOpsUser | None,
        request_id: str,
    ) -> ReportingRequestDetail:
        repository = self.repository or CampaignOpsRepository()
        detail = repository.get_reporting_request_detail(request_id)
        if detail is None:
            raise CampaignOpsNotFoundError("Reporting request was not found.")
        program = self._require_program(repository, detail.program_id)
        assignments = repository.list_assignments_by_program(detail.program_id)
        if not can_view_program(actor, program, assignments):
            raise CampaignOpsPermissionError("You do not have access to this request.")
        return detail

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
