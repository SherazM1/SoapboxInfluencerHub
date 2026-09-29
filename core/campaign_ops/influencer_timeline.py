"""The simple Influencer workspace, backed by existing campaign/planning-step rows."""
from __future__ import annotations

from datetime import date, datetime
from collections.abc import Iterable
from dataclasses import asdict

from core.campaign_ops.models import CampaignOpsUser, InfluencerCampaignRecord, InfluencerPlanningStepRecord

from core.campaign_ops.exceptions import CampaignOpsPermissionError, CampaignOpsValidationError
from core.campaign_ops.enums import WorkflowRole, WorkstreamType
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


EDITOR_COLUMNS = ("Date", "Action", "Program Notes")
CUSTOM_STEP_TYPE = "timeline_custom"


def editor_record(row: InfluencerPlanningStepRecord) -> dict:
    custom = row.step_type == CUSTOM_STEP_TYPE or row.step_title not in ACTION_LIBRARY or row.step_title == "Custom"
    return {"_row_id": row.id, "Date": row.due_date,
            "Action": "Custom" if custom else row.step_title,
            "Custom Action": row.step_title if custom else "",
            "Program Notes": row.notes or ""}


def normalize_editor_record(record: dict) -> dict | None:
    """Normalize one buffered row; completely blank dynamic rows are harmless."""
    def text(key):
        value = record.get(key)
        if value is None:
            return ""
        if not isinstance(value, str):
            raise CampaignOpsValidationError(f"{key} must be text.")
        return value.strip()
    row_id = text("_row_id") or None
    action, custom, notes = text("Action"), text("Custom Action"), text("Program Notes")
    due = record.get("Date")
    if due == "":
        due = None
    if not row_id and due is None and not any((action, custom, notes)):
        return None
    if isinstance(due, datetime):
        due = due.date()
    if due is not None and not isinstance(due, date):
        raise CampaignOpsValidationError("Choose a valid date or leave it blank.")
    title = action_title(action, custom)
    if action != "Custom" and custom:
        raise CampaignOpsValidationError("Clear Custom Action or choose Custom in Action.")
    return {"id": row_id, "title": title, "date": due, "notes": notes or None, "custom": action == "Custom"}


class InfluencerTimelineService(CampaignOpsService):
    """Keeps the new workflow separate from legacy readiness-driven operations."""

    def _owner(self, repository: CampaignOpsRepository, owner_id: str) -> CampaignOpsUser:
        owner = self._require_active_user(repository, owner_id, "Owner")
        eligible_ids = {
            user.id
            for user in repository.list_workflow_role_users(
                WorkstreamType.INFLUENCER.value, WorkflowRole.LEAD_OWNER.value
            )
        }
        if owner.id not in eligible_ids:
            raise CampaignOpsValidationError("Owner must be an active Influencer Lead Owner.")
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

    def save_changes(self, actor: CampaignOpsUser | None, campaign_id: str, owner_id: str,
                     edited_records: list[dict], original_rows: list[InfluencerPlanningStepRecord],
                     original_owner_id: str | None, original_stage: str) -> dict[str, int]:
        """Validate the whole form, then apply a differential save in one transaction."""
        edited = []
        for index, record in enumerate(edited_records, 1):
            try:
                normalized = normalize_editor_record(record)
            except CampaignOpsValidationError as exc:
                raise CampaignOpsValidationError(f"Row {index}: {exc}") from exc
            if normalized is not None:
                edited.append(normalized)
        original = {row.id: row for row in original_rows}
        ids = [row["id"] for row in edited if row["id"] is not None]
        if len(ids) != len(set(ids)) or any(row_id not in original for row_id in ids):
            raise CampaignOpsValidationError("Timeline row identity is invalid. Reopen the campaign.")

        def operation(repository):
            campaign = repository.get_influencer_campaign_for_update(campaign_id)
            if campaign is None or not campaign.is_active:
                raise CampaignOpsValidationError("Campaign is unavailable.")
            self._validate_influencer_access(repository, actor, campaign.program_id)
            self._owner(repository, owner_id)
            current_rows = repository.list_influencer_planning_steps(campaign_id, include_inactive=True)
            current = {row.id: row for row in current_rows if row.is_active}
            if (campaign.manager_user_id != original_owner_id or campaign.influencer_stage != original_stage
                    or set(current) != set(original)
                    or any(asdict(current[key]) != asdict(original[key]) for key in current)):
                raise CampaignOpsValidationError("This campaign changed since you opened it. Reopen it before saving.")
            # Every payload is validated before the first database mutation, including
            # legacy start/due constraints and the owner update's existing rules.
            owner_payload = None
            if owner_id != campaign.manager_user_id:
                owner_payload = self._validate_influencer_campaign_payload(repository, actor, {"manager_user_id": owner_id}, campaign)
            updates, additions = [], []
            next_order = max((row.sequence_order for row in current_rows), default=0)
            for record in edited:
                before = current.get(record["id"])
                if before:
                    was_custom = editor_record(before)["Action"] == "Custom"
                    if (before.step_title, before.due_date, before.notes or "", was_custom) == (
                            record["title"], record["date"], record["notes"] or "", record["custom"]):
                        continue
                    kwargs = {"step_title": record["title"], "due_date": record["date"], "notes": record["notes"]}
                    if record["custom"]:
                        kwargs["step_type"] = CUSTOM_STEP_TYPE
                    elif was_custom:
                        kwargs["step_type"] = "timeline_manual"
                    payload = self._planning_step_payload(repository, campaign_id, kwargs, before)
                    updates.append((before.id, payload))
                else:
                    next_order += 1
                    payload = self._planning_step_payload(repository, campaign_id, {
                        "step_title": record["title"], "due_date": record["date"], "notes": record["notes"],
                        "step_type": CUSTOM_STEP_TYPE if record["custom"] else "timeline_manual",
                        "status": "not_started", "sequence_order": next_order})
                    additions.append(payload)
            removals = set(original) - set(ids)
            def event(kind, row_id, title):
                repository.append_event(event_type=f"influencer_planning_step_{kind}",
                    entity_type="influencer_planning_step", entity_id=row_id,
                    program_id=campaign.program_id, workstream_id=campaign.workstream_id,
                    actor_user_id=actor.id if actor else None,
                    message=f"{self._influencer_actor_label(actor)} {kind} timeline row {title}.")
            for row_id, payload in updates:
                repository.update_influencer_planning_step(row_id, **payload)
                event("updated", row_id, payload["step_title"])
            for payload in additions:
                row = repository.create_influencer_planning_step(campaign_id, **payload)
                event("created", row.id, row.step_title)
            for row_id in sorted(removals):
                repository.deactivate_influencer_planning_step(row_id)
                event("deactivated", row_id, original[row_id].step_title)
            if owner_payload is not None:
                before_owner = campaign.manager_user_id
                repository.update_influencer_campaign(campaign_id, **{key: value for key, value in owner_payload.items() if key != "program_id"})
                repository.append_event(event_type="influencer_campaign_manager_user_id_changed",
                    entity_type="influencer_campaign", entity_id=campaign_id,
                    program_id=campaign.program_id, workstream_id=campaign.workstream_id,
                    actor_user_id=actor.id if actor else None,
                    old_value_json={"manager_user_id": before_owner}, new_value_json={"manager_user_id": owner_id},
                    message=f"{self._influencer_actor_label(actor)} changed the timeline owner.")
            return {"updated": len(updates), "added": len(additions), "removed": len(removals),
                    "owner_changed": int(owner_payload is not None), "unchanged": len(ids) - len(updates)}
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
