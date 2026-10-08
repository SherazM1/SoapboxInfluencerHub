from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app.campaign_ops.formatting import WORKFLOW_LABELS
from app.campaign_ops.program_forms import render_new_program_form
from core.campaign_ops.enums import AssignmentRole, CrossStage, ProgramStatus, RiskLevel, UserRole, WorkflowRole, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsPermissionError, CampaignOpsValidationError
from core.campaign_ops.models import CampaignOpsUser, Client, UserWorkflowRole
from core.campaign_ops.service import CampaignOpsService
from tests.test_campaign_ops_foundation import FakePrompt4ARepository


ROSTER = {
    (WorkstreamType.INFLUENCER.value, WorkflowRole.LEAD_OWNER.value): ("Taylor", "Lauren", "Ava"),
    (WorkstreamType.INFLUENCER.value, WorkflowRole.MANAGER.value): ("Allyn", "Maren", "Carly"),
    (WorkstreamType.ECOMMERCE.value, WorkflowRole.LEAD_OWNER.value): ("Emma", "Kate"),
    (WorkstreamType.ECOMMERCE.value, WorkflowRole.MANAGER.value): ("Emma", "Kate"),
    (WorkstreamType.RETAIL_MEDIA.value, WorkflowRole.LEAD_OWNER.value): ("Chloe",),
    (WorkstreamType.RETAIL_MEDIA.value, WorkflowRole.MANAGER.value): ("Chloe",),
    (WorkstreamType.SMM.value, WorkflowRole.LEAD_OWNER.value): ("Taylor", "Ava"),
    (WorkstreamType.SMM.value, WorkflowRole.MANAGER.value): ("Ava", "Maren"),
}


