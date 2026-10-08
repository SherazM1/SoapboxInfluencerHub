from __future__ import annotations

import unittest
from datetime import date
from streamlit.testing.v1 import AppTest
from unittest.mock import patch
from core.campaign_ops.enums import WorkstreamType
from tests.test_campaign_ops_roster_new_program import button, selectbox, text_input


def page_app():
    import streamlit as st
    from unittest.mock import patch
    from app.pages import campaigns
    from core.campaign_ops.db import CampaignOpsSetupStatus
    from core.campaign_ops.service import CampaignOpsService
    from tests.test_campaign_ops_roster_new_program import RosterRepository

    if "roster_repo" not in st.session_state:
        st.session_state.roster_repo = RosterRepository()
    repo = st.session_state.roster_repo
    status = CampaignOpsSetupStatus("initialized", True, True, True, True, "Ready")
    with patch.object(campaigns, "CampaignOpsRepository", return_value=repo), \
         patch.object(campaigns, "CampaignOpsService", return_value=CampaignOpsService(repo)), \
         patch.object(campaigns, "get_campaign_ops_setup_status", return_value=status), \
         patch("app.campaign_ops.program_workspace.CampaignOpsService", return_value=CampaignOpsService(repo)):
        campaigns.main()


class NewProgramFlowTests(unittest.TestCase):
    def open_form(self):
        app = AppTest.from_function(page_app, default_timeout=20).run()
        button(app, "New Program").click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(["Client", "Program Name"], [w.label for w in app.text_input])
        self.assertEqual(["Workflow", "Lead Owner", "Manager"],
                         [w.label for w in app.selectbox if w.label != "Viewing as"])
        self.assertFalse(any(w.label == "Filters" for w in app.expander))
        return app

    def test_open_cancel_reopen_clears_draft_without_writes(self):
        app = self.open_form()
        text_input(app, "Client").set_value("Discard me").run()
        button(app, "Cancel").click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual("All Programs", app.session_state["campaign_ops_section"])
        self.assertFalse(app.session_state["campaign_ops_create_program_open"])
        self.assertEqual([], app.session_state.roster_repo.clients)
        self.assertEqual([], app.session_state.roster_repo.programs)
        button(app, "New Program").click().run()
        self.assertEqual("", text_input(app, "Client").value)

    def test_create_opens_workspace_and_returns_to_visible_portfolio(self):
        app = self.open_form()
        repo = app.session_state.roster_repo
        text_input(app, "Client").set_value("Test Client")
        text_input(app, "Program Name").set_value("Test Influencer Program")
        selectbox(app, "Lead Owner").select(repo.get_user_by_display_name("Taylor").id)
        selectbox(app, "Manager").select(repo.get_user_by_display_name("Allyn").id)
        button(app, "Create Program").click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(repo.programs))
        self.assertEqual(repo.influencer_campaigns[0].id, app.session_state["campaign_ops_selected_influencer_campaign_id"])
        self.assertEqual("Influencer", app.session_state["campaign_ops_section"])
        self.assertTrue(any(w.value == "Program created." for w in app.success))
        app._run(None)  # Fresh render: AppTest retains stale nodes across st.rerun().
        self.assertFalse(any(w.label == "Create Program" for w in app.button))
        self.assertFalse(any(k.startswith("campaign_ops_new_program_")
                             for k in app.session_state.filtered_state))
        button(app, "All Programs").click().run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any(w.value == "Test Influencer Program" for w in app.markdown))

    def test_create_smm_program_initializes_and_opens_smm_editor(self):
        from app.campaign_ops.formatting import WORKFLOW_LABELS

        app = self.open_form()
        repo = app.session_state.roster_repo
        text_input(app, "Client").set_value("SMM Client")
        text_input(app, "Program Name").set_value("New SMM Program")
        selectbox(app, "Workflow").select(WORKFLOW_LABELS["smm"]).run()
        selectbox(app, "Lead Owner").select(repo.get_user_by_display_name("Taylor").id)
        selectbox(app, "Manager").select(repo.get_user_by_display_name("Ava").id)
        button(app, "Create Program").click().run()

        self.assertFalse(app.exception)
        program_id = app.session_state["campaign_ops_selected_smm_program_id"]
        workspace = repo.get_smm_program_by_program(program_id)
        self.assertIsNotNone(workspace)
        self.assertEqual(1, len(repo.list_smm_programs_by_program(program_id)))
        self.assertEqual(8, len(repo.list_smm_timeline_rows(workspace.id)))
        self.assertEqual("Social Media Management", app.session_state["campaign_ops_section"])
        self.assertTrue(any(widget.label == "Save Changes" for widget in app.button))

    def test_section_content_creation_opens_operational_editor(self):
        from core.campaign_ops.content_management_timeline import DEFAULT_CONTENT_MANAGEMENT_ACTIONS
        from tests.operational_editor_helpers import edit

        app = AppTest.from_function(page_app, default_timeout=20).run()
        button(app, "eCommerce / Content").click().run()
        button(app, "New Content Program").click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(["Client", "Program Name"], [widget.label for widget in app.text_input])
        self.assertEqual({"Lead Owner", "Manager"},
                         {widget.label for widget in app.selectbox if widget.label != "Viewing as"})

        repository = app.session_state.roster_repo
        text_input(app, "Client").set_value("Content Client")
        text_input(app, "Program Name").set_value("PDP Launch")
        selectbox(app, "Lead Owner").select(repository.get_user_by_display_name("Emma").id)
        selectbox(app, "Manager").select(repository.get_user_by_display_name("Kate").id)
        button(app, "Create Program").click().run()

        self.assertEqual([], list(app.exception))
        program = repository.programs[0]
        workspace = repository.get_content_management_program_by_program(program.id)
        rows = repository.list_content_management_timeline_rows(workspace.id)
        self.assertEqual(WorkstreamType.ECOMMERCE.value, program.primary_workstream_type)
        self.assertEqual(DEFAULT_CONTENT_MANAGEMENT_ACTIONS, tuple(row.action for row in rows))
        self.assertEqual(10, len(rows))
        self.assertEqual([], repository.content_programs)
        self.assertEqual("eCommerce / Content", app.session_state["campaign_ops_section"])
        self.assertEqual(workspace.id, app.session_state["campaign_ops_selected_content_program_id"])
        self.assertTrue(any(widget.label == "Save Changes" for widget in app.button))
        self.assertFalse(any(widget.label == "Retail Type" for widget in app.selectbox))
        self.assertTrue(any(
            assignment.program_id == program.id and assignment.user_id == repository.get_user_by_display_name("Emma").id
            and assignment.assignment_role == "program_owner" and assignment.is_primary
            and assignment.workstream_id is None and assignment.is_active
            for assignment in repository.assignments
        ))
        workstream = next(item for item in repository.workstreams if item.program_id == program.id)
        self.assertEqual(repository.get_user_by_display_name("Kate").id, workstream.owner_user_id)
        self.assertTrue(any(
            assignment.program_id == program.id and assignment.workstream_id == workstream.id
            and assignment.user_id == workstream.owner_user_id and assignment.assignment_role == "workstream_lead"
            and assignment.is_active for assignment in repository.assignments
        ))

        with patch.object(repository, "update_content_management_timeline_row",
                          wraps=repository.update_content_management_timeline_row) as update_row, \
             patch.object(repository, "create_content_management_timeline_row",
                          wraps=repository.create_content_management_timeline_row) as create_row, \
             patch.object(repository, "deactivate_content_management_timeline_row",
                          wraps=repository.deactivate_content_management_timeline_row) as remove_row:
            edit(app, 0, **{"Date": "2026-10-15", "Action": "Edited free text",
                            "Done": True, "Program Notes": "Buffered until save"})
            button(app, "Add row").click().run()
            edit(app, 10, **{"Action": "New free-text action"})
            [widget for widget in app.button if widget.label == "×"][1].click().run()
            self.assertEqual([], list(app.exception))
            update_row.assert_not_called()
            create_row.assert_not_called()
            remove_row.assert_not_called()
            button(app, "Save Changes").click().run()
            self.assertEqual([], list(app.exception))
            update_row.assert_called_once()
            create_row.assert_called_once()
            remove_row.assert_called_once()

        active_rows = repository.list_content_management_timeline_rows(workspace.id)
        self.assertEqual(10, len(active_rows))
        edited = next(row for row in active_rows if row.action == "Edited free text")
        self.assertEqual(date(2026, 10, 15), edited.due_date)
        self.assertTrue(edited.done)
        self.assertEqual("Buffered until save", edited.program_notes)
        self.assertIn("New free-text action", [row.action for row in active_rows])

    def test_rosters_change_and_insights_can_be_canceled(self):
        from app.campaign_ops.formatting import WORKFLOW_LABELS
        from tests.test_campaign_ops_roster_new_program import ROSTER
        app = self.open_form()
        for workflow in ("ecommerce", "retail_media", "smm"):
            selectbox(app, "Workflow").select(WORKFLOW_LABELS[workflow]).run()
            for role, label in (("lead_owner", "Lead Owner"), ("manager", "Manager")):
                self.assertEqual(set(ROSTER[(workflow, role)]), set(selectbox(app, label).options))
                self.assertIsNone(selectbox(app, label).value)
        selectbox(app, "Workflow").select(WORKFLOW_LABELS["insights"]).run()
        self.assertFalse(any(w.label == "Create Program" for w in app.button))
        button(app, "Cancel").click().run()
        self.assertEqual("All Programs", app.session_state["campaign_ops_section"])

    def test_non_admin_cannot_render_creation_route(self):
        from app.campaign_ops.state import update_viewer_state
        from core.campaign_ops.models import CampaignOpsUser
        state = {"campaign_ops_previous_viewer": "Member", "campaign_ops_section": "New Program"}
        update_viewer_state(state, "Member", None)
        self.assertEqual("New Program", state["campaign_ops_section"])
        update_viewer_state(state, "Member", CampaignOpsUser(id="member", display_name="Member", role="team_member"))
        self.assertEqual("My Programs", state["campaign_ops_section"])
