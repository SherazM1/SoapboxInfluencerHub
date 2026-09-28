"""The simple Influencer workspace, backed by existing campaign/planning-step rows."""
from __future__ import annotations

from datetime import date
from collections.abc import Iterable

from core.campaign_ops.models import CampaignOpsUser, InfluencerCampaignRecord, InfluencerPlanningStepRecord

from core.campaign_ops.exceptions import CampaignOpsPermissionError, CampaignOpsValidationError
from core.campaign_ops.permissions import can_access_admin, can_view_program
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService

DEFAULT_ACTIONS = (
    "Application out to influencers",
    "Soapbox to send first round of influencers & brief for review",
    "Client to send brief and influencer feedback / approvals",
    "Soapbox to hire influencers",
    "Influencer drafts are due",
    "Influencer resubmissions are due",
    "Soapbox to send first round of influencer content for review",
    "Client to send content feedback / approvals",
    "Influencers begin going live in waves",
)
ACTION_LIBRARY = (
    *DEFAULT_ACTIONS[:4],
    "Client to send content / messaging guidelines",
    "Soapbox to ship product(s) to influencers",
    "Influencer approvals due",
    "Scripts & captions due from influencers",
    "Soapbox to provide scripts & captions for review",
    "Script / caption feedback due",
    DEFAULT_ACTIONS[4],
    "Influencer drafts due for internal review",
    *DEFAULT_ACTIONS[5:8],
    "Soapbox to send second round of influencer content for review, if needed",
    "Final content approval due",
    "Display creative sent for approval",
    "Display creative approval due",
    DEFAULT_ACTIONS[8],
    "Campaign Launch", "Wave Launch", "Paid Live End", "Campaign Wrap", "Ready for Recap",
    "EOP Survey Due", "Reporting Due", "Recap Draft Due", "Internal Review", "Client Review",
    "Client Recap", "Invoice Due", "Final Close", "Custom",
)
STAGE_LABELS = {"planning": "Planning", "live": "Live", "recapping": "Recapping"}
FORWARD_STAGES = {"planning": "live", "live": "recapping", "recapping": "complete"}


def sort_timeline(rows: Iterable[InfluencerPlanningStepRecord]) -> list[InfluencerPlanningStepRecord]:
    return sorted((row for row in rows if row.is_active), key=lambda row: (
        row.due_date is None, row.due_date or date.max, row.sequence_order, str(row.id)))


def action_title(action: str, custom: str = "") -> str:
    if action not in ACTION_LIBRARY:
        raise CampaignOpsValidationError("Choose an action from the library.")
    title = custom.strip() if action == "Custom" else action
    if not title:
        raise CampaignOpsValidationError("Enter a custom action.")
    return title


