from __future__ import annotations

from datetime import date
import unittest

from core.campaign_ops.enums import WorkflowRole, WorkstreamType
from core.campaign_ops.models import CampaignOpsUser, Program, Workstream
from core.campaign_ops.smm import DEFAULT_SMM_ACTIONS, SMMTimelineService, sort_smm_timeline_rows


class SMMFakeRepository:
    def __init__(self):
        self.users = [
            CampaignOpsUser(id="u-admin", display_name="Bailey", role="administrator"),
            CampaignOpsUser(id="u-taylor", display_name="Taylor", role="team_member"),
            CampaignOpsUser(id="u-ava", display_name="Ava", role="team_member"),
            CampaignOpsUser(id="u-maren", display_name="Maren", role="team_member"),
        ]
        self.programs = [Program(id="p-1", program_name="SMM Program")]
        self.workstreams = [
            Workstream(id="ws-1", program_id="p-1", workstream_type=WorkstreamType.SMM.value, owner_user_id="u-ava")
        ]
        self.smm_programs = []
        self.smm_rows = []

    def lock_program(self, program_id):
        return self.get_program(program_id)

    def get_program(self, program_id):
        return next((program for program in self.programs if program.id == program_id), None)

    def list_workstreams_by_program(self, program_id):
        return [ws for ws in self.workstreams if ws.program_id == program_id and ws.is_active]

    def list_workflow_role_users(self, workflow_key, workflow_role):
        if workflow_key == WorkstreamType.SMM.value and workflow_role == WorkflowRole.LEAD_OWNER.value:
            return [user for user in self.users if user.id in {"u-taylor", "u-ava"}]
        if workflow_key == WorkstreamType.SMM.value and workflow_role == WorkflowRole.MANAGER.value:
            return [user for user in self.users if user.id in {"u-ava", "u-maren"}]
        return []

    def get_user_by_id(self, user_id):
        return next((user for user in self.users if user.id == user_id), None)

    def get_smm_program_by_program(self, program_id):
        return next((workspace for workspace in self.smm_programs if workspace.program_id == program_id and workspace.is_active), None)

    def create_smm_program(self, program_id, workstream_id, actor_user_id=None):
        workspace = type("SMMProgramRecord", (), {"id": f"smm-{len(self.smm_programs)+1}", "program_id": program_id, "workstream_id": workstream_id, "is_active": True})()
        self.smm_programs.append(workspace)
        return workspace

    def list_smm_timeline_rows(self, smm_program_id, include_inactive=False):
        rows = [row for row in self.smm_rows if row.smm_program_id == smm_program_id]
        if not include_inactive:
            rows = [row for row in rows if row.is_active]
        return rows

    def get_smm_timeline_row(self, row_id):
        return next((row for row in self.smm_rows if row.id == row_id), None)

    def create_smm_timeline_row(self, smm_program_id, action, due_date=None, program_notes=None, done=False, sequence_order=0, actor_user_id=None):
        row = type(
            "SMMTimelineRow",
            (),
            {
                "id": f"row-{len(self.smm_rows)+1}",
                "smm_program_id": smm_program_id,
                "due_date": due_date,
                "action": action,
                "done": done,
                "program_notes": program_notes,
                "sequence_order": sequence_order,
                "is_active": True,
            },
        )()
        self.smm_rows.append(row)
        return row

    def update_smm_timeline_row(self, row_id, **kwargs):
        row = next((item for item in self.smm_rows if item.id == row_id), None)
        if row is None:
            raise ValueError("row not found")
        for key, value in kwargs.items():
            setattr(row, key, value)
        return row

    def deactivate_smm_timeline_row(self, row_id, actor_user_id=None):
        row = next((item for item in self.smm_rows if item.id == row_id), None)
        if row is None:
            raise ValueError("row not found")
        row.is_active = False


class SMMWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.repo = SMMFakeRepository()
        self.service = SMMTimelineService(self.repo)

    def test_smm_workspace_initializes_and_reuses_one_record(self):
        workspace, rows = self.service.initialize_program(self.repo.users[0], "p-1")
        self.assertEqual("p-1", workspace.program_id)
        self.assertEqual(1, len([entry for entry in self.repo.smm_programs if entry.program_id == "p-1"]))
        self.assertEqual(8, len(rows))
        workspace_again, rows_again = self.service.initialize_program(self.repo.users[0], "p-1")
        self.assertEqual(workspace.id, workspace_again.id)
        self.assertEqual(len(rows), len(rows_again))

    def test_baseline_defaults_and_dynamic_manager_action(self):
        _, rows = self.service.initialize_program(self.repo.users[0], "p-1")
        self.assertEqual(DEFAULT_SMM_ACTIONS, tuple(row.action for row in rows[:7]))
        self.assertEqual("Ava be checking DM's, responding/filtering comments, etc. DAILY", rows[7].action)
        self.assertTrue(all(row.due_date is None for row in rows))
        self.assertTrue(all(not row.done for row in rows))
        self.assertTrue(all(row.program_notes in (None, "") for row in rows))

    def test_sorting_and_done_are_independent(self):
        _, rows = self.service.initialize_program(self.repo.users[0], "p-1")
        rows[0].due_date = date(2026, 1, 5)
        rows[1].due_date = date(2026, 1, 1)
        rows[2].done = True
        rows[3].due_date = date(2026, 1, 1)
        ordered = sort_smm_timeline_rows(rows)
        self.assertEqual([rows[1].id, rows[3].id, rows[0].id, rows[2].id, rows[4].id, rows[5].id, rows[6].id, rows[7].id], [row.id for row in ordered])
        self.assertTrue(ordered[0].done is False)

    def test_row_create_update_and_remove(self):
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
