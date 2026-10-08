from __future__ import annotations

from datetime import date
import unittest

from core.campaign_ops.enums import WorkflowRole, WorkstreamType
from core.campaign_ops.models import CampaignOpsUser, Program, Workstream
from core.campaign_ops.retail_media_timeline import (
    DEFAULT_GENERAL_RETAIL_MEDIA_ACTIONS,
    DEFAULT_INCOMM_RETAIL_MEDIA_ACTIONS,
    RetailMediaTimelineService,
    sort_retail_media_timeline_rows,
)


class RetailMediaFakeRepository:
    def __init__(self):
        self.users = [
            CampaignOpsUser(id="u-admin", display_name="Bailey", role="administrator"),
            CampaignOpsUser(id="u-chloe", display_name="Chloe", role="team_member"),
            CampaignOpsUser(id="u-jordan", display_name="Jordan", role="team_member"),
        ]
        self.programs = [Program(id="p-1", program_name="Retail Program")]
        self.workstreams = [
            Workstream(id="ws-1", program_id="p-1", workstream_type=WorkstreamType.RETAIL_MEDIA.value, owner_user_id="u-chloe")
        ]
        self.retail_programs = []
        self.retail_rows = []

    def list_workflow_role_users(self, workflow_key, workflow_role):
        if workflow_key == WorkstreamType.RETAIL_MEDIA.value and workflow_role == WorkflowRole.LEAD_OWNER.value:
            return [user for user in self.users if user.id in {"u-chloe"}]
        if workflow_key == WorkstreamType.RETAIL_MEDIA.value and workflow_role == WorkflowRole.MANAGER.value:
            return [user for user in self.users if user.id in {"u-chloe"}]
        return []

    def lock_program(self, program_id):
        return next((program for program in self.programs if program.id == program_id), None)

    def get_program(self, program_id):
        return next((program for program in self.programs if program.id == program_id), None)

    def list_workstreams_by_program(self, program_id):
        return [ws for ws in self.workstreams if ws.program_id == program_id and ws.is_active]

    def get_retail_media_program_by_program(self, program_id):
        return next((workspace for workspace in self.retail_programs if workspace.program_id == program_id and workspace.is_active), None)

    def create_retail_media_program(self, program_id, workstream_id, retail_type="general", actor_user_id=None):
        workspace = type(
            "RetailMediaProgramRecord",
            (),
            {
                "id": f"rm-{len(self.retail_programs) + 1}",
                "program_id": program_id,
                "workstream_id": workstream_id,
                "retail_type": retail_type,
                "is_active": True,
            },
        )()
        self.retail_programs.append(workspace)
        return workspace

    def list_retail_media_timeline_rows(self, retail_program_id, include_inactive=False):
        rows = [row for row in self.retail_rows if row.retail_media_program_id == retail_program_id]
        if not include_inactive:
            rows = [row for row in rows if row.is_active]
        return rows

    def create_retail_media_timeline_row(self, retail_media_program_id, action, due_date=None, program_notes=None, done=False, sequence_order=0, actor_user_id=None):
        row = type(
            "RetailMediaTimelineRow",
            (),
            {
                "id": f"row-{len(self.retail_rows) + 1}",
                "retail_media_program_id": retail_media_program_id,
                "due_date": due_date,
                "action": action,
                "done": done,
                "program_notes": program_notes,
                "sequence_order": sequence_order,
                "is_active": True,
            },
        )()
        self.retail_rows.append(row)
        return row

    def update_retail_media_timeline_row(self, row_id, **kwargs):
        row = next((item for item in self.retail_rows if item.id == row_id), None)
        if row is None:
            raise ValueError("row not found")
        for key, value in kwargs.items():
            setattr(row, key, value)
        return row

    def deactivate_retail_media_timeline_row(self, row_id, actor_user_id=None):
        row = next((item for item in self.retail_rows if item.id == row_id), None)
        if row is None:
            raise ValueError("row not found")
        row.is_active = False

    def get_retail_media_timeline_row(self, row_id):
        return next((row for row in self.retail_rows if row.id == row_id), None)


class RetailMediaTimelineTests(unittest.TestCase):
    def setUp(self):
        self.repo = RetailMediaFakeRepository()
        self.service = RetailMediaTimelineService(self.repo)

    def test_general_workspace_initializes_with_12_rows(self):
        workspace, rows = self.service.initialize_program(self.repo.users[0], "p-1")
        self.assertEqual("p-1", workspace.program_id)
        self.assertEqual("general", workspace.retail_type)
        self.assertEqual(12, len(rows))
        self.assertEqual(DEFAULT_GENERAL_RETAIL_MEDIA_ACTIONS, tuple(row.action for row in rows))

    def test_incomm_workspace_initializes_with_18_rows_and_general_suffix(self):
        workspace, rows = self.service.initialize_program(self.repo.users[0], "p-1", retail_type="incomm")
        self.assertEqual("incomm", workspace.retail_type)
        self.assertEqual(18, len(rows))
        self.assertEqual(DEFAULT_INCOMM_RETAIL_MEDIA_ACTIONS, tuple(row.action for row in rows[:6]))
        self.assertEqual(DEFAULT_GENERAL_RETAIL_MEDIA_ACTIONS, tuple(row.action for row in rows[6:]))

    def test_sorting_keeps_done_separate_from_ordering(self):
        _, rows = self.service.initialize_program(self.repo.users[0], "p-1")
        rows[0].due_date = date(2026, 1, 5)
        rows[1].due_date = date(2026, 1, 1)
        rows[2].done = True
        rows[3].due_date = date(2026, 1, 1)
        ordered = sort_retail_media_timeline_rows(rows)
        self.assertEqual([rows[1].id, rows[3].id, rows[0].id, rows[2].id, rows[4].id, rows[5].id, rows[6].id, rows[7].id, rows[8].id, rows[9].id, rows[10].id, rows[11].id], [row.id for row in ordered[:12]])
        self.assertFalse(ordered[0].done)

    def test_update_and_remove_row(self):
        workspace, _ = self.service.initialize_program(self.repo.users[0], "p-1")
        row = self.service.create_row(self.repo.users[0], workspace.id, "Custom action", due_date=date(2026, 2, 1), program_notes="hello")
        self.assertEqual("Custom action", row.action)
        updated = self.service.update_row(self.repo.users[0], row.id, action="Edited action", done=True, due_date=None, program_notes="updated")
        self.assertEqual("Edited action", updated.action)
        self.assertTrue(updated.done)
        self.service.remove_row(self.repo.users[0], row.id)
        self.assertFalse(self.service.get_row(row.id).is_active)


if __name__ == "__main__":
    unittest.main()
