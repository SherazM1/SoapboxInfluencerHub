from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from core.campaign_ops.enums import WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsValidationError
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.permissions import require_program_access
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService

DEFAULT_CONTENT_MANAGEMENT_ACTIONS = (
    "Campaign internal kick off with Account Managers, Seller, Designer, & eComm team",
    "eComm team to finalize PDP outline",
    "Graphic direction & rationale to be reviewed internally by eComm team",
    "Notify design team that graphic outline & rationale are ready to be put in deck",
    "Soapbox to deliver initial graphic direction & rationale",
    "Client to send feedback on initial graphic direction",
    "Photography to be ready for graphic designers",
    "Soapbox to send the 1st round of PDP graphics",
    "Client to send feedback on PDP graphics",
    "Soapbox to present to final photography, PDP graphics, & copy optimizations",
)


def sort_content_management_timeline_rows(rows: Iterable) -> list:
    return sorted(
        (row for row in rows if getattr(row, "is_active", True)),
        key=lambda row: (
            row.due_date is None,
            row.due_date or date.max,
            getattr(row, "sequence_order", 0),
            str(getattr(row, "id", "")),
        ),
    )


class ContentManagementTimelineService(CampaignOpsService):
    def initialize_program(self, actor: CampaignOpsUser | None, program_id: str):
        repository = self.repository or CampaignOpsRepository()
        program = require_program_access(repository, actor, program_id, active_only=True)
        if program.primary_workstream_type != WorkstreamType.ECOMMERCE.value:
            raise CampaignOpsValidationError("An active Content Management / eCommerce Program is required.")
        existing = repository.get_content_management_program_by_program(program_id)
        if existing is not None:
            return existing, repository.list_content_management_timeline_rows(existing.id)

        def operation(repo):
            repo.lock_program(program_id)
            return ContentManagementTimelineService(repo)._initialize(actor, program_id)

        return self._transaction(operation)

    def _initialize(self, actor, program_id):
        program = require_program_access(self.repository, actor, program_id, active_only=True)
        if program.primary_workstream_type != WorkstreamType.ECOMMERCE.value:
            raise CampaignOpsValidationError("An active Content Management / eCommerce Program is required.")
        existing = self.repository.get_content_management_program_by_program(program_id)
        if existing is not None:
            return existing, self.repository.list_content_management_timeline_rows(existing.id)
        workstreams = [
            workstream for workstream in self.repository.list_workstreams_by_program(program_id)
            if workstream.is_active and workstream.workstream_type == WorkstreamType.ECOMMERCE.value
        ]
        if len(workstreams) != 1:
            raise CampaignOpsValidationError("The Program must have exactly one active Content/eCommerce Workstream.")
        workspace = self.repository.create_content_management_program(
            program_id, workstreams[0].id, actor_user_id=getattr(actor, "id", None)
        )
        rows = [
            self.repository.create_content_management_timeline_row(
                workspace.id, action, sequence_order=index, actor_user_id=getattr(actor, "id", None)
            )
            for index, action in enumerate(DEFAULT_CONTENT_MANAGEMENT_ACTIONS, 1)
        ]
        return workspace, rows

    def assignment_state(self, actor, program_id):
        repo = self.repository or CampaignOpsRepository()
        require_program_access(repo, actor, program_id, active_only=True)
        assignments = repo.list_assignments_by_program(program_id)
        streams = [
            workstream for workstream in repo.list_workstreams_by_program(program_id)
            if workstream.is_active and workstream.workstream_type == WorkstreamType.ECOMMERCE.value
        ]
        leads = [
            assignment for assignment in assignments
            if assignment.is_active and assignment.is_primary
            and assignment.assignment_role == "program_owner" and assignment.workstream_id is None
        ]
        if len(streams) != 1 or len(leads) != 1:
            raise CampaignOpsValidationError("Resolve Program ownership before editing this workspace.")
        return {
            "lead_id": leads[0].user_id,
            "manager_id": streams[0].owner_user_id,
            "workstream_id": streams[0].id,
            "assignments": tuple(sorted(
                (assignment.id, assignment.user_id, assignment.assignment_role, assignment.is_primary)
                for assignment in assignments if assignment.is_active
            )),
        }

    @staticmethod
    def _row_state(row):
        return (row.id, row.due_date, row.action, bool(row.done), row.program_notes or "", row.sequence_order)

    def save_changes(self, actor, program_id, records, original_rows, original_assignments, lead_id, manager_id):
        edited = []
        for record in records:
            action = (record.get("Action") or "").strip()
            due = record.get("Date")
            done = record.get("Done", False)
            notes = record.get("Program Notes") or ""
            if not record.get("_row_id") and not any((action, due, done, notes)):
                continue
            if not action:
                raise CampaignOpsValidationError("Every row requires an action.")
            if due is not None and not isinstance(due, date):
                raise CampaignOpsValidationError("Choose a valid date or leave it blank.")
            if not isinstance(done, bool):
                raise CampaignOpsValidationError("Done must be a checkbox value.")
            edited.append({
                "id": record.get("_row_id"), "action": action, "due_date": due,
                "done": done, "program_notes": notes,
            })

        original = {row.id: self._row_state(row) for row in original_rows}
        ids = [row["id"] for row in edited if row["id"]]
        if len(ids) != len(set(ids)) or any(row_id not in original for row_id in ids):
            raise CampaignOpsValidationError("Timeline row identity is invalid. Reopen the Program.")

        def operation(repo):
            repo.lock_program(program_id)
            require_program_access(repo, actor, program_id, active_only=True)
            scoped = ContentManagementTimelineService(repo)
            ownership = scoped.assignment_state(actor, program_id)
            if ownership != original_assignments:
                raise CampaignOpsValidationError("Assignments changed. Reopen the Program before saving.")
            lead_changed = lead_id != ownership["lead_id"]
            manager_changed = manager_id != ownership["manager_id"]
            if lead_changed or manager_changed:
                self._require_admin(actor)
                for changed, user_id, role in (
                    (lead_changed, lead_id, "lead_owner"),
                    (manager_changed, manager_id, "manager"),
                ):
                    if changed and user_id not in {
                        user.id for user in repo.list_workflow_role_users("ecommerce", role)
                    }:
                        raise CampaignOpsValidationError("Choose an eligible active owner or manager.")

            workspace = repo.get_content_management_program_by_program(program_id)
            if workspace is None:
                raise CampaignOpsValidationError("Workspace is unavailable.")
            all_rows = repo.list_content_management_timeline_rows(workspace.id, include_inactive=True)
            current = {row.id: row for row in all_rows if row.is_active}
            if {key: self._row_state(row) for key, row in current.items()} != original:
                raise CampaignOpsValidationError("Timeline changed. Reopen the Program before saving.")

            order = max((row.sequence_order for row in all_rows), default=0)
            counts = {"updated": 0, "added": 0, "removed": 0}
            for row in edited:
                payload = {key: value for key, value in row.items() if key != "id"}
                if row["id"]:
                    before = current[row["id"]]
                    if (before.due_date, before.action, bool(before.done), before.program_notes or "") == (
                        row["due_date"], row["action"], row["done"], row["program_notes"]
                    ):
                        continue
                    repo.update_content_management_timeline_row(
                        row["id"], actor_user_id=actor.id, **payload
                    )
                    counts["updated"] += 1
                else:
                    order += 1
                    repo.create_content_management_timeline_row(
                        workspace.id, sequence_order=order, actor_user_id=actor.id, **payload
                    )
                    counts["added"] += 1
            for row_id in set(original) - set(ids):
                repo.deactivate_content_management_timeline_row(row_id, actor_user_id=actor.id)
                counts["removed"] += 1
            if lead_changed:
                scoped.reassign_primary_program_owner(actor, program_id, lead_id)
            if manager_changed:
                scoped.reassign_workstream_lead(actor, program_id, ownership["workstream_id"], manager_id)
            counts.update(owner_changed=int(lead_changed), manager_changed=int(manager_changed))
            return counts

        return self._transaction(operation)
