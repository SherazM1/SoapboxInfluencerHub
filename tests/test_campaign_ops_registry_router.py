from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from app.campaign_ops.program_router import open_program
from core.campaign_ops.exceptions import CampaignOpsPermissionError, CampaignOpsValidationError
from core.campaign_ops.influencer_timeline import DEFAULT_ACTIONS
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService
from tests.test_campaign_ops_new_program_flow import page_app
from tests.test_campaign_ops_roster_new_program import RosterRepository, button


class RegistryRouterTests(unittest.TestCase):
    def setUp(self):
        self.repo = RosterRepository()
        self.service = ProgramRoutingService(self.repo)
        self.admin = self.repo.users[0]
        self.lead = self.repo.get_user_by_display_name("Taylor")
        self.manager = self.repo.get_user_by_display_name("Allyn")

    def create(self, workflow="influencer", bridge=False):
        if workflow in ("ecommerce", "retail_media", "smm"):
            lead = self.repo.list_workflow_role_users(workflow, "lead_owner")[0]
            manager = self.repo.list_workflow_role_users(workflow, "manager")[0]
        else:
            lead, manager = self.lead, self.manager
        kwargs = dict(actor=self.admin, program_name="Registry program", new_client_name="Registry client",
                      primary_workstream_type=workflow, primary_owner_user_id=lead.id)
        if workflow != "insights":
            kwargs["manager_user_id"] = manager.id
        create = self.service.create_registry_program if bridge else self.service.create_program_with_workstreams_and_assignments
        return create(**kwargs)

    def test_registry_ownership_uses_primary_workstream_and_current_names(self):
        pid = self.create()
        self.repo.create_workstream(pid, "ecommerce", owner_user_id=self.lead.id)
        self.lead.display_name = "Renamed Lead"
        self.manager.display_name = "Renamed Manager"
        row = self.service.list_registry(self.admin)[0]
        self.assertEqual("Renamed Lead", row.primary_owner_name)
        self.assertEqual("Renamed Manager", row.manager_name)
        self.assertEqual(self.manager.id, row.manager_user_id)

    def test_registry_sql_has_only_registry_joins_and_existing_visibility(self):
        repo = CampaignOpsRepository()
        with patch.object(repo, "_fetch_all", return_value=[]) as fetch:
            repo.list_program_registry(self.lead.id)
        sql, params, model = fetch.call_args.args
        self.assertEqual((self.lead.id,) * 4, params)
        self.assertEqual("ProgramRegistryRow", model.__name__)
        for forbidden in ("campaign_ops_tasks", "campaign_ops_notes", "campaign_ops_activity",
                          "campaign_ops_milestones", "array_agg", "cross_stage", "risk_level"):
            self.assertNotIn(forbidden, sql)
        for required in ("assignment_role = 'program_owner'", "a.is_primary = true",
                         "ws.workstream_type = p.primary_workstream_type", "ws.owner_user_id",
                         "access_lead.is_active = true", "access_manager.is_active = true"):
            self.assertIn(required, sql)

    def test_registry_page_has_only_six_columns_and_no_filters_or_generic_loads(self):
        with patch.object(CampaignOpsService, "get_program_workspace_summary", side_effect=AssertionError("Generic bundle")), \
             patch.object(CampaignOpsService, "list_program_portfolio", side_effect=AssertionError("Heavy portfolio")):
            app = AppTest.from_function(page_app).run()
            self.assertFalse(app.exception)
            headings = [w.value for w in app.markdown if w.value.startswith("**")]
            self.assertEqual(["**Client**", "**Program**", "**Workflow**", "**Lead Owner**", "**Manager**", "**Open**"], headings)
            self.assertFalse(any(w.label == "Filters" for w in app.expander))
            self.assertEqual([], list(app.text_input))
            self.assertFalse(any(w.label in ("Risk", "Cross stage", "Program status") for w in app.selectbox))

    def test_open_bridges_once_and_never_reseeds_existing_rows(self):
        pid = self.create()
        assignments = deepcopy(self.repo.assignments)
        workstreams = deepcopy(self.repo.workstreams)
        with patch.object(self.repo, "lock_influencer_timeline_program", wraps=self.repo.lock_influencer_timeline_program) as lock:
            first = self.service.resolve(self.admin, pid)
            self.assertTrue(lock.called)
        campaign = self.repo.influencer_campaigns[0]
        self.assertEqual("Influencer", first.section)
        self.assertEqual(campaign.id, first.record_id)
        self.assertEqual(self.lead.id, campaign.manager_user_id)
        self.assertEqual(workstreams[0].id, campaign.workstream_id)
        rows = self.repo.list_influencer_planning_steps(campaign.id)
        self.assertEqual(list(DEFAULT_ACTIONS), [r.step_title for r in rows])
        self.repo.deactivate_influencer_planning_step(rows[0].id)
        rows[1].step_title = "Edited action"
        original_ids = [r.id for r in self.repo.list_influencer_planning_steps(campaign.id, include_inactive=True)]
        for _ in range(3):
            self.assertEqual(first, self.service.resolve(self.admin, pid))
        self.assertEqual(1, len(self.repo.influencer_campaigns))
        self.assertEqual(original_ids, [r.id for r in self.repo.list_influencer_planning_steps(campaign.id, include_inactive=True)])
        self.assertEqual(assignments, self.repo.assignments)
        self.assertEqual(workstreams, self.repo.workstreams)

    def test_creation_includes_timeline_and_reuses_it_on_open(self):
        pid = self.create(bridge=True)
        campaign = self.repo.influencer_campaigns[0]
        state = {"campaign_ops_selected_program_id": pid,
                 "campaign_ops_selected_retail_media_campaign_id": "stale",
                 "campaign_ops_influencer_draft_old": {"stale": True}}
        open_program(state, self.admin, self.service, pid)
        self.assertEqual("Influencer", state["campaign_ops_section"])
        self.assertEqual(campaign.id, state["campaign_ops_selected_influencer_campaign_id"])
        self.assertEqual("Planning", state["campaign_ops_influencer_timeline_navigation"])
        self.assertNotIn("campaign_ops_selected_program_id", state)
        self.assertNotIn("campaign_ops_selected_retail_media_campaign_id", state)
        self.assertNotIn("campaign_ops_influencer_draft_old", state)
        self.assertEqual(1, len(self.repo.influencer_campaigns))

    def test_existing_campaign_at_live_or_recapping_opens_correct_stage(self):
        pid = self.create(bridge=True)
        for stage, label in (("live", "Live"), ("recapping", "Recapping")):
            self.repo.influencer_campaigns[0].influencer_stage = stage
            state = {}
            open_program(state, self.admin, self.service, pid)
            self.assertEqual(label, state["campaign_ops_influencer_timeline_navigation"])
            self.assertEqual(1, len(self.repo.influencer_campaigns))

    def test_multiple_or_archived_campaigns_are_not_duplicated(self):
        pid = self.create(bridge=True)
        campaign = self.repo.influencer_campaigns[0]
        campaign.is_active = False
        self.assertIsNone(self.service.resolve(self.admin, pid).record_id)
        self.assertEqual(1, len(self.repo.influencer_campaigns))
        campaign.is_active = True
        self.repo.create_influencer_campaign(program_id=pid, campaign_title="Another", influencer_stage="planning")
        with self.assertRaisesRegex(CampaignOpsValidationError, "Multiple active Influencer campaigns"):
            self.service.resolve(self.admin, pid)
        self.assertEqual(2, len(self.repo.influencer_campaigns))

    def test_other_workflows_open_single_record_or_section_and_clear_stale_selection(self):
        for workflow, section, key in (
            ("retail_media", "Retail Media", "campaign_ops_selected_retail_media_campaign_id"),
            ("ecommerce", "eCommerce / Content", "campaign_ops_selected_content_program_id"),
            ("insights", "Insights", "campaign_ops_selected_insights_project_id"),
        ):
            with self.subTest(workflow=workflow):
                pid = self.create(workflow)
                state = {key: "old"}
                open_program(state, self.admin, self.service, pid)
                self.assertEqual(section, state["campaign_ops_section"])
                if workflow == "ecommerce":
                    workspace = self.repo.get_content_management_program_by_program(pid)
                    self.assertEqual(workspace.id, state[key])
                else:
                    self.assertNotIn(key, state)
                record = SimpleNamespace(id="workflow-record", is_active=True)
                with patch.object(self.repo, "list_program_workflow_records", return_value=[record]):
                    open_program(state, self.admin, self.service, pid)
                if workflow == "ecommerce":
                    self.assertEqual(workspace.id, state[key])
                else:
                    self.assertEqual("workflow-record", state[key])
                self.assertNotIn("campaign_ops_selected_program_id", state)

    def test_smm_has_explicit_section_fallback(self):
        pid = self.create("smm")
        state = {}
        destination = open_program(state, self.admin, self.service, pid)
        self.assertEqual("Social Media Management", destination.section)
        self.assertEqual(pid, destination.record_id)
        self.assertEqual(pid, state["campaign_ops_selected_smm_program_id"])
        self.assertNotIn("campaign_ops_selected_program_id", state)

    def test_smm_workspace_is_initialized_once_and_reused_by_all_registry_routes(self):
        pid = self.create("smm", bridge=True)
        workspace = self.repo.get_smm_program_by_program(pid)
        rows = self.repo.list_smm_timeline_rows(workspace.id)
        row_ids = [row.id for row in rows]
        state = {}

        for _ in range(3):
            destination = open_program(state, self.admin, self.service, pid)
            self.assertEqual("Social Media Management", destination.section)
            self.assertEqual(pid, state["campaign_ops_selected_smm_program_id"])

        self.assertEqual(1, len(self.repo.list_smm_programs_by_program(pid)))
        self.assertEqual(8, len(self.repo.list_smm_timeline_rows(workspace.id)))
        self.assertEqual(row_ids, [row.id for row in self.repo.list_smm_timeline_rows(workspace.id)])

    def test_open_initializes_missing_smm_workspace_once(self):
        pid = self.create("smm")
        self.assertEqual([], self.repo.list_smm_programs_by_program(pid))
        for _ in range(2):
            open_program({}, self.admin, self.service, pid)
        workspace = self.repo.get_smm_program_by_program(pid)
        self.assertIsNotNone(workspace)
        self.assertEqual(1, len(self.repo.list_smm_programs_by_program(pid)))
        self.assertEqual(8, len(self.repo.list_smm_timeline_rows(workspace.id)))

    def test_duplicate_active_smm_workspaces_fail_without_guessing(self):
        pid = self.create("smm")
        workstream = self.repo.list_workstreams_by_program(pid)[0]
        self.repo.create_smm_program(pid, workstream.id)
        self.repo.create_smm_program(pid, workstream.id)
        with self.assertRaisesRegex(CampaignOpsValidationError, "Multiple active SMM workspaces"):
            open_program({}, self.admin, self.service, pid)

    def test_smm_section_open_uses_same_editor_and_back_returns_to_list(self):
        app = AppTest.from_function(page_app, default_timeout=20).run()
        repo = app.session_state.roster_repo
        pid = ProgramRoutingService(repo).create_registry_program(
            actor=repo.users[0], program_name="SMM section route", new_client_name="Client",
            primary_workstream_type="smm",
            primary_owner_user_id=repo.get_user_by_display_name("Taylor").id,
            manager_user_id=repo.get_user_by_display_name("Ava").id,
        )
        app.run()
        button(app, "Social Media Management").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(
            ["**Program**", "**Lead Owner**", "**Manager**", "**Open**"],
            [widget.value for widget in app.markdown if widget.value.startswith("**")],
        )
        self.assertFalse(any(widget.label in ("Risk", "Cross stage", "Program status") for widget in app.selectbox))
        button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(pid, app.session_state["campaign_ops_selected_smm_program_id"])
        self.assertEqual("Social Media Management", app.session_state["campaign_ops_section"])
        self.assertTrue(any(widget.label == "Save Changes" for widget in app.button))
        self.assertFalse(any(widget.label == "Open Program Workspace" for widget in app.button))
        self.assertEqual([], list(app.tabs))
        button(app, "Back to programs").click().run()
        self.assertNotIn("campaign_ops_selected_smm_program_id", app.session_state)
        self.assertTrue(any(widget.label == "Open" for widget in app.button))

    def test_content_registry_my_programs_and_section_open_same_editor(self):
        app = AppTest.from_function(page_app, default_timeout=20).run()
        repository = app.session_state.roster_repo
        lead = repository.get_user_by_display_name("Emma")
        manager = repository.get_user_by_display_name("Kate")
        program_id = ProgramRoutingService(repository).create_registry_program(
            actor=repository.users[0], program_name="Content route", new_client_name="Client",
            primary_workstream_type="ecommerce", primary_owner_user_id=lead.id,
            manager_user_id=manager.id,
        )
        workspace = repository.get_content_management_program_by_program(program_id)
        app.run()

        button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(workspace.id, app.session_state["campaign_ops_selected_content_program_id"])
        self.assertEqual("eCommerce / Content", app.session_state["campaign_ops_section"])
        self.assertTrue(any(widget.label == "Save Changes" for widget in app.button))
        self.assertFalse(any(widget.label == "Open Program Workspace" for widget in app.button))
        self.assertEqual([], list(app.tabs))

        button(app, "Back to programs").click().run()
        button(app, "My Programs").click().run()
        button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(workspace.id, app.session_state["campaign_ops_selected_content_program_id"])
        button(app, "Back to programs").click().run()
        button(app, "eCommerce / Content").click().run()
        self.assertEqual(["**Client**", "**Program**", "**Lead Owner**", "**Manager**", "**Open**"],
                         [widget.value for widget in app.markdown if widget.value.startswith("**")])
        button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(workspace.id, app.session_state["campaign_ops_selected_content_program_id"])
        self.assertTrue(any(widget.label == "Save Changes" for widget in app.button))

    def test_all_programs_and_my_programs_smm_opens_use_shared_router(self):
        app = AppTest.from_function(page_app, default_timeout=20).run()
        repo = app.session_state.roster_repo
        pid = ProgramRoutingService(repo).create_registry_program(
            actor=repo.users[0], program_name="SMM registry route", new_client_name="Client",
            primary_workstream_type="smm",
            primary_owner_user_id=repo.get_user_by_display_name("Taylor").id,
            manager_user_id=repo.get_user_by_display_name("Ava").id,
        )
        app.run()
        button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(pid, app.session_state["campaign_ops_selected_smm_program_id"])
        self.assertTrue(any(widget.label == "Save Changes" for widget in app.button))
        button(app, "Back to programs").click().run()
        button(app, "My Programs").click().run()
        button(app, "Open").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(pid, app.session_state["campaign_ops_selected_smm_program_id"])
        self.assertEqual("Social Media Management", app.session_state["campaign_ops_section"])
        self.assertTrue(any(widget.label == "Save Changes" for widget in app.button))

    def test_unknown_workflow_never_falls_back_to_generic_workspace(self):
        pid = self.create()
        self.repo.get_program(pid).primary_workstream_type = None
        self.assertEqual("All Programs", self.service.resolve(self.admin, pid).section)

    def test_unauthorized_route_does_not_initialize_campaign(self):
        pid = self.create()
        outsider = self.repo.get_user_by_display_name("Emma")
        with self.assertRaises(CampaignOpsPermissionError):
            self.service.resolve(outsider, pid)
        self.assertEqual([], self.repo.influencer_campaigns)

    def test_open_from_registry_and_my_programs_renders_timeline_without_generic_bundle(self):
        with patch.object(CampaignOpsService, "get_program_workspace_summary", side_effect=AssertionError("Generic bundle")):
            app = AppTest.from_function(page_app).run()
            repo = app.session_state.roster_repo
            pid = ProgramRoutingService(repo).create_registry_program(
                actor=repo.users[0], program_name="Open directly", new_client_name="Client",
                primary_workstream_type="influencer",
                primary_owner_user_id=repo.get_user_by_display_name("Taylor").id,
                manager_user_id=repo.get_user_by_display_name("Allyn").id)
            app.run()
            button(app, "Open").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any(w.label == "Save Changes" for w in app.button))
            self.assertEqual([], list(app.tabs))
            button(app, "My Programs").click().run()
            # My Programs uses the same administrator scope and row-level Open action.
            button(app, "Open").click().run()
            self.assertFalse(app.exception)
            self.assertEqual("Influencer", app.session_state["campaign_ops_section"])
            self.assertTrue(any(w.label == "Save Changes" for w in app.button))

    def test_bridge_failure_rolls_back_entire_new_program_transaction(self):
        repo = self.repo
        class Transaction:
            def __enter__(self):
                self.snapshot = deepcopy(repo.__dict__)
            def __exit__(self, exc_type, exc, tb):
                if exc_type:
                    repo.__dict__.clear()
                    repo.__dict__.update(self.snapshot)
                return False
        connection = SimpleNamespace(transaction=lambda: Transaction(), close=lambda: None)
        with patch("core.campaign_ops.service.connect_to_database", return_value=connection), \
             patch("core.campaign_ops.service.CampaignOpsRepository", return_value=repo), \
             patch.object(repo, "create_influencer_planning_step", side_effect=RuntimeError("Timeline write failed")):
            with self.assertRaisesRegex(RuntimeError, "Timeline write failed"):
                ProgramRoutingService().create_registry_program(
                    actor=self.admin, program_name="Rollback", new_client_name="Rollback Client",
                    primary_workstream_type="influencer", primary_owner_user_id=self.lead.id,
                    manager_user_id=self.manager.id)
        for collection in (repo.clients, repo.programs, repo.workstreams, repo.assignments,
                           repo.influencer_campaigns, repo.events):
            self.assertEqual([], collection)
