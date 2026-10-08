from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from core.campaign_ops.enums import WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsValidationError
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import require_program_access
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService

DEFAULT_GENERAL_RETAIL_MEDIA_ACTIONS = (
    "Finalize campaign brief and retailer scope",
    "Confirm retailer setup, login access, and account owner",
    "Collect and align product assortment and SKU list",
    "Lock media placements, exclusions, and targeting",
    "Finalize campaign launch calendar and flighting dates",
    "Submit initial assets and trafficking for review",
    "QA all targeting, creative, and placements",
    "Launch campaign and monitor pacing",
    "Review early performance and optimization opportunities",
    "Refresh creative or targeting based on results",
    "Prepare wrap-up recap and final reporting",
    "Close campaign and archive final learnings",
)

DEFAULT_INCOMM_RETAIL_MEDIA_ACTIONS = (
    "InComm retailer brief and partner setup",
    "InComm product and SKU master file confirmed",
    "InComm asset list and retail requirements collected",
    "InComm retailer QA and approval complete",
    "InComm launch readiness checklist approved",
    "InComm performance review and optimization sync",
)


@dataclass(slots=True)
class RetailMediaProgramRecord:
    id: str
    program_id: str
    workstream_id: str | None
    retail_type: str = "general"
    is_active: bool = True
    created_at: object | None = None
    updated_at: object | None = None
    created_by_user_id: str | None = None
    updated_by_user_id: str | None = None


@dataclass(slots=True)
class RetailMediaTimelineRowRecord:
    id: str
    retail_media_program_id: str
    action: str
    due_date: date | None = None
    done: bool = False
    program_notes: str | None = None
    sequence_order: int = 0
    is_active: bool = True
    created_at: object | None = None
    updated_at: object | None = None
    created_by_user_id: str | None = None
    updated_by_user_id: str | None = None

    def __post_init__(self) -> None:
        if not self.action:
            raise ValueError("action is required")


def sort_retail_media_timeline_rows(rows: Iterable[RetailMediaTimelineRowRecord]) -> list[RetailMediaTimelineRowRecord]:
    return sorted(
        (row for row in rows if getattr(row, "is_active", True)),
        key=lambda row: (
            getattr(row, "due_date", None) is None,
            not bool(getattr(row, "done", False)),
            getattr(row, "due_date", None) or date.max,
            getattr(row, "sequence_order", 0),
            str(getattr(row, "id", "")),
        ),
    )


