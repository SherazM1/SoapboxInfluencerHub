from __future__ import annotations

from datetime import date
from unittest import TestCase

from core.campaign_ops.content_management_timeline import (
    DEFAULT_CONTENT_MANAGEMENT_ACTIONS,
    ContentManagementTimelineService,
    sort_content_management_timeline_rows,
)
from core.campaign_ops.enums import AssignmentRole, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsPermissionError
from core.campaign_ops.models import CampaignOpsUser, Program, ProgramAssignment, Workstream
from core.campaign_ops.program_routing import ProgramRoutingService


class ContentTimelineRepository:
    def __init__(self):
        self.users = [
            CampaignOpsUser(id="admin", display_name="Admin", role="administrator"),
            CampaignOpsUser(id="lead", display_name="Lead", role="team_member"),
            CampaignOpsUser(id="manager", display_name="Manager", role="team_member"),
            CampaignOpsUser(id="roster-only", display_name="Roster only", role="team_member"),
        ]
        self.program = Program(
            id="program", program_name="Content Program", status="active",
            primary_workstream_type=WorkstreamType.ECOMMERCE.value,
        )
        self.workstream = Workstream(
            id="workstream", program_id="program", workstream_type=WorkstreamType.ECOMMERCE.value,
            owner_user_id="manager",
        )
        self.assignments = [
            ProgramAssignment("a-lead", "program", "lead", AssignmentRole.PROGRAM_OWNER.value, is_primary=True),
            ProgramAssignment("a-manager", "program", "manager", AssignmentRole.WORKSTREAM_LEAD.value,
                              workstream_id="workstream"),
        ]
        self.workspaces = []
        self.rows = []
        self.writes = 0

    def get_program(self, program_id):
        return self.program if program_id == self.program.id else None

    def lock_program(self, program_id):
        return self.get_program(program_id)

    def list_assignments_by_program(self, program_id):
        return self.assignments

    def list_workstreams_by_program(self, program_id):
        return [self.workstream]

    def get_content_management_program_by_program(self, program_id):
        return next((item for item in self.workspaces if item.program_id == program_id and item.is_active), None)

    def get_content_management_program(self, workspace_id):
        return next((item for item in self.workspaces if item.id == workspace_id), None)

    def list_content_management_programs_by_program(self, program_id):
        workspace = self.get_content_management_program_by_program(program_id)
        return [workspace] if workspace else []

    def create_content_management_program(self, program_id, workstream_id, actor_user_id=None):
        self.writes += 1
        item = type("Workspace", (), {"id": "workspace", "program_id": program_id,
            "workstream_id": workstream_id, "is_active": True})()
        self.workspaces.append(item)
        return item

    def list_content_management_timeline_rows(self, workspace_id, include_inactive=False):
        return [row for row in self.rows if row.content_management_program_id == workspace_id
                and (include_inactive or row.is_active)]

    def create_content_management_timeline_row(self, workspace_id, action, due_date=None,
            program_notes=None, done=False, sequence_order=0, actor_user_id=None):
        self.writes += 1
        row = type("TimelineRow", (), {"id": f"row-{len(self.rows) + 1}",
            "content_management_program_id": workspace_id, "action": action, "due_date": due_date,
            "done": done, "program_notes": program_notes, "sequence_order": sequence_order,
            "is_active": True})()
        self.rows.append(row)
        return row

    def update_content_management_timeline_row(self, row_id, **kwargs):
        self.writes += 1
        row = next(item for item in self.rows if item.id == row_id)
        for key, value in kwargs.items():
            setattr(row, key, value)
        return row

    def deactivate_content_management_timeline_row(self, row_id, actor_user_id=None):
        self.writes += 1
        next(item for item in self.rows if item.id == row_id).is_active = False

    def list_workflow_role_users(self, workflow, role):
        if workflow != WorkstreamType.ECOMMERCE.value:
            return []
        user_id = "lead" if role == "lead_owner" else "manager"
        if role == "lead_owner":
            return [user for user in self.users if user.id in {"lead", "roster-only"}]
        return [user for user in self.users if user.id == user_id]

    def get_user_by_id(self, user_id):
        return next((user for user in self.users if user.id == user_id), None)


