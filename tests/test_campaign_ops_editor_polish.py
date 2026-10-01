from copy import deepcopy
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsPermissionError
from core.campaign_ops.influencer_timeline import InfluencerTimelineService, editor_record, sort_timeline
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.smm import SMMTimelineService
from tests.operational_editor_helpers import button, edit, field, draft_records
from tests.test_campaign_ops_smm_editor import smm_app
from tests.test_influencer_timeline import fixture, timeline_app


class EditorPolishTests(unittest.TestCase):
    def test_influencer_done_is_independent_of_status_sort_and_stage(self):
        repo, service, actor, lead, _, program = fixture()
        campaign = service.create_campaign(actor, program, 'Done tracking', lead.id)
        rows = service.workspace(actor, campaign.id)[1]
        self.assertTrue(all(not r.done for r in rows))
        rows[0].due_date = rows[1].due_date = date(2026, 6, 1)
        rows[0].status = 'complete'
        original = deepcopy(rows)
        records = [editor_record(r) for r in rows]
        records[1]['Done'] = True
        records[-1]['Done'] = True
        service.save_changes(actor, campaign.id, lead.id, records, original, lead.id, 'planning')
        self.assertEqual([r.id for r in original], [r.id for r in sort_timeline(rows)])
        self.assertTrue(rows[1].done)
        self.assertFalse(rows[0].done)
        self.assertEqual('complete', rows[0].status)
        self.assertEqual('planning', campaign.influencer_stage)
        service.advance(actor, campaign.id, 'planning')
        self.assertTrue(rows[1].done)

    def test_widgets_buffer_without_save_or_timeline_reload(self):
        for page, kind in ((timeline_app, InfluencerTimelineService), (smm_app, SMMTimelineService)):
            with self.subTest(kind=kind):
                app = AppTest.from_function(page).run()
                token = draft_records(app)[0]['_draft_id']
                with patch.object(kind, 'save_changes', side_effect=AssertionError('Per-cell save')), \
                     patch.object(kind, 'workspace', side_effect=AssertionError('Workspace reload')):
                    edit(app, 0, **{'Date': '2026-07-01', 'Done': True, 'Program Notes': 'Buffered'})
                    button(app, 'Add row').click().run()
                self.assertEqual(token, draft_records(app)[0]['_draft_id'])
                self.assertTrue(field(app, 'Done, row 1').value)
                self.assertEqual('Buffered', field(app, 'Program Notes, row 1').value)

    def test_smm_save_one_transaction_and_clear_date(self):
        app = AppTest.from_function(smm_app).run()
        repo, _, actor, program = app.session_state.smm_fixture
        service = SMMTimelineService(repo)
        _, rows = service.workspace(actor, program)
        rows[0].due_date = date(2026, 7, 1)
        original = deepcopy(rows)
        records = deepcopy(draft_records(app))
        records[0].update({'Date': None, 'Done': True, 'Action': 'Revised'})
        ownership = service.assignment_state(actor, program)
        connection = MagicMock()
        with patch('core.campaign_ops.service.connect_to_database', return_value=connection), \
             patch('core.campaign_ops.service.CampaignOpsRepository', return_value=repo):
            SMMTimelineService().save_changes(actor, program, records, original, ownership,
                ownership['lead_id'], ownership['manager_id'])
        connection.transaction.assert_called_once()
        self.assertIsNone(rows[0].due_date)
        self.assertTrue(rows[0].done)
        self.assertEqual('Revised', rows[0].action)

    def test_smm_invalid_draft_and_revoked_access_do_not_write(self):
        app = AppTest.from_function(smm_app).run()
        repo, _, actor, program = app.session_state.smm_fixture
        service = SMMTimelineService(repo)
        ownership = service.assignment_state(actor, program)
        _, rows = service.workspace(actor, program)
        records = deepcopy(draft_records(app))
        original = deepcopy(rows)
        records[0]['Program Notes'] = 'Must not save'
        records[-1]['Action'] = ''
        with patch.object(repo, 'update_smm_timeline_row') as update:
            with self.assertRaises(CampaignOpsError):
                service.save_changes(actor, program, records, original, ownership,
                    ownership['lead_id'], ownership['manager_id'])
            update.assert_not_called()
        with self.assertRaises(CampaignOpsPermissionError):
            service.initialize_program(None, program)
        manager = repo.get_user_by_id(ownership['manager_id'])
        records[-1]['Action'] = original[-1].action
        repo.workstreams[0].owner_user_id = None
        for assignment in repo.assignments:
            if assignment.user_id == manager.id:
                assignment.is_active = False
        with self.assertRaises(CampaignOpsPermissionError):
            service.save_changes(manager, program, records, original, ownership,
                ownership['lead_id'], ownership['manager_id'])
        self.assertEqual(original, rows)

    def test_smm_initialization_uses_actor_and_never_reseeds_removed_rows(self):
        app = AppTest.from_function(smm_app).run()
        repo, _, actor, program = app.session_state.smm_fixture
        workspace = repo.get_smm_program_by_program(program)
        self.assertEqual(actor.id, workspace.created_by)
        rows = repo.list_smm_timeline_rows(workspace.id)
        repo.deactivate_smm_timeline_row(rows[0].id, actor.id)
        again, rows = SMMTimelineService(repo).initialize_program(actor, program)
        self.assertEqual(workspace.id, again.id)
        self.assertEqual(7, len(rows))
        self.assertNotIn('initialize_program(None', Path('app/campaign_ops/smm/views.py').read_text())

    def test_repository_preserves_done_and_distinguishes_date_clear_from_omission(self):
        repo = CampaignOpsRepository()
        with patch.object(repo, '_create_content_child') as create:
            repo.create_influencer_planning_step('campaign', 'Action', done=True)
            fields, values = create.call_args.args[2:]
            self.assertIs(True, dict(zip(fields, values))['done'])
        with patch.object(repo, '_write_returning') as write:
            repo.update_smm_timeline_row('row', done=True)
            self.assertEqual((False, None), write.call_args.args[1][:2])
            repo.update_smm_timeline_row('row', due_date=None)
            self.assertEqual((True, None), write.call_args.args[1][:2])

    def test_save_and_back_do_not_explicitly_rerun(self):
        for page in (timeline_app, smm_app):
            app = AppTest.from_function(page).run()
            edit(app, 0, **{'Done': True})
            with patch('streamlit.rerun', side_effect=AssertionError('Redundant rerun')):
                button(app, 'Save Changes').click().run()
                label = 'Back to campaigns' if page is timeline_app else 'Back to programs'
                button(app, label).click().run()
            self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
