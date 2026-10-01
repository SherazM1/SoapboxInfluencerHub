from __future__ import annotations

import unittest
from tests.operational_editor_helpers import apply_edits, edit, field, draft_records

from streamlit.testing.v1 import AppTest

from core.campaign_ops.enums import WorkstreamType


def smm_app():
    import streamlit as st

    from app.campaign_ops.smm.views import render_smm
    from core.campaign_ops.enums import WorkstreamType
    from core.campaign_ops.service import CampaignOpsService
    from tests.test_campaign_ops_foundation import FakePrompt4ARepository

    if "smm_fixture" not in st.session_state:
        repo = FakePrompt4ARepository()
        service = CampaignOpsService(repository=repo)
        bailey = repo.users[0]
        repo.get_user_by_display_name("Taylor").display_name = "Taylor"
        taylor = next(user for user in repo.users if user.display_name == "Taylor")
        ava = next(user for user in repo.users if user.display_name == "Ava")
        program_id = service.create_program_with_workstreams_and_assignments(
            actor=bailey,
            program_name="SMM Program",
            new_client_name="Client",
            primary_workstream_type=WorkstreamType.SMM.value,
            primary_owner_user_id=taylor.id,
            workstream_types=[WorkstreamType.SMM.value],
            workstream_lead_user_ids={WorkstreamType.SMM.value: ava.id},
        )
        st.session_state["smm_fixture"] = (repo, service, bailey, program_id)

    repo, service, actor, program_id = st.session_state["smm_fixture"]
    render_smm(actor, service, program_id)


class SMMEditorTests(unittest.TestCase):
    def test_smm_workspace_renders_with_expected_columns_and_buttons(self):
        app = AppTest.from_function(smm_app, default_timeout=20).run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(["Lead Owner", "Manager"], [item.label for item in app.selectbox[:2]])
        self.assertEqual(["Taylor", "Ava"], app.selectbox[0].options)
        self.assertEqual(["Ava", "Maren"], app.selectbox[1].options)
        self.assertIn("Save Changes", [button.label for button in app.button])
        self.assertNotIn("Save Owner", [button.label for button in app.button])
        self.assertNotIn("Save Manager", [button.label for button in app.button])
        self.assertEqual(["Date", "Action", "Done", "Program Notes"], [w.value.strip("*") for w in app.markdown if w.value in ("**Date**", "**Action**", "**Done**", "**Program Notes**")])

    def test_smm_owner_and_row_changes_persist_once(self):
        initial_table_state = {
            "edited_rows": {0: {"Date": "2026-01-05", "Action": "Updated SMM action", "Done": True, "Program Notes": "Reviewed"}},
            "added_rows": [{"Date": "2026-01-10", "Action": "Custom SMM action", "Done": True, "Program Notes": "Ready"}],
            "deleted_rows": [1],
        }
        app = AppTest.from_function(smm_app, default_timeout=20).run()
        repo, service, actor, program_id = app.session_state.smm_fixture
        current = next(ws for ws in repo.workstreams if ws.program_id == program_id and ws.workstream_type == WorkstreamType.SMM.value)
        apply_edits(app, initial_table_state)
        ava = next(user for user in repo.list_workflow_role_users(WorkstreamType.SMM.value, "lead_owner") if user.display_name == "Ava")
        maren = next(user for user in repo.list_workflow_role_users(WorkstreamType.SMM.value, "manager") if user.display_name == "Maren")
        app.selectbox[0].select(ava.id)
        app.selectbox[1].select(maren.id)
        next(button for button in app.button if button.label == "Save Changes").click().run()
        self.assertEqual([], list(app.exception))
        summary = service.get_program_workspace_summary(actor, program_id)
        lead = next(a for a in summary.assignments if a.is_active and a.is_primary and a.assignment_role == "program_owner")
        self.assertEqual(ava.id, lead.user_id)
        self.assertEqual(maren.id, current.owner_user_id)
        manager_assignment = next(
            assignment
            for assignment in summary.assignments
            if assignment.is_active
            and assignment.workstream_id == current.id
            and assignment.assignment_role == "workstream_lead"
        )
        self.assertEqual(maren.id, manager_assignment.user_id)
        rows = repo.list_smm_timeline_rows(repo.get_smm_program_by_program(program_id).id)
        self.assertEqual(8, len(rows))
        self.assertFalse(any(row.action == "Creators content is due" for row in rows))
        edited_row = next(row for row in rows if row.action == "Updated SMM action")
        self.assertEqual("2026-01-05", edited_row.due_date.isoformat())
        self.assertTrue(edited_row.done)
        self.assertEqual("Reviewed", edited_row.program_notes)
        added_row = next(row for row in rows if row.action == "Custom SMM action")
        self.assertEqual("2026-01-10", added_row.due_date.isoformat())
        self.assertTrue(added_row.done)
        self.assertEqual("Ready", added_row.program_notes)


if __name__ == "__main__":
    unittest.main()