class RosterRepository(FakePrompt4ARepository):
    def __init__(self) -> None:
        super().__init__()
        self.content_management_programs = []
        self.content_management_rows = []
        self.users[1].display_name = "Taylor"
        self.users[2].display_name = "Lauren"
        for name in ("Jordon", "Ava", "Allyn", "Maren", "Carly", "Emma", "Kate", "Chloe"):
            if self.get_user_by_display_name(name):
                continue
            role = UserRole.ADMINISTRATOR.value if name == "Jordon" else UserRole.TEAM_MEMBER.value
            self.users.append(CampaignOpsUser(id=f"user-{name.lower()}", display_name=name, role=role))
        self.workflow_roles: list[UserWorkflowRole] = []
        self._seed_roster()

    def _seed_roster(self) -> None:
        for (workflow, role), names in ROSTER.items():
            for name in names:
                self.workflow_roles.append(
                    UserWorkflowRole(
                        id=f"role-{len(self.workflow_roles) + 1}",
                        user_id=self.get_user_by_display_name(name).id,
                        workflow_key=workflow,
                        workflow_role=role,
                    )
                )

    def list_workflow_role_users(self, workflow_key: str, workflow_role: str) -> list[CampaignOpsUser]:
        user_ids = [
            item.user_id
            for item in self.workflow_roles
            if item.is_active and item.workflow_key == workflow_key and item.workflow_role == workflow_role
        ]
        users_by_id = {user.id: user for user in self.users if user.is_active}
        return [users_by_id[user_id] for user_id in user_ids if user_id in users_by_id]

    def list_workflow_roles(self, workflow_key=None, workflow_role=None, include_inactive=False):
        return [
            item for item in self.workflow_roles
            if (include_inactive or item.is_active)
            and (workflow_key is None or item.workflow_key == workflow_key)
            and (workflow_role is None or item.workflow_role == workflow_role)
        ]

    def create_workflow_role(self, user_id, workflow_key, workflow_role, actor_user_id=None):
        item = UserWorkflowRole(
            id=f"role-{len(self.workflow_roles) + 1}",
            user_id=user_id,
            workflow_key=workflow_key,
            workflow_role=workflow_role,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        self.workflow_roles.append(item)
        return item

    def update_workflow_role(self, role_id, user_id, workflow_key, workflow_role, actor_user_id=None):
        item = next(item for item in self.workflow_roles if item.id == role_id)
        item.user_id = user_id
        item.workflow_key = workflow_key
        item.workflow_role = workflow_role
        item.updated_by = actor_user_id
        return item

    def deactivate_workflow_role(self, role_id, actor_user_id=None):
        item = next(item for item in self.workflow_roles if item.id == role_id)
        item.is_active = False
        item.updated_by = actor_user_id

    def reactivate_workflow_role(self, role_id, actor_user_id=None):
        item = next(item for item in self.workflow_roles if item.id == role_id)
        item.is_active = True
        item.updated_by = actor_user_id
        return item

    def list_content_management_programs_by_program(self, program_id):
        return [item for item in self.content_management_programs
                if item.program_id == program_id and item.is_active]

    def get_content_management_program_by_program(self, program_id):
        return next(iter(self.list_content_management_programs_by_program(program_id)), None)

    def get_content_management_program(self, workspace_id):
        return next((item for item in self.content_management_programs if item.id == workspace_id), None)

    def create_content_management_program(self, program_id, workstream_id, actor_user_id=None):
        from core.campaign_ops.models import ContentManagementProgramRecord

        workspace = ContentManagementProgramRecord(
            id=f"content-workspace-{len(self.content_management_programs) + 1}",
            program_id=program_id,
            workstream_id=workstream_id,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        self.content_management_programs.append(workspace)
        return workspace

    def list_content_management_timeline_rows(self, workspace_id, include_inactive=False):
        return [row for row in self.content_management_rows
                if row.content_management_program_id == workspace_id
                and (include_inactive or row.is_active)]

    def create_content_management_timeline_row(
        self, workspace_id, action, due_date=None, program_notes=None, done=False,
        sequence_order=0, actor_user_id=None,
    ):
        from core.campaign_ops.models import ContentManagementTimelineRowRecord

        row = ContentManagementTimelineRowRecord(
            id=f"content-row-{len(self.content_management_rows) + 1}",
            content_management_program_id=workspace_id,
            action=action,
            due_date=due_date,
            done=done,
            program_notes=program_notes,
            sequence_order=sequence_order,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )
        self.content_management_rows.append(row)
        return row

    def update_content_management_timeline_row(self, row_id, **kwargs):
        row = next(item for item in self.content_management_rows if item.id == row_id)
        for key, value in kwargs.items():
            if key != "actor_user_id":
                setattr(row, key, value)
        return row

    def deactivate_content_management_timeline_row(self, row_id, actor_user_id=None):
        next(item for item in self.content_management_rows if item.id == row_id).is_active = False


def new_program_app():
    import streamlit as st

    from app.campaign_ops.program_forms import render_new_program_form
    from core.campaign_ops.service import CampaignOpsService
    from tests.test_campaign_ops_roster_new_program import RosterRepository

    if "roster_repo" not in st.session_state:
        st.session_state.roster_repo = RosterRepository()
    repository = st.session_state.roster_repo
    render_new_program_form(
        repository.users[0], CampaignOpsService(repository), repository.users, repository.clients
    )


def selectbox(app, label):
    return next(item for item in app.selectbox if item.label == label)


def text_input(app, label):
    return next(item for item in app.text_input if item.label == label)


def button(app, label):
    return next(item for item in app.button if item.label == label)


class WorkflowRosterTests(unittest.TestCase):
    def setUp(self):
        self.repository = RosterRepository()
        self.service = CampaignOpsService(self.repository)
        self.admin = self.repository.get_user_by_display_name("Bailey")
        self.member = self.repository.get_user_by_display_name("Taylor")

    def test_normalized_current_users_and_preserved_legacy_ids(self):
        expected = {
            "Bailey": "administrator", "Jordon": "administrator",
            "Taylor": "team_member", "Lauren": "team_member", "Ava": "team_member",
            "Allyn": "team_member", "Maren": "team_member", "Carly": "team_member",
            "Emma": "team_member", "Kate": "team_member", "Chloe": "team_member",
        }
        actual = {user.display_name: user.role for user in self.repository.users if user.is_active}
        self.assertTrue(set(expected.items()) <= set(actual.items()))
        self.assertEqual(self.repository.users[1].id, "22222222-2222-4222-8222-222222222222")
        self.assertEqual(self.repository.users[2].id, "33333333-3333-4333-8333-333333333333")
        self.assertFalse(any(user.is_active and user.display_name in ("T", "L") for user in self.repository.users))
        for name in expected:
            self.assertEqual(1, sum(user.is_active and user.display_name.casefold() == name.casefold() for user in self.repository.users))

    def test_configured_workflow_rosters_match_current_business_data(self):
        for (workflow, role), names in ROSTER.items():
            with self.subTest(workflow=workflow, role=role):
                actual = tuple(sorted(user.display_name for user in self.service.list_workflow_role_users(workflow, role)))
                self.assertEqual(tuple(sorted(names)), actual)
        self.assertEqual([], self.service.list_workflow_role_users(WorkstreamType.INSIGHTS.value, WorkflowRole.LEAD_OWNER.value))

    def test_program_creation_eligibility_uses_workflow_specific_roster_roles(self):
        expected = {
            WorkstreamType.ECOMMERCE.value: ("Emma", "Kate"),
            WorkstreamType.RETAIL_MEDIA.value: ("Chloe",),
            WorkstreamType.INFLUENCER.value: ("Taylor", "Lauren", "Ava"),
            WorkstreamType.SMM.value: ("Taylor", "Ava", "Maren"),
        }
        for workflow, eligible_names in expected.items():
            for name in eligible_names:
                with self.subTest(workflow=workflow, actor=name):
                    self.assertTrue(self.service.can_create_program(self.repository.get_user_by_display_name(name), workflow))
        for workflow in WorkstreamType:
            for admin_name in ("Bailey", "Jordon"):
                with self.subTest(workflow=workflow.value, admin=admin_name):
                    self.assertTrue(self.service.can_create_program(
                        self.repository.get_user_by_display_name(admin_name), workflow.value
                    ))
        for actor_name, workflow in (
            ("Allyn", WorkstreamType.INFLUENCER.value),
            ("Carly", WorkstreamType.INFLUENCER.value),
            ("Lauren", WorkstreamType.SMM.value),
            ("Emma", WorkstreamType.RETAIL_MEDIA.value),
            ("Chloe", WorkstreamType.ECOMMERCE.value),
        ):
            with self.subTest(workflow=workflow, actor=actor_name):
                self.assertFalse(self.service.can_create_program(
                    self.repository.get_user_by_display_name(actor_name), workflow
                ))

    def test_roster_eligible_member_can_create_without_admin_role(self):
        emma = self.repository.get_user_by_display_name("Emma")
        kate = self.repository.get_user_by_display_name("Kate")
        program_id = self.service.create_program_with_workstreams_and_assignments(
            actor=emma,
            program_name="Emma Content Creation",
            new_client_name="Roster Creation Client",
            primary_workstream_type=WorkstreamType.ECOMMERCE.value,
            primary_owner_user_id=emma.id,
            manager_user_id=kate.id,
            workstream_types=[WorkstreamType.ECOMMERCE.value],
        )
        program = self.repository.get_program(program_id)
        self.assertEqual(WorkstreamType.ECOMMERCE.value, program.primary_workstream_type)

    def test_roster_seed_migration_is_idempotent_and_preserves_identity_ids(self):
        from pathlib import Path

        migration = Path("db/migrations/012_campaign_ops_workflow_role_roster.sql").read_text(encoding="utf-8")
        self.assertIn("create table if not exists campaign_ops_user_workflow_roles", migration)
        self.assertIn("where is_active = true", migration)
        self.assertIn("on conflict (user_id, workflow_key, workflow_role) where is_active = true", migration)
        self.assertIn("do nothing", migration)
        self.assertIn("set display_name = 'Taylor'", migration)
        self.assertIn("set display_name = 'Lauren'", migration)
        self.assertIn("22222222-2222-4222-8222-222222222222", migration)
        self.assertIn("33333333-3333-4333-8333-333333333333", migration)
        self.assertIn("('Taylor', 'smm', 'lead_owner')", migration)
        self.assertNotIn("lead_owner_user_id", migration)
        self.assertNotIn("manager_user_id", migration)

    def test_roster_roles_allow_multi_role_and_admin_crud(self):
        emma = self.repository.get_user_by_display_name("Emma")
        existing = self.service.list_workflow_roles(WorkstreamType.ECOMMERCE.value)
        self.assertEqual(4, len(existing))
        self.assertTrue(any(item.user_id == emma.id and item.workflow_role == WorkflowRole.LEAD_OWNER.value for item in existing))
        self.assertTrue(any(item.user_id == emma.id and item.workflow_role == WorkflowRole.MANAGER.value for item in existing))

        with self.assertRaises(CampaignOpsValidationError):
            self.service.add_workflow_role(self.admin, emma.id, WorkstreamType.ECOMMERCE.value, WorkflowRole.MANAGER.value)
        with self.assertRaises(CampaignOpsPermissionError):
            self.service.add_workflow_role(self.member, emma.id, WorkstreamType.INFLUENCER.value, WorkflowRole.MANAGER.value)

        extra = self.service.add_workflow_role(self.admin, emma.id, WorkstreamType.INFLUENCER.value, WorkflowRole.MANAGER.value)
        carly = self.repository.get_user_by_display_name("Carly")
        self.service.update_workflow_role(self.admin, extra.id, carly.id, WorkstreamType.SMM.value, WorkflowRole.LEAD_OWNER.value)
        self.service.deactivate_workflow_role(self.admin, extra.id)
        self.assertNotIn(carly.id, {u.id for u in self.service.list_workflow_role_users(WorkstreamType.SMM.value, WorkflowRole.LEAD_OWNER.value)})
        self.service.reactivate_workflow_role(self.admin, extra.id)
        self.assertIn(carly.id, {u.id for u in self.service.list_workflow_role_users(WorkstreamType.SMM.value, WorkflowRole.LEAD_OWNER.value)})
        emma.is_active = False
        self.assertNotIn(emma.id, {u.id for u in self.service.list_workflow_role_users(WorkstreamType.SMM.value, WorkflowRole.LEAD_OWNER.value)})

    def test_new_program_form_exposes_only_requested_fields_and_roster_choices(self):
        app = AppTest.from_function(new_program_app).run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(["Client", "Program Name"], [item.label for item in app.text_input])
        self.assertEqual(["Workflow", "Lead Owner", "Manager"], [item.label for item in app.selectbox])
        self.assertEqual(["Cancel", "Create Program"], [item.label for item in app.button])
        self.assertEqual(["Taylor", "Lauren", "Ava"], selectbox(app, "Lead Owner").options)
        self.assertEqual(["Allyn", "Maren", "Carly"], selectbox(app, "Manager").options)
        self.assertNotIn("Description", [item.label for item in app.text_area])
        self.assertNotIn("Primary workflow", [item.label for item in app.selectbox])

    def test_new_program_requires_manager_before_calling_service(self):
        app = AppTest.from_function(new_program_app).run()
        selectbox(app, "Lead Owner").select(app.session_state.roster_repo.get_user_by_display_name("Taylor").id)
        button(app, "Create Program").click().run()
        self.assertTrue(any("Choose a Manager" in item.value for item in app.error))
        self.assertEqual([], app.session_state.roster_repo.programs)

    def test_unconfigured_workflow_has_no_fabricated_owners_or_create_button(self):
        app = AppTest.from_function(new_program_app).run()
        selectbox(app, "Workflow").select(WORKFLOW_LABELS[WorkstreamType.INSIGHTS.value]).run()
        self.assertEqual([], list(app.exception))
        self.assertTrue(any("No active Lead Owner / Manager roster is configured" in item.value for item in app.info))
        self.assertEqual(["Workflow"], [item.label for item in app.selectbox])
        self.assertFalse(any(item.label == "Create Program" for item in app.button))

    def test_program_creation_reuses_client_and_stores_both_ownership_assignments(self):
        app = AppTest.from_function(new_program_app).run()
        repository = app.session_state.roster_repo
        client = repository.create_client("Acme")
        app.run()
        text_input(app, "Client").set_value(" aCME ")
        text_input(app, "Program Name").set_value("Fall Launch")
        selectbox(app, "Lead Owner").select(app.session_state.roster_repo.get_user_by_display_name("Taylor").id)
        selectbox(app, "Manager").select(app.session_state.roster_repo.get_user_by_display_name("Allyn").id)
        button(app, "Create Program").click().run()

        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(repository.clients))
        program = repository.programs[0]
        self.assertEqual(client.id, program.client_id)
        self.assertEqual(WorkstreamType.INFLUENCER.value, program.primary_workstream_type)
        self.assertEqual(ProgramStatus.DRAFT.value, program.status)
        self.assertEqual(CrossStage.DRAFT.value, program.cross_stage)
        self.assertEqual(RiskLevel.UNRATED.value, program.risk_level)
        workstream = repository.workstreams[0]
        self.assertEqual(WorkstreamType.INFLUENCER.value, workstream.workstream_type)
        self.assertEqual(repository.get_user_by_display_name("Allyn").id, workstream.owner_user_id)
        self.assertTrue(any(
            item.program_id == program.id and item.workstream_id is None
            and item.assignment_role == AssignmentRole.PROGRAM_OWNER.value
            and item.is_primary and item.user_id == repository.get_user_by_display_name("Taylor").id
            for item in repository.assignments
        ))
        self.assertTrue(any(
            item.program_id == program.id and item.workstream_id == workstream.id
            and item.assignment_role == AssignmentRole.WORKSTREAM_LEAD.value
            and item.user_id == workstream.owner_user_id and item.is_active
            for item in repository.assignments
        ))

    def test_program_creation_can_use_same_person_as_lead_and_manager(self):
        emma = self.repository.get_user_by_display_name("Emma")
        program_id = self.service.create_program_with_workstreams_and_assignments(
            actor=self.admin,
            program_name="Content Launch",
            new_client_name="New Client",
            primary_workstream_type=WorkstreamType.ECOMMERCE.value,
            primary_owner_user_id=emma.id,
            manager_user_id=emma.id,
            workstream_types=[WorkstreamType.ECOMMERCE.value],
        )
        program = self.repository.get_program(program_id)
        workstream = next(item for item in self.repository.workstreams if item.program_id == program_id)
        self.assertEqual(emma.id, workstream.owner_user_id)
        self.assertTrue(any(item.program_id == program.id and item.user_id == emma.id and item.assignment_role == AssignmentRole.PROGRAM_OWNER.value for item in self.repository.assignments))
        self.assertTrue(any(item.program_id == program.id and item.user_id == emma.id and item.assignment_role == AssignmentRole.WORKSTREAM_LEAD.value for item in self.repository.assignments))

    def test_program_creation_rejects_users_outside_selected_workflow_roster(self):
        emma = self.repository.get_user_by_display_name("Emma")
        allyn = self.repository.get_user_by_display_name("Allyn")
        with self.assertRaisesRegex(CampaignOpsValidationError, "Lead Owner is not active"):
            self.service.create_program_with_workstreams_and_assignments(
                actor=self.admin,
                program_name="Invalid",
                new_client_name="Atomic Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=emma.id,
                manager_user_id=allyn.id,
            )
        self.assertEqual([], self.repository.programs)
        self.assertEqual([], self.repository.clients)

    def test_program_name_is_required_by_creation_service(self):
        taylor = self.repository.get_user_by_display_name("Taylor")
        allyn = self.repository.get_user_by_display_name("Allyn")
        with self.assertRaisesRegex(CampaignOpsValidationError, "Program name is required"):
            self.service.create_program_with_workstreams_and_assignments(
                actor=self.admin,
                program_name="  ",
                new_client_name="Unused Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=taylor.id,
                manager_user_id=allyn.id,
            )
        self.assertEqual([], self.repository.programs)
        self.assertEqual([], self.repository.clients)

    def test_program_creation_rejects_unrostered_manager(self):
        taylor = self.repository.get_user_by_display_name("Taylor")
        emma = self.repository.get_user_by_display_name("Emma")
        with self.assertRaisesRegex(CampaignOpsValidationError, "Manager is not active"):
            self.service.create_program_with_workstreams_and_assignments(
                actor=self.admin,
                program_name="Invalid Manager",
                new_client_name="Unused Client",
                primary_workstream_type=WorkstreamType.INFLUENCER.value,
                primary_owner_user_id=taylor.id,
                manager_user_id=emma.id,
            )
        self.assertEqual([], self.repository.programs)
        self.assertEqual([], self.repository.clients)

    def test_program_creation_failure_rolls_back_client_program_workstream_and_assignments(self):
        repository = RosterRepository()
        admin = repository.get_user_by_display_name("Bailey")
        taylor = repository.get_user_by_display_name("Taylor")
        allyn = repository.get_user_by_display_name("Allyn")
        original_create_assignment = repository.create_assignment

        def fail_workstream_lead(program_id, user_id, assignment_role, **kwargs):
            if assignment_role == AssignmentRole.WORKSTREAM_LEAD.value:
                raise RuntimeError("workstream assignment write failed")
            return original_create_assignment(program_id, user_id, assignment_role, **kwargs)

        repository.create_assignment = fail_workstream_lead

        class Transaction:
            def __enter__(self):
                self.snapshot = {
                    name: deepcopy(getattr(repository, name))
                    for name in ("clients", "programs", "workstreams", "assignments", "events")
                }
                return self

            def __exit__(self, exc_type, _exc, _traceback):
                if exc_type:
                    for name, value in self.snapshot.items():
                        setattr(repository, name, value)
                return False

        class Connection:
            def transaction(self):
                return Transaction()

            def close(self):
                self.closed = True

        connection = Connection()
        with patch("core.campaign_ops.service.connect_to_database", return_value=connection):
            with patch("core.campaign_ops.service.CampaignOpsRepository", return_value=repository):
                with self.assertRaisesRegex(RuntimeError, "workstream assignment write failed"):
                    CampaignOpsService().create_program_with_workstreams_and_assignments(
                        actor=admin,
                        program_name="Atomic Failure",
                        new_client_name="Atomic Client",
                        primary_workstream_type=WorkstreamType.INFLUENCER.value,
                        primary_owner_user_id=taylor.id,
                        manager_user_id=allyn.id,
                    )

        self.assertEqual([], repository.clients)
        self.assertEqual([], repository.programs)
        self.assertEqual([], repository.workstreams)
        self.assertEqual([], repository.assignments)
        self.assertEqual([], repository.events)
        self.assertTrue(connection.closed)


if __name__ == "__main__":
    unittest.main()
