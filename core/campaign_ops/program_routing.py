"""Lightweight registry reads and workflow destinations; no generic workspace bundles."""
from dataclasses import dataclass, field
from core.campaign_ops.models import InfluencerCampaignRecord

from core.campaign_ops.exceptions import CampaignOpsPermissionError, CampaignOpsValidationError
from core.campaign_ops.influencer_timeline import InfluencerTimelineService, STAGE_LABELS
from core.campaign_ops.permissions import program_scope_user_id, require_program_access
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService

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
        # The program, roster assignments, campaign and nine initial rows share ONE transaction.
        def operation(repository):
            program_id = CampaignOpsService(repository).create_program_with_workstreams_and_assignments(actor, **kwargs)
            if kwargs.get("primary_workstream_type") == "influencer":
                self._ensure_influencer(repository, actor, program_id)
            return program_id
        return self._transaction(operation)

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

    def resolve(self, actor, program_id):
        repository = self.repository or CampaignOpsRepository()
        program = require_program_access(repository, actor, program_id, active_only=True)
        section = WORKFLOW_SECTIONS.get(program.primary_workstream_type)
        if section is None:
            return ProgramDestination("All Programs", message="No workflow is configured for this Program.")
        if section == "Social Media Management":
            return ProgramDestination(section)
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