class RetailMediaTimelineService(CampaignOpsService):
    """Keep the new Retail Media workflow separate from the legacy campaign dashboard."""

    def _baseline_rows(self, retail_media_program_id: str, retail_type: str) -> list[dict]:
        normalized = (retail_type or "general").strip().lower()
        actions = DEFAULT_INCOMM_RETAIL_MEDIA_ACTIONS + DEFAULT_GENERAL_RETAIL_MEDIA_ACTIONS if normalized == "incomm" else DEFAULT_GENERAL_RETAIL_MEDIA_ACTIONS
        return [
            {
                "retail_media_program_id": retail_media_program_id,
                "action": action,
                "done": False,
                "due_date": None,
                "program_notes": None,
                "sequence_order": index + 1,
            }
            for index, action in enumerate(actions)
        ]

    def initialize_program(self, actor: CampaignOpsUser | None, program_id: str, retail_type: str = "general"):
        repository = self.repository or CampaignOpsRepository()
        require_program_access(repository, actor, program_id, active_only=True)
        existing = repository.get_retail_media_program_by_program(program_id)
        if existing is not None:
            return existing, repository.list_retail_media_timeline_rows(existing.id)

        def operation(repo):
            repo.lock_program(program_id)
            return RetailMediaTimelineService(repo)._initialize(actor, program_id, retail_type)

        return self._transaction(operation)

    def _initialize(self, actor, program_id: str, retail_type: str = "general"):
        program = self.repository.get_program(program_id)
        if program is None:
            raise ValueError("Program not found")
        existing = self.repository.get_retail_media_program_by_program(program_id)
        if existing is not None:
            return existing, self.repository.list_retail_media_timeline_rows(existing.id)

        workstream = next(
            (ws for ws in self.repository.list_workstreams_by_program(program_id) if ws.workstream_type == WorkstreamType.RETAIL_MEDIA.value),
            None,
        )
        if workstream is None:
            raise ValueError("Retail Media workstream missing")

        workspace = self.repository.create_retail_media_program(
            program_id,
            workstream.id,
            retail_type=str(retail_type or "general").lower(),
            actor_user_id=getattr(actor, "id", None),
        )
        rows = []
        for row in self._baseline_rows(workspace.id, workspace.retail_type):
            rows.append(
                self.repository.create_retail_media_timeline_row(
                    row["retail_media_program_id"],
                    row["action"],
                    due_date=row["due_date"],
                    program_notes=row["program_notes"],
                    done=row["done"],
                    sequence_order=row["sequence_order"],
                    actor_user_id=getattr(actor, "id", None),
                )
            )
        return workspace, rows

    def workspace(self, actor: CampaignOpsUser | None, program_id: str, retail_type: str = "general"):
        return self.initialize_program(actor, program_id, retail_type=retail_type)

    def get_workspace(self, actor: CampaignOpsUser | None, program_id: str, retail_type: str = "general"):
        return self.initialize_program(actor, program_id, retail_type=retail_type)

    def timeline_rows(self, program_id: str):
        return self.fetch_rows(program_id)

    def fetch_rows(self, program_id: str):
        workspace = self.repository.get_retail_media_program_by_program(program_id)
        if workspace is None:
            return []
        return self.repository.list_retail_media_timeline_rows(workspace.id)

    def get_row(self, row_id: str):
        return self.repository.get_retail_media_timeline_row(row_id)

    def seed_baseline(self, actor: CampaignOpsUser | None, program_id: str, retail_type: str = "general"):
        return self.initialize_program(actor, program_id, retail_type=retail_type)

    def create_row(self, actor: CampaignOpsUser | None, retail_media_program_id: str, action: str, due_date=None, program_notes=None, done=False):
        rows = self.repository.list_retail_media_timeline_rows(retail_media_program_id, include_inactive=True)
        sequence_order = max((row.sequence_order for row in rows), default=0) + 1
        return self.repository.create_retail_media_timeline_row(
            retail_media_program_id,
            action,
            due_date=due_date,
            program_notes=program_notes,
            done=done,
            sequence_order=sequence_order,
            actor_user_id=getattr(actor, "id", None),
        )

    def update_row(self, actor: CampaignOpsUser | None, row_id: str, **kwargs):
        return self.repository.update_retail_media_timeline_row(
            row_id,
            actor_user_id=getattr(actor, "id", None),
            **kwargs,
        )

    def remove_row(self, actor: CampaignOpsUser | None, row_id: str):
        self.repository.deactivate_retail_media_timeline_row(row_id, actor_user_id=getattr(actor, "id", None))

    def update_done(self, actor: CampaignOpsUser | None, row_id: str, done: bool):
        return self.update_row(actor, row_id, done=done)

    def update_date(self, actor: CampaignOpsUser | None, row_id: str, due_date):
        return self.update_row(actor, row_id, due_date=due_date)

    def update_action(self, actor: CampaignOpsUser | None, row_id: str, action: str):
        return self.update_row(actor, row_id, action=action)

    def update_program_notes(self, actor: CampaignOpsUser | None, row_id: str, program_notes):
        return self.update_row(actor, row_id, program_notes=program_notes)

    def assignment_state(self, actor, program_id):
        repo = self.repository or CampaignOpsRepository()
        require_program_access(repo, actor, program_id, active_only=True)
        assignments = repo.list_assignments_by_program(program_id)
        streams = [w for w in repo.list_workstreams_by_program(program_id)
                   if w.is_active and w.workstream_type == WorkstreamType.RETAIL_MEDIA.value]
        leads = [a for a in assignments if a.is_active and a.is_primary
                 and a.assignment_role == "program_owner" and a.workstream_id is None]
        if len(streams) != 1 or len(leads) != 1:
            raise CampaignOpsValidationError("Resolve Program ownership before editing this workspace.")
        return {"lead_id": leads[0].user_id, "manager_id": streams[0].owner_user_id,
                "workstream_id": streams[0].id,
                "assignments": tuple(sorted((a.id, a.user_id, a.assignment_role, a.is_primary)
                    for a in assignments if a.is_active))}

    @staticmethod
    def _row_state(row):
        return (row.id, row.due_date, row.action, bool(row.done), row.program_notes or "", row.sequence_order)

    def save_changes(self, actor, program_id, records, original_rows, original_assignments, lead_id, manager_id, retail_type=None):
        edited = []
        for record in records:
            action = (record.get("Action") or "").strip()
            due, done, notes = record.get("Date"), record.get("Done", False), record.get("Program Notes") or ""
            if not record.get("_row_id") and not any((action, due, done, notes)):
                continue
            if not action:
                raise CampaignOpsValidationError("Every row requires an action.")
            if due is not None and not isinstance(due, date):
                raise CampaignOpsValidationError("Choose a valid date or leave it blank.")
            if not isinstance(done, bool):
                raise CampaignOpsValidationError("Done must be a checkbox value.")
            edited.append({"id": record.get("_row_id"), "action": action, "due_date": due,
                           "done": done, "program_notes": notes})

        original = {r.id: self._row_state(r) for r in original_rows}
        ids = [row["id"] for row in edited if row["id"]]
        if len(ids) != len(set(ids)) or any(i not in original for i in ids):
            raise CampaignOpsValidationError("Timeline row identity is invalid. Reopen the Program.")

        def operation(repo):
            repo.lock_program(program_id)
            require_program_access(repo, actor, program_id, active_only=True)
            scoped = RetailMediaTimelineService(repo)
            ownership = scoped.assignment_state(actor, program_id)
            if ownership != original_assignments:
                raise CampaignOpsValidationError("Assignments changed. Reopen the Program before saving.")
            lead_changed = lead_id != ownership["lead_id"]
            manager_changed = manager_id != ownership["manager_id"]
            if retail_type is not None:
                retail_type = str(retail_type).strip().lower() or "general"
            if lead_changed or manager_changed:
                self._require_admin(actor)
                if lead_changed and lead_id not in {u.id for u in repo.list_workflow_role_users("retail_media", "lead_owner")}:
                    raise CampaignOpsValidationError("Choose an eligible active lead owner.")
                if manager_changed and manager_id not in {u.id for u in repo.list_workflow_role_users("retail_media", "manager")}:
                    raise CampaignOpsValidationError("Choose an eligible active manager.")

            workspace = repo.get_retail_media_program_by_program(program_id)
            if workspace is None:
                raise CampaignOpsValidationError("Workspace is unavailable.")
            all_rows = repo.list_retail_media_timeline_rows(workspace.id, include_inactive=True)
            current = {r.id: r for r in all_rows if r.is_active}
            if {i: self._row_state(r) for i, r in current.items()} != original:
                raise CampaignOpsValidationError("Timeline changed. Reopen the Program before saving.")
            if retail_type is not None and retail_type != workspace.retail_type:
                repo.update_retail_media_program(workspace.id, actor_user_id=actor.id, retail_type=retail_type)

            order = max((r.sequence_order for r in all_rows), default=0)
            counts = {"updated": 0, "added": 0, "removed": 0}
            for row in edited:
                payload = {k: v for k, v in row.items() if k != "id"}
                if row["id"]:
                    before = current[row["id"]]
                    if (before.due_date, before.action, bool(before.done), before.program_notes or "") == (
                            row["due_date"], row["action"], row["done"], row["program_notes"]):
                        continue
                    repo.update_retail_media_timeline_row(row["id"], actor_user_id=actor.id, **payload)
                    counts["updated"] += 1
                else:
                    order += 1
                    repo.create_retail_media_timeline_row(workspace.id, sequence_order=order, actor_user_id=actor.id, **payload)
                    counts["added"] += 1
            for row_id in set(original) - set(ids):
                repo.deactivate_retail_media_timeline_row(row_id, actor_user_id=actor.id)
                counts["removed"] += 1
            if lead_changed:
                scoped.reassign_primary_program_owner(actor, program_id, lead_id)
            if manager_changed:
                scoped.reassign_workstream_lead(actor, program_id, ownership["workstream_id"], manager_id)
            counts.update(owner_changed=int(lead_changed), manager_changed=int(manager_changed))
            return counts

        return self._transaction(operation)
