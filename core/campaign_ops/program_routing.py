"""Lightweight registry reads and workflow destinations; no generic workspace bundles."""
from dataclasses import dataclass, field

from core.campaign_ops.enums import WorkstreamType
from core.campaign_ops.models import InfluencerCampaignRecord
from core.campaign_ops.exceptions import CampaignOpsPermissionError, CampaignOpsValidationError
from core.campaign_ops.influencer_timeline import InfluencerTimelineService, STAGE_LABELS
from core.campaign_ops.content_management_timeline import ContentManagementTimelineService
from core.campaign_ops.permissions import program_scope_user_id, require_program_access
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.retail_media_timeline import RetailMediaTimelineService
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.smm import SMMTimelineService

WORKFLOW_SECTIONS = {
    "influencer": "Influencer",
    "retail_media": "Retail Media",
    "ecommerce": "eCommerce / Content",
    "smm": "Social Media Management",
    "insights": "Insights",
}


@dataclass(frozen=True)
class ProgramDestination:
    section: str
    record_id: str | None = None
    stage: str | None = None
    message: str | None = None
    campaign: InfluencerCampaignRecord | None = field(default=None, compare=False, repr=False)


class ProgramRoutingService(CampaignOpsService):
    def list_registry(self, actor):
        if actor is None:
            raise CampaignOpsPermissionError("A Campaign Operations user is required.")
        repository = self.repository or CampaignOpsRepository()
        return repository.list_program_registry(program_scope_user_id(actor))

    def create_registry_program(self, actor, **kwargs):
        # The program, assignments and workflow workspace share ONE transaction.
        def operation(repository):
            program_id = CampaignOpsService(repository).create_program_with_workstreams_and_assignments(actor, **kwargs)
            if kwargs.get("primary_workstream_type") == "influencer":
                self._ensure_influencer(repository, actor, program_id)
            elif kwargs.get("primary_workstream_type") == WorkstreamType.SMM.value:
                self._ensure_smm(repository, actor, program_id)
            elif kwargs.get("primary_workstream_type") == WorkstreamType.RETAIL_MEDIA.value:
                self._ensure_retail_media(repository, actor, program_id, retail_type=kwargs.get("retail_type"))
            elif kwargs.get("primary_workstream_type") == WorkstreamType.ECOMMERCE.value:
                self._ensure_content_management(repository, actor, program_id)
            return program_id
        return self._transaction(operation)

    def _ensure_smm(self, repository, actor, program_id):
        program = repository.lock_program(program_id)
        if program is None or not program.is_active or program.primary_workstream_type != WorkstreamType.SMM.value:
            raise CampaignOpsValidationError("An active SMM Program is required.")
        require_program_access(repository, actor, program.id, active_only=True)

        workstreams = [
            workstream for workstream in repository.list_workstreams_by_program(program.id)
            if workstream.workstream_type == WorkstreamType.SMM.value and workstream.is_active
        ]
        if len(workstreams) != 1:
            raise CampaignOpsValidationError("The SMM Program must have exactly one active SMM Workstream.")

        workspaces = repository.list_smm_programs_by_program(program.id)
        if len(workspaces) > 1:
            raise CampaignOpsValidationError(
                "Multiple active SMM workspaces are linked to this Program. Resolve the duplicates before opening it."
            )
        if workspaces and workspaces[0].workstream_id != workstreams[0].id:
            raise CampaignOpsValidationError("The active SMM workspace is linked to a different Workstream.")

        workspace, _ = SMMTimelineService(repository).initialize_program(actor, program.id)
        return workspace

    def _ensure_influencer(self, repository, actor, program_id):
        # Same program row lock used by the existing timeline campaign create path.
        # Re-read after locking so simultaneous opens cannot both create a campaign.
        program = repository.lock_influencer_timeline_program(program_id)
        if program is None or not program.is_active:
            raise CampaignOpsValidationError("An active Program is required.")
        records = repository.list_influencer_campaigns_by_program(program_id)
        if records:
            return records
        assignments = repository.list_assignments_by_program(program_id)
        require_program_access(repository, actor, program.id, active_only=True)
        lead = next((a for a in assignments if a.is_active and a.is_primary
                     and a.assignment_role == "program_owner" and a.workstream_id is None), None)
        if lead is None:
            raise CampaignOpsValidationError("A primary Lead Owner is required to initialize this Influencer timeline.")
        # The existing timeline Owner is the Lead Owner, despite the legacy campaign
        # column name manager_user_id. Workstream ownership remains the selected Manager.
        campaign = InfluencerTimelineService(repository).create_campaign(
            actor, program.id, program.program_name, lead.user_id)
        return [campaign]

    def _ensure_retail_media(self, repository, actor, program_id, retail_type: str | None = None):
        if not all(hasattr(repository, name) for name in (
            "get_retail_media_program_by_program",
            "create_retail_media_program",
            "list_retail_media_timeline_rows",
            "create_retail_media_timeline_row",
            "update_retail_media_timeline_row",
            "deactivate_retail_media_timeline_row",
            "get_retail_media_timeline_row",
        )):
            return None

        program = repository.lock_program(program_id)
        if program is None or not program.is_active or program.primary_workstream_type != WorkstreamType.RETAIL_MEDIA.value:
            raise CampaignOpsValidationError("An active Retail Media Program is required.")
        require_program_access(repository, actor, program.id, active_only=True)

        workstreams = [
            workstream for workstream in repository.list_workstreams_by_program(program.id)
            if workstream.workstream_type == WorkstreamType.RETAIL_MEDIA.value and workstream.is_active
        ]
        if len(workstreams) != 1:
            raise CampaignOpsValidationError("The Retail Media Program must have exactly one active Retail Media Workstream.")

        workspace = repository.get_retail_media_program_by_program(program.id)
        if workspace is not None and workspace.workstream_id != workstreams[0].id:
            raise CampaignOpsValidationError("The active Retail Media workspace is linked to a different Workstream.")

        workspace = repository.get_retail_media_program_by_program(program.id)
        if workspace is None:
            workspace, _ = RetailMediaTimelineService(repository).initialize_program(actor, program.id, retail_type=retail_type or "general")
        return workspace

    def _ensure_content_management(self, repository, actor, program_id):
        program = repository.lock_program(program_id)
        if program is None or not program.is_active or program.primary_workstream_type != WorkstreamType.ECOMMERCE.value:
            raise CampaignOpsValidationError("An active Content Management / eCommerce Program is required.")
        require_program_access(repository, actor, program.id, active_only=True)
        workstreams = [
            workstream for workstream in repository.list_workstreams_by_program(program.id)
            if workstream.workstream_type == WorkstreamType.ECOMMERCE.value and workstream.is_active
        ]
        if len(workstreams) != 1:
            raise CampaignOpsValidationError(
                "The Content Management Program must have exactly one active Content/eCommerce Workstream."
            )
        workspaces = repository.list_content_management_programs_by_program(program.id)
        if len(workspaces) > 1:
            raise CampaignOpsValidationError(
                "Multiple active Content Management workspaces are linked to this Program. Resolve duplicates before opening it."
            )
        if workspaces and workspaces[0].workstream_id != workstreams[0].id:
            raise CampaignOpsValidationError("The Content Management workspace is linked to a different Workstream.")
        workspace, _ = ContentManagementTimelineService(repository).initialize_program(actor, program.id)
        return workspace

    def resolve(self, actor, program_id):
        repository = self.repository or CampaignOpsRepository()
        program = require_program_access(repository, actor, program_id, active_only=True)
        section = WORKFLOW_SECTIONS.get(program.primary_workstream_type)
        if section is None:
            return ProgramDestination("All Programs", message="No workflow is configured for this Program.")
        if section == "Social Media Management":
            self._transaction(lambda repo: self._ensure_smm(repo, actor, program.id))
            return ProgramDestination(section, program.id)
        if section == "eCommerce / Content":
            if all(hasattr(repository, name) for name in (
                "list_content_management_programs_by_program",
                "get_content_management_program_by_program",
                "create_content_management_program",
                "list_content_management_timeline_rows",
                "create_content_management_timeline_row",
                "update_content_management_timeline_row",
                "deactivate_content_management_timeline_row",
            )):
                workspace = self._transaction(lambda repo: self._ensure_content_management(repo, actor, program.id))
                return ProgramDestination(section, workspace.id)
        if section == "Retail Media":
            workspace = None
            if all(hasattr(repository, name) for name in (
                "get_retail_media_program_by_program",
                "create_retail_media_program",
                "list_retail_media_timeline_rows",
                "create_retail_media_timeline_row",
                "update_retail_media_timeline_row",
                "deactivate_retail_media_timeline_row",
                "get_retail_media_timeline_row",
            )):
                workspace = self._transaction(lambda repo: self._ensure_retail_media(repo, actor, program.id))
            if workspace is not None:
                return ProgramDestination(section, workspace.id)
            records = repository.list_program_workflow_records(program.id, program.primary_workstream_type)
            active = [record for record in records if getattr(record, "is_active", True)]
            if len(active) == 1:
                return ProgramDestination(section, active[0].id)
            if len(active) > 1:
                raise CampaignOpsValidationError("Multiple active Retail Media records are linked to this Program. Resolve the duplicates before opening it.")
            return ProgramDestination(section, message="No open Retail Media workspace is available for this Program.")
        records = (repository.list_influencer_campaigns_by_program(program.id)
                   if section == "Influencer" else
                   repository.list_program_workflow_records(program.id, program.primary_workstream_type))
        if not records and program.primary_workstream_type == "influencer" and program.is_active:
            records = self._transaction(lambda repo: self._ensure_influencer(repo, actor, program.id))
        active = [record for record in records if record.is_active]
        if section == "Influencer" and len(active) > 1:
            raise CampaignOpsValidationError(
                "Multiple active Influencer campaigns are linked to this Program. "
                "Resolve the duplicate campaign links before opening it from All Programs."
            )
        if len(active) == 1:
            record = active[0]
            stage = record.influencer_stage if section == "Influencer" else None
            if section != "Influencer" or stage in STAGE_LABELS:
                return ProgramDestination(section, record.id, stage, campaign=record if section == "Influencer" else None)
        # Never choose an arbitrary record or reseed archived/completed timelines.
        message = ("This Program has multiple workflow records. Choose one from the workflow list."
                   if len(active) > 1 else "No open workflow record is available for this Program.")
        return ProgramDestination(section, message=message)
