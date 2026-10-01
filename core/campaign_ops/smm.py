from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.permissions import require_program_access
from core.campaign_ops.exceptions import CampaignOpsValidationError

from core.campaign_ops.enums import WorkflowRole, WorkstreamType
from core.campaign_ops.models import CampaignOpsUser, SMMProgramRecord, SMMTimelineRowRecord

DEFAULT_SMM_ACTIONS = (
    "Hire creators",
    "Creators content is due",
    "Collect revised content from creators",
    "Upload content on Trello for client approval",
    "Send client Trello board for feedback/approvals",
    "Client send feedback/approvals through Trello",
    "Make sure content folder is up to date for client",
)


def sort_smm_timeline_rows(rows: Iterable[SMMTimelineRowRecord]) -> list[SMMTimelineRowRecord]:
    return sorted(
        (row for row in rows if getattr(row, "is_active", True)),
        key=lambda row: (
            row.due_date is None,
            row.due_date or date.max,
            getattr(row, "sequence_order", 0),
            str(getattr(row, "id", "")),
        ),
    )


class SMMTimelineService(CampaignOpsService):

    def _manager_name(self, program_id: str) -> str:
        workstreams = self.repository.list_workstreams_by_program(program_id)
        smm_workstream = next((ws for ws in workstreams if ws.workstream_type == WorkstreamType.SMM.value), None)
        if smm_workstream is None or not smm_workstream.owner_user_id:
            return "Ava"
        user = self.repository.get_user_by_id(smm_workstream.owner_user_id)
        return user.display_name if user else "Ava"

    def _baseline_rows(self, smm_program_id: str, program_id: str) -> list[dict]:
        manager_name = self._manager_name(program_id)
        rows = [
            {"action": action, "done": False, "due_date": None, "program_notes": None}
            for action in DEFAULT_SMM_ACTIONS
        ]
        rows.append(
            {
                "action": f"{manager_name} be checking DM's, responding/filtering comments, etc. DAILY",
                "done": False,
                "due_date": None,
                "program_notes": None,
            }
        )
        return [{"smm_program_id": smm_program_id, **row, "sequence_order": index + 1} for index, row in enumerate(rows)]

    def initialize_program(self, actor: CampaignOpsUser | None, program_id: str):
        # Production constructs this service with repository=None. Resolve the existing
        # repository API for reads; the write path still obtains a transaction-bound one.
        repository = self.repository or CampaignOpsRepository()
        require_program_access(repository, actor, program_id, active_only=True)
        existing = repository.get_smm_program_by_program(program_id)
        if existing:
            return existing, repository.list_smm_timeline_rows(existing.id)
        def operation(repo):
            repo.lock_program(program_id)
            return SMMTimelineService(repo)._initialize(actor, program_id)
        return self._transaction(operation)

    def _initialize(self, actor, program_id):
        program = require_program_access(self.repository, actor, program_id, active_only=True)
        if program is None:
            raise ValueError("Program not found")
        existing = self.repository.get_smm_program_by_program(program_id)
        if existing is not None:
            rows = self.repository.list_smm_timeline_rows(existing.id)
            return existing, rows
        workstream = next(
            (ws for ws in self.repository.list_workstreams_by_program(program_id) if ws.workstream_type == WorkstreamType.SMM.value),
            None,
        )
        if workstream is None:
            raise ValueError("SMM workstream missing")
        workspace = self.repository.create_smm_program(program_id, workstream.id, actor_user_id=getattr(actor, "id", None))
        created_rows = []
        for row in self._baseline_rows(workspace.id, program_id):
            created_rows.append(
                self.repository.create_smm_timeline_row(
                    row["smm_program_id"],
                    row["action"],
                    due_date=row["due_date"],
                    program_notes=row["program_notes"],
                    done=row["done"],
                    sequence_order=row["sequence_order"],
                    actor_user_id=getattr(actor, "id", None),
                )
            )
        return workspace, created_rows

    def workspace(self, actor: CampaignOpsUser | None, program_id: str):
        return self.initialize_program(actor, program_id)

    def get_workspace(self, actor: CampaignOpsUser | None, program_id: str):
        return self.initialize_program(actor, program_id)

    def timeline_rows(self, program_id: str):
        return self.fetch_rows(program_id)

    def get_row(self, row_id: str):
        return self.repository.get_smm_timeline_row(row_id)

    def fetch_rows(self, program_id: str):
        workspace = self.repository.get_smm_program_by_program(program_id)
        if workspace is None:
            return []
        return self.repository.list_smm_timeline_rows(workspace.id)

    def seed_baseline(self, actor: CampaignOpsUser | None, program_id: str):
        workspace, rows = self.initialize_program(actor, program_id)
        return workspace, rows

    def create_row(self, actor: CampaignOpsUser | None, smm_program_id: str, action: str, due_date=None, program_notes=None, done=False):
        return self.repository.create_smm_timeline_row(
            smm_program_id,
            action,
            due_date=due_date,
            program_notes=program_notes,
            done=done,
            sequence_order=self.repository.list_smm_timeline_rows(smm_program_id, include_inactive=True).__len__() + 1,
            actor_user_id=getattr(actor, "id", None),
        )

    def update_row(self, actor: CampaignOpsUser | None, row_id: str, **kwargs):
        return self.repository.update_smm_timeline_row(
            row_id,
            actor_user_id=getattr(actor, "id", None),
            **kwargs,
        )

    def remove_row(self, actor: CampaignOpsUser | None, row_id: str):
        self.repository.deactivate_smm_timeline_row(row_id, actor_user_id=getattr(actor, "id", None))

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
                   if w.is_active and w.workstream_type == WorkstreamType.SMM.value]
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

    def save_changes(self, actor, program_id, records, original_rows, original_assignments, lead_id, manager_id):
        """Validate the draft, then persist rows and ownership in one transaction."""
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
        ids = [r["id"] for r in edited if r["id"]]
        if len(ids) != len(set(ids)) or any(i not in original for i in ids):
            raise CampaignOpsValidationError("Timeline row identity is invalid. Reopen the Program.")
        def operation(repo):
            repo.lock_program(program_id)
            require_program_access(repo, actor, program_id, active_only=True)
            scoped = SMMTimelineService(repo)
            ownership = scoped.assignment_state(actor, program_id)
            if ownership != original_assignments:
                raise CampaignOpsValidationError("Assignments changed. Reopen the Program before saving.")
            lead_changed = lead_id != ownership["lead_id"]
            manager_changed = manager_id != ownership["manager_id"]
            if lead_changed or manager_changed:
                self._require_admin(actor)
                for changed, user_id, role in ((lead_changed, lead_id, "lead_owner"), (manager_changed, manager_id, "manager")):
                    if changed and user_id not in {u.id for u in repo.list_workflow_role_users("smm", role)}:
                        raise CampaignOpsValidationError("Choose an eligible active owner or manager.")
            workspace = repo.get_smm_program_by_program(program_id)
            if workspace is None:
                raise CampaignOpsValidationError("Workspace is unavailable.")
            all_rows = repo.list_smm_timeline_rows(workspace.id, include_inactive=True)
            current = {r.id: r for r in all_rows if r.is_active}
            if {i: self._row_state(r) for i, r in current.items()} != original:
                raise CampaignOpsValidationError("Timeline changed. Reopen the Program before saving.")
            order = max((r.sequence_order for r in all_rows), default=0)
            counts = {"updated": 0, "added": 0, "removed": 0}
            for row in edited:
                payload = {k: v for k, v in row.items() if k != "id"}
                if row["id"]:
                    before = current[row["id"]]
                    if (before.due_date, before.action, bool(before.done), before.program_notes or "") == (
                            row["due_date"], row["action"], row["done"], row["program_notes"]):
                        continue
                    repo.update_smm_timeline_row(row["id"], actor_user_id=actor.id, **payload)
                    counts["updated"] += 1
                else:
                    order += 1
                    repo.create_smm_timeline_row(workspace.id, sequence_order=order, actor_user_id=actor.id, **payload)
                    counts["added"] += 1
            for row_id in set(original) - set(ids):
                repo.deactivate_smm_timeline_row(row_id, actor_user_id=actor.id)
                counts["removed"] += 1
            if lead_changed:
                scoped.reassign_primary_program_owner(actor, program_id, lead_id)
            if manager_changed:
                scoped.reassign_workstream_lead(actor, program_id, ownership["workstream_id"], manager_id)
            counts.update(owner_changed=int(lead_changed), manager_changed=int(manager_changed))
            return counts
        return self._transaction(operation)
