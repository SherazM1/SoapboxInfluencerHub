from __future__ import annotations

import unittest
from streamlit.testing.v1 import AppTest
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
        self.assertEqual(repo.programs[0].id, app.session_state["campaign_ops_selected_program_id"])
        self.assertTrue(any(w.value == "Program created." for w in app.success))
        app._run(None)  # Fresh render: AppTest retains stale nodes across st.rerun().
        self.assertFalse(any(w.label == "Create Program" for w in app.button))
        self.assertFalse(any(k.startswith("campaign_ops_new_program_")
                             for k in app.session_state.filtered_state))
        button(app, "Back to Programs").click().run()
        self.assertEqual([], list(app.exception))
        self.assertIn("Test Influencer Program", app.dataframe[0].value["Program name"].tolist())

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