class InfluencerTimelineService(CampaignOpsService):
    """Keeps the new workflow separate from legacy readiness-driven operations."""

    def _owner(self, repository: CampaignOpsRepository, owner_id: str) -> CampaignOpsUser:
        owner = self._require_active_user(repository, owner_id, "Owner")
        if owner.display_name not in ("T", "L"):
            raise CampaignOpsValidationError("Owner must be T or L.")
        return owner

    def create_campaign(self, actor: CampaignOpsUser | None, program_id: str, title: str, owner_id: str) -> InfluencerCampaignRecord:
        def operation(repository):
            self._validate_influencer_access(repository, actor, program_id)
            repository.lock_influencer_timeline_program(program_id)
            self._owner(repository, owner_id)
            service = CampaignOpsService(repository)
            campaign = service.create_influencer_campaign(
                actor, program_id=program_id, campaign_title=title, manager_user_id=owner_id,
                influencer_stage="planning", planning_status="not_started")
            # Creation and all nine defaults commit together. There is deliberately no
            # reseed-on-open path: renamed/deactivated defaults must never reappear.
            for order, action in enumerate(DEFAULT_ACTIONS, 1):
                step = repository.create_influencer_planning_step(
                    campaign.id, action, sequence_order=order,
                    step_type="timeline_default", due_date=None, notes=None, status="not_started")
                repository.append_event(event_type="influencer_planning_step_created",
                    entity_type="influencer_planning_step", entity_id=step.id,
                    program_id=campaign.program_id, workstream_id=campaign.workstream_id,
                    actor_user_id=actor.id if actor else None,
                    message=f"{self._influencer_actor_label(actor)} added planning step {action}.")
            return campaign
        return self._transaction(operation)

    def list_campaigns(self, actor: CampaignOpsUser | None, stage: str) -> tuple[list[InfluencerCampaignRecord], dict[str, list[InfluencerPlanningStepRecord]]]:
        if actor is None:
            raise CampaignOpsPermissionError("A Campaign Operations user is required.")
        if stage not in STAGE_LABELS:
            raise CampaignOpsValidationError("Choose Planning, Live or Recapping.")
        repository = self.repository or CampaignOpsRepository()
        campaigns = repository.list_influencer_timeline_campaigns(stage)
        access = {}
        visible = []
        for campaign in campaigns:
            if can_access_admin(actor):
                visible.append(campaign)
                continue
            if campaign.program_id not in access:
                access[campaign.program_id] = can_view_program(actor,
                    self._require_program(repository, campaign.program_id),
                    repository.list_assignments_by_program(campaign.program_id))
            if access[campaign.program_id]:
                visible.append(campaign)
        rows = repository.list_influencer_planning_steps_for_campaigns([c.id for c in visible])
        return visible, rows

    def workspace(self, actor: CampaignOpsUser | None, campaign_id: str) -> tuple[InfluencerCampaignRecord, list[InfluencerPlanningStepRecord]]:
        repository = self.repository or CampaignOpsRepository()
        campaign = self._require_influencer_campaign(repository, campaign_id)
        if actor is None or not (can_access_admin(actor) or
                can_view_program(actor, self._require_program(repository, campaign.program_id),
                                 repository.list_assignments_by_program(campaign.program_id))):
            raise CampaignOpsPermissionError("You do not have access to this Influencer campaign.")
        return campaign, sort_timeline(repository.list_influencer_planning_steps(campaign_id))

    def change_owner(self, actor: CampaignOpsUser | None, campaign_id: str, owner_id: str) -> InfluencerCampaignRecord:
        def operation(repository):
            repository.get_influencer_campaign_for_update(campaign_id)
            self._owner(repository, owner_id)
            return CampaignOpsService(repository).update_influencer_campaign(actor, campaign_id, manager_user_id=owner_id)
        return self._transaction(operation)

    def save_row(self, actor: CampaignOpsUser | None, campaign_id: str, action: str, custom: str, due_date: date | None, notes: str, row_id: str | None = None) -> InfluencerPlanningStepRecord:
        title = action_title(action, custom)
        def operation(repository):
            campaign = repository.get_influencer_campaign_for_update(campaign_id)
            if campaign is None:
                raise CampaignOpsValidationError("Campaign is unavailable.")
            self._validate_influencer_access(repository, actor, campaign.program_id)
            rows = repository.list_influencer_planning_steps(campaign_id, include_inactive=True)
            service = CampaignOpsService(repository)
            if row_id is not None:
                if not any(row.id == row_id and row.is_active for row in rows):
                    raise CampaignOpsValidationError("This timeline row is no longer available.")
                return service.update_influencer_planning_step(actor, campaign_id, row_id,
                    step_title=title, due_date=due_date, notes=notes)
            return service.create_influencer_planning_step(actor, campaign_id, title,
                due_date=due_date, notes=notes, status="not_started", step_type="timeline_manual",
                sequence_order=max((row.sequence_order for row in rows), default=0) + 1)
        return self._transaction(operation)

    def remove_row(self, actor: CampaignOpsUser | None, campaign_id: str, row_id: str) -> None:
        def operation(repository):
            repository.get_influencer_campaign_for_update(campaign_id)
            self._influencer_child_context(repository, actor, campaign_id)
            if not any(row.id == row_id for row in repository.list_influencer_planning_steps(campaign_id)):
                raise CampaignOpsValidationError("This timeline row is no longer available.")
            CampaignOpsService(repository).deactivate_influencer_planning_step(actor, campaign_id, row_id)
        return self._transaction(operation)

    def advance(self, actor: CampaignOpsUser | None, campaign_id: str, expected_stage: str) -> InfluencerCampaignRecord:
        def operation(repository):
            before = repository.get_influencer_campaign_for_update(campaign_id)
            if before is None:
                raise CampaignOpsValidationError("Campaign is unavailable.")
            self._validate_influencer_access(repository, actor, before.program_id)
            if not before.is_active or before.influencer_stage != expected_stage or expected_stage not in FORWARD_STAGES:
                raise CampaignOpsValidationError("Campaign stage changed. Reopen the campaign before moving it.")
            target = FORWARD_STAGES[expected_stage]
            status = {"live": "ready_to_launch", "recapping": "ready_to_recap", "complete": "complete"}[target]
            # Intentionally replaces tracker readiness prerequisites in this UI only.
            # Legacy methods, child records, statuses and templates are untouched.
            updated = CampaignOpsService(repository).update_influencer_campaign(
                actor, campaign_id, influencer_stage=target, planning_status=status)
            repository.append_event(event_type="influencer_timeline_stage_changed",
                entity_type="influencer_campaign", entity_id=campaign_id,
                program_id=updated.program_id, workstream_id=updated.workstream_id,
                actor_user_id=actor.id, old_value_json={"stage": expected_stage},
                new_value_json={"stage": target},
                message=f"{actor.display_name} moved {updated.campaign_title} to {target} from the timeline workspace.")
            return updated
        return self._transaction(operation)
