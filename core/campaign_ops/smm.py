from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from types import SimpleNamespace

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


class SMMTimelineService:
    def __init__(self, repository):
        self.repository = repository

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
        program = self.repository.get_program(program_id)
        if program is None:
            raise ValueError("Program not found")
        existing = self.repository.get_smm_program_by_program(program_id)
        if existing is not None:
            rows = self.repository.list_smm_timeline_rows(existing.id)
            if len(rows) == 8:
                return existing, rows
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
