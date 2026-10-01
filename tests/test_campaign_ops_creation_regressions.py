from dataclasses import asdict
import unittest
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from core.campaign_ops.exceptions import CampaignOpsPermissionError
from core.campaign_ops.models import CampaignOpsUser, Program, SMMProgramRecord, SMMTimelineRowRecord
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.smm import SMMTimelineService
from tests.test_campaign_ops_new_program_flow import page_app
from tests.test_campaign_ops_roster_new_program import button, selectbox, text_input


class InfluencerCreationRegressionTests(unittest.TestCase):
    def open_form(self):
        app = AppTest.from_function(page_app, default_timeout=20).run()
        button(app, 'Influencer').click().run()
        self.assertFalse(any(w.label == 'New Campaign' for w in app.expander))
        button(app, 'New Program').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(['Client', 'Program Name'], [w.label for w in app.text_input])
        self.assertEqual(['Viewing as', 'Lead Owner', 'Manager'], [w.label for w in app.selectbox])
        self.assertEqual('influencer', app.session_state['campaign_ops_new_program_fixed_workflow'])
        return app

    def test_section_creation_uses_program_assignments_and_same_editor_once(self):
        app = self.open_form()
        repo = app.session_state.roster_repo
        lead = repo.get_user_by_display_name('Taylor')
        manager = repo.get_user_by_display_name('Allyn')
        client = CampaignOpsService(repo).create_client(repo.users[0], 'Existing Client')
        text_input(app, 'Client').set_value('  EXISTING client  ')
        text_input(app, 'Program Name').set_value('Section-created Program')
        selectbox(app, 'Lead Owner').select(lead.id)
        selectbox(app, 'Manager').select(manager.id)
        with patch('streamlit.rerun', side_effect=AssertionError('Extra rerun')), \
             patch('app.campaign_ops.program_workspace.render_program_workspace', side_effect=AssertionError('Generic workspace')):
            button(app, 'Create Program').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(1, len(repo.clients))
        self.assertEqual(1, len(repo.programs))
        program = repo.programs[0]
        self.assertEqual(client.id, program.client_id)
        self.assertEqual('influencer', program.primary_workstream_type)
        streams = repo.list_workstreams_by_program(program.id)
        self.assertEqual(1, len(streams))
        self.assertEqual(manager.id, streams[0].owner_user_id)
        assignments = repo.list_assignments_by_program(program.id)
        self.assertTrue(any(a.user_id == lead.id and a.assignment_role == 'program_owner'
                            and a.is_primary and a.workstream_id is None for a in assignments))
        self.assertTrue(any(a.user_id == manager.id and a.assignment_role == 'workstream_lead'
                            and a.workstream_id == streams[0].id and a.is_active for a in assignments))
        self.assertEqual(1, len(repo.influencer_campaigns))
        campaign = repo.influencer_campaigns[0]
        row_ids = [r.id for r in repo.influencer_planning_steps]
        self.assertEqual(9, len(row_ids))
        self.assertEqual(campaign.id, app.session_state['campaign_ops_selected_influencer_campaign_id'])
        self.assertEqual(lead.id, selectbox(app, 'Lead Owner').value)
        self.assertEqual(manager.id, selectbox(app, 'Manager').value)
        self.assertEqual(9, len(app.date_input))
        self.assertEqual(9, sum(w.label.startswith('Done, row') for w in app.checkbox))
        self.assertEqual(['**Date**', '**Action**', '**Done**', '**Program Notes**', '**Remove**'],
                         [w.value for w in app.markdown if w.value.startswith('**')])
        self.assertEqual(1, sum(w.label == 'Save Changes' for w in app.button))
        router = ProgramRoutingService(repo)
        self.assertEqual([program.id], [r.id for r in router.list_registry(lead)])
        self.assertEqual([program.id], [r.id for r in router.list_registry(manager)])
        self.assertEqual([], router.list_registry(repo.get_user_by_display_name('Maren')))
        for _ in range(2):
            button(app, 'Back to campaigns').click().run()
            button(app, 'Open').click().run()
            self.assertFalse(app.exception)
        button(app, 'All Programs').click().run()
        button(app, 'Open').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(1, len(repo.influencer_campaigns))
        self.assertEqual(row_ids, [r.id for r in repo.influencer_planning_steps])

    def test_manager_is_required_and_rosters_come_from_database(self):
        app = self.open_form()
        repo = app.session_state.roster_repo
        self.assertEqual([u.display_name for u in repo.list_workflow_role_users('influencer', 'lead_owner')],
                         selectbox(app, 'Lead Owner').options)
        self.assertEqual([u.display_name for u in repo.list_workflow_role_users('influencer', 'manager')],
                         selectbox(app, 'Manager').options)
        text_input(app, 'Client').set_value('New Client')
        text_input(app, 'Program Name').set_value('New Program')
        selectbox(app, 'Lead Owner').select(repo.get_user_by_display_name('Taylor').id)
        button(app, 'Create Program').click().run()
        self.assertTrue(any('Choose a Manager' in w.value for w in app.error))
        self.assertEqual([], repo.clients)
        self.assertEqual([], repo.programs)
        selectbox(app, 'Manager').select(repo.get_user_by_display_name('Allyn').id)
        button(app, 'Create Program').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(1, len(repo.clients))
        self.assertEqual('New Client', repo.clients[0].name)

    def test_cancel_returns_to_influencer_and_does_not_pin_registry_workflow(self):
        app = self.open_form()
        text_input(app, 'Client').set_value('Discarded')
        button(app, 'Cancel').click().run()
        self.assertEqual('Influencer', app.session_state['campaign_ops_section'])
        button(app, 'All Programs').click().run()
        button(app, 'New Program').click().run()
        self.assertTrue(any(w.label == 'Workflow' for w in app.selectbox))
        self.assertEqual('', text_input(app, 'Client').value)

    def test_non_admin_cannot_create_programs_from_section(self):
        app = AppTest.from_function(page_app).run()
        selectbox(app, 'Viewing as').select('Allyn').run()
        button(app, 'Influencer').click().run()
        self.assertFalse(any(w.label in ('New Program', 'Create Program', 'Create Campaign') for w in app.button))


