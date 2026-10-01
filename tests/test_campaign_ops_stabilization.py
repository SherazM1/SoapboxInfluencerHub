from copy import deepcopy
from dataclasses import asdict
import unittest
from tests.operational_editor_helpers import apply_edits, edit, field, draft_records
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest
from core.campaign_ops.exceptions import CampaignOpsValidationError, CampaignOpsPermissionError
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.influencer_timeline import InfluencerTimelineService, editor_record
from tests.test_campaign_ops_new_program_flow import page_app
from tests.test_campaign_ops_roster_new_program import RosterRepository, button, selectbox, text_input


class StabilizationTests(unittest.TestCase):
    def setUp(self):
        self.repo = RosterRepository()
        self.actor = self.repo.users[0]
        self.lead = self.repo.get_user_by_display_name("Taylor")
        self.manager = self.repo.get_user_by_display_name("Allyn")
        self.program_id = ProgramRoutingService(self.repo).create_registry_program(
            self.actor, program_name="Stabilization", new_client_name="Client",
            primary_workstream_type="influencer", primary_owner_user_id=self.lead.id,
            manager_user_id=self.manager.id)
        self.campaign = self.repo.influencer_campaigns[0]
        self.service = InfluencerTimelineService(self.repo)
        self.rows = deepcopy(self.service.workspace(self.actor, self.campaign.id)[1])
        self.ownership = self.service.workspace_assignments(self.actor, self.campaign)
        self.records = [editor_record(r) for r in self.rows]

    def save(self, lead=None, manager=None):
        return self.service.save_changes(self.actor, self.campaign.id, lead or self.lead.id,
            self.records, self.rows, self.lead.id, "planning", manager_id=manager or self.manager.id,
            original_assignments=self.ownership)

    def test_real_repository_contract_constructs_typed_campaign_and_router_reuses_it(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [asdict(self.campaign)]
        repository = CampaignOpsRepository(connection)
        with patch.object(repository, "get_program", return_value=self.repo.get_program(self.program_id)), \
             patch.object(repository, "list_program_workflow_records", side_effect=AssertionError("Wrong Influencer interface")):
            destination = ProgramRoutingService(repository).resolve(self.actor, self.program_id)
        self.assertEqual(self.campaign.id, destination.record_id)
        cursor.execute.assert_called_once()
        self.assertEqual((self.program_id,), cursor.execute.call_args.args[1])
        self.assertIn("campaign_ops_influencer_campaigns", cursor.execute.call_args.args[0])

    def test_lead_and_manager_save_distinct_assignments_with_timeline(self):
        lead = self.repo.get_user_by_display_name("Lauren")
        manager = self.repo.get_user_by_display_name("Maren")
        self.records[0]["Program Notes"] = "Buffered edit"
        result = self.save(lead.id, manager.id)
        row = ProgramRoutingService(self.repo).list_registry(self.actor)[0]
        self.assertEqual((lead.id, manager.id), (row.primary_owner_user_id, row.manager_user_id))
        self.assertEqual("Buffered edit", self.repo.influencer_planning_steps[0].notes)
        matches = [a for a in self.repo.assignments if a.is_active and a.assignment_role == "workstream_lead"
                   and a.workstream_id == self.ownership["workstream_id"]]
        self.assertEqual([manager.id], [a.user_id for a in matches])
        self.assertEqual(1, result["manager_changed"])
        self.assertEqual(1, result["owner_changed"])

    def test_roster_validation_precedes_any_timeline_or_assignment_write(self):
        self.records[0]["Program Notes"] = "Do not write"
        before = deepcopy(self.repo.__dict__)
        with self.assertRaisesRegex(CampaignOpsValidationError, "active Influencer Manager"):
            self.save(manager=self.lead.id)
        self.assertEqual(before, self.repo.__dict__)

    def test_assignment_conflict_is_not_overwritten(self):
        self.repo.workstreams[0].owner_user_id = self.repo.get_user_by_display_name("Maren").id
        with self.assertRaisesRegex(CampaignOpsValidationError, "Assignments changed"):
            self.save()

    def test_non_admin_can_save_rows_but_cannot_reassign(self):
        self.actor = self.lead
        self.records[0]["Program Notes"] = "Allowed timeline edit"
        self.assertEqual(1, self.save()["updated"])
        self.rows = deepcopy(self.repo.list_influencer_planning_steps(self.campaign.id))
        self.records = [editor_record(r) for r in self.rows]
        with self.assertRaises(CampaignOpsPermissionError):
            self.save(manager=self.repo.get_user_by_display_name("Maren").id)

    def test_manager_assignment_failure_rolls_back_timeline_and_lead(self):
        repo = self.repo
        before = deepcopy(repo.__dict__)
        class Transaction:
            def __enter__(self):
                return self
            def __exit__(self, kind, exc, tb):
                if kind:
                    repo.__dict__.update(deepcopy(before))
                return False
        connection = MagicMock()
        connection.transaction.return_value = Transaction()
        self.records[0]["Program Notes"] = "Rollback note"
        with patch("core.campaign_ops.service.connect_to_database", return_value=connection), \
             patch("core.campaign_ops.service.CampaignOpsRepository", return_value=repo), \
             patch.object(repo, "update_workstream", side_effect=RuntimeError("Assignment failure")):
            with self.assertRaisesRegex(RuntimeError, "Assignment failure"):
                InfluencerTimelineService().save_changes(self.actor, self.campaign.id,
                    self.repo.get_user_by_display_name("Lauren").id, self.records, self.rows, self.lead.id,
                    "planning", manager_id=self.repo.get_user_by_display_name("Maren").id,
                    original_assignments=self.ownership)
        self.assertEqual(before, repo.__dict__)
        connection.transaction.assert_called_once()

    def test_both_entry_paths_and_save_use_same_editor_without_explicit_rerun(self):
        app = AppTest.from_function(page_app).run()
        app.session_state.roster_repo = self.repo
        app.run()
        with patch("streamlit.rerun", side_effect=AssertionError("Redundant rerun")):
            button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.campaign.id, app.session_state["campaign_ops_selected_influencer_campaign_id"])
        ids = [r["_row_id"] for r in draft_records(app)]
        self.assertEqual(["Taylor", "Lauren", "Ava"], selectbox(app, "Lead Owner").options)
        self.assertEqual(["Allyn", "Maren", "Carly"], selectbox(app, "Manager").options)
        selectbox(app, "Manager").select(self.repo.get_user_by_display_name("Maren").id).run()
        self.assertEqual(self.manager.id, self.repo.workstreams[0].owner_user_id)
        with patch("streamlit.rerun", side_effect=AssertionError("Redundant rerun")), \
             patch.object(InfluencerTimelineService, "save_changes", autospec=True,
                          side_effect=InfluencerTimelineService.save_changes) as save:
            button(app, "Save Changes").click().run()
        self.assertFalse(app.exception)
        save.assert_called_once()
        self.assertEqual(self.repo.get_user_by_display_name("Maren").id, self.repo.workstreams[0].owner_user_id)
        button(app, "Back to campaigns").click().run()
        with patch("streamlit.rerun", side_effect=AssertionError("Redundant rerun")):
            button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(ids, [r["_row_id"] for r in draft_records(app)])
        self.assertEqual(self.campaign.id, app.session_state["campaign_ops_selected_influencer_campaign_id"])
        self.assertFalse(app.tabs)

    def test_new_program_callback_persists_once_and_renders_final_workspace(self):
        app = AppTest.from_function(page_app).run()
        with patch("streamlit.rerun", side_effect=AssertionError("Redundant rerun")):
            button(app, "New Program").click().run()
        repo = app.session_state.roster_repo
        text_input(app, "Client").set_value("Callback client")
        text_input(app, "Program Name").set_value("Callback program")
        selectbox(app, "Lead Owner").select(repo.get_user_by_display_name("Taylor").id)
        selectbox(app, "Manager").select(repo.get_user_by_display_name("Allyn").id)
        with patch("streamlit.rerun", side_effect=AssertionError("Redundant rerun")), \
             patch.object(ProgramRoutingService, "create_registry_program", autospec=True,
                          side_effect=ProgramRoutingService.create_registry_program) as create:
            button(app, "Create Program").click().run()
        self.assertFalse(app.exception)
        create.assert_called_once()
        self.assertEqual(1, len(repo.programs))
        self.assertEqual(1, len(repo.influencer_campaigns))
        self.assertEqual("Influencer", app.session_state["campaign_ops_section"])
        self.assertTrue(any(w.label == "Save Changes" for w in app.button))
        self.assertFalse(any(w.label == "Create Program" for w in app.button))