class ContentManagementTimelineTests(TestCase):
    def setUp(self):
        self.repository = ContentTimelineRepository()
        self.service = ContentManagementTimelineService(self.repository)
        self.admin = self.repository.users[0]

    def test_initializes_exact_baseline_and_reopen_is_idempotent(self):
        workspace, rows = self.service.initialize_program(self.admin, "program")
        reopened, reopened_rows = self.service.initialize_program(self.admin, "program")
        self.assertEqual("workspace", workspace.id)
        self.assertEqual(workspace.id, reopened.id)
        self.assertEqual(DEFAULT_CONTENT_MANAGEMENT_ACTIONS, tuple(row.action for row in rows))
        self.assertEqual(10, len(rows))
        self.assertEqual(10, len(reopened_rows))
        self.assertTrue(all(row.due_date is None and row.done is False for row in rows))
        self.assertEqual(11, self.repository.writes)

    def test_reopen_does_not_reseed_deleted_or_restore_edited_actions(self):
        workspace, rows = self.service.initialize_program(self.admin, "program")
        rows[0].action = "Edited baseline wording"
        self.repository.deactivate_content_management_timeline_row(rows[1].id)
        reopened, active_rows = self.service.initialize_program(self.admin, "program")
        self.assertEqual(workspace.id, reopened.id)
        self.assertEqual(9, len(active_rows))
        self.assertEqual("Edited baseline wording", active_rows[0].action)
        self.assertNotIn(rows[1].id, [row.id for row in active_rows])

    def test_sorting_uses_dates_stable_sequence_and_ignores_done(self):
        _, rows = self.service.initialize_program(self.admin, "program")
        rows[0].due_date = date(2026, 10, 7)
        rows[1].due_date = date(2026, 10, 1)
        rows[2].due_date = date(2026, 10, 1)
        rows[3].done = True
        ordered = sort_content_management_timeline_rows(rows)
        self.assertEqual([rows[1].id, rows[2].id, rows[0].id], [row.id for row in ordered[:3]])
        self.assertIsNone(ordered[3].due_date)

    def test_save_persists_free_text_fields_and_row_add_remove(self):
        workspace, rows = self.service.initialize_program(self.admin, "program")
        ownership = self.service.assignment_state(self.admin, "program")
        records = [{"_row_id": row.id, "Action": row.action, "Date": row.due_date,
                    "Done": row.done, "Program Notes": row.program_notes or ""} for row in rows]
        records[0].update({"Action": "Edited freely", "Date": date(2026, 10, 7),
                           "Done": True, "Program Notes": "Saved note"})
        records.pop(1)
        records.append({"_row_id": None, "Action": "A new free-form step", "Date": None,
                        "Done": False, "Program Notes": ""})
        before_save_writes = self.repository.writes
        counts = self.service.save_changes(self.admin, "program", records, rows, ownership,
                                           "lead", "manager")
        self.assertEqual(before_save_writes + 3, self.repository.writes)
        self.assertEqual({"updated": 1, "added": 1, "removed": 1,
                          "owner_changed": 0, "manager_changed": 0}, counts)
        changed = next(row for row in self.repository.rows if row.id == rows[0].id)
        self.assertEqual("Edited freely", changed.action)
        self.assertEqual(date(2026, 10, 7), changed.due_date)
        self.assertTrue(changed.done)
        self.assertEqual("Saved note", changed.program_notes)
        self.assertFalse(next(row for row in self.repository.rows if row.id == rows[1].id).is_active)
        self.assertEqual(10, len(self.repository.list_content_management_timeline_rows(workspace.id)))

    def test_lead_manager_and_admin_access_uses_program_ownership(self):
        for user in self.repository.users[:3]:
            with self.subTest(user=user.id):
                _, rows = self.service.initialize_program(user, "program")
                self.assertEqual(10, len(rows))

    def test_roster_eligibility_alone_does_not_grant_access(self):
        with self.assertRaises(CampaignOpsPermissionError):
            self.service.initialize_program(self.repository.users[3], "program")

    def test_registry_route_resolves_to_one_operational_workspace(self):
        router = ProgramRoutingService(self.repository)
        first = router.resolve(self.admin, "program")
        second = router.resolve(self.repository.users[1], "program")
        self.assertEqual("eCommerce / Content", first.section)
        self.assertEqual("workspace", first.record_id)
        self.assertEqual(first.record_id, second.record_id)
        self.assertEqual(1, len(self.repository.workspaces))
        self.assertEqual(10, len(self.repository.rows))

    def test_direct_route_denies_roster_only_user(self):
        with self.assertRaises(CampaignOpsPermissionError):
            ProgramRoutingService(self.repository).resolve(self.repository.users[3], "program")
        self.assertEqual([], self.repository.workspaces)

    def test_reassignment_changes_access_through_central_program_policy(self):
        _, _ = self.service.initialize_program(self.admin, "program")
        old_manager, new_manager = self.repository.users[2], self.repository.users[3]
        self.assertEqual("workspace", ProgramRoutingService(self.repository).resolve(old_manager, "program").record_id)
        self.repository.workstream.owner_user_id = new_manager.id
        next(
            assignment for assignment in self.repository.assignments
            if assignment.assignment_role == AssignmentRole.WORKSTREAM_LEAD.value
        ).is_active = False
        with self.assertRaises(CampaignOpsPermissionError):
            self.service.initialize_program(old_manager, "program")
        self.assertEqual("workspace", ProgramRoutingService(self.repository).resolve(new_manager, "program").record_id)