class SMMProductionRepositoryRegressionTests(unittest.TestCase):
    def test_unbound_service_uses_real_repository_get_program_contract(self):
        actor = CampaignOpsUser(id='admin', display_name='Renamed admin', role='administrator')
        program = Program(id='program', program_name='SMM', primary_workstream_type='smm')
        workspace = SMMProgramRecord(id='workspace', program_id=program.id, workstream_id='workstream')
        row = SMMTimelineRowRecord(id='row', smm_program_id=workspace.id, action='Existing', done=True)
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [asdict(program), asdict(workspace)] * 2
        cursor.fetchall.return_value = [asdict(row)]
        repository = CampaignOpsRepository(connection)
        service = SMMTimelineService()  # Exactly the production constructor path, not a fake-bound service.
        self.assertIsNone(service.repository)
        with patch('core.campaign_ops.smm.CampaignOpsRepository', return_value=repository), \
             patch.object(service, '_transaction', side_effect=AssertionError('Existing workspace must not be created')):
            for _ in range(2):
                actual, rows = service.initialize_program(actor, program.id)
                self.assertEqual(workspace, actual)
                self.assertEqual([row], rows)
        statements = [call.args[0].strip().lower() for call in cursor.execute.call_args_list]
        self.assertEqual(6, len(statements))
        self.assertTrue(all(sql.startswith('select') for sql in statements))
        self.assertTrue(any('campaign_ops_programs where id' in sql for sql in statements))

    def test_unbound_service_rejects_missing_actor_before_workspace_lookup(self):
        program = Program(id='program', program_name='SMM', primary_workstream_type='smm')
        repository = MagicMock(spec=CampaignOpsRepository)
        repository.get_program.return_value = program
        with patch('core.campaign_ops.smm.CampaignOpsRepository', return_value=repository):
            with self.assertRaises(CampaignOpsPermissionError):
                SMMTimelineService().initialize_program(None, program.id)
        repository.get_smm_program_by_program.assert_not_called()


if __name__ == '__main__':
    unittest.main()
