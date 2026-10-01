from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
import unittest
from tests.operational_editor_helpers import apply_edits, edit, field, draft_records
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer_timeline import ACTION_LIBRARY, EDITOR_COLUMNS, InfluencerTimelineService, editor_record
from tests.test_influencer_timeline import button, fixture, select, timeline_app


class DirectEditorTests(unittest.TestCase):
    def setUp(self):
        self.repo, self.service, self.actor, self.t, self.l, self.program = fixture()
        self.campaign = self.service.create_campaign(self.actor, self.program, 'Direct editor', self.t.id)
        self.refresh()

    def refresh(self):
        self.original = deepcopy(self.service.workspace(self.actor, self.campaign.id)[1])
        self.edited = [editor_record(row) for row in self.original]
        self.original_owner = self.campaign.manager_user_id
        self.original_stage = self.campaign.influencer_stage

    def save(self, owner=None):
        return self.service.save_changes(self.actor, self.campaign.id, owner or self.original_owner,
            self.edited, self.original, self.original_owner, self.original_stage)

    def test_native_rows_preserve_ids_and_blank_dates(self):
        app = AppTest.from_function(timeline_app).run()
        repo, *_ = app.session_state.fixture
        self.assertEqual([r.id for r in repo.influencer_planning_steps], [r['_row_id'] for r in draft_records(app)])
        self.assertTrue(all(r['_draft_id'] == r['_row_id'] for r in draft_records(app)))
        self.assertTrue(all(w.value is None for w in app.date_input))
        self.assertFalse(app.dataframe)

    def test_unchanged_save_has_no_row_owner_or_event_writes(self):
        with patch.object(self.repo, 'update_influencer_planning_step') as update, patch.object(self.repo, 'create_influencer_planning_step') as create, patch.object(self.repo, 'deactivate_influencer_planning_step') as remove, patch.object(self.repo, 'update_influencer_campaign') as owner, patch.object(self.repo, 'append_event') as event:
            result = self.save()
        self.assertEqual({'updated': 0, 'added': 0, 'removed': 0, 'owner_changed': 0, 'unchanged': 9}, result)
        for mock in (update, create, remove, owner, event): mock.assert_not_called()

    def test_atomic_differential_owner_add_edit_delete_and_sort(self):
        self.edited[0].update({'Date': date(2026, 6, 20), 'Action': 'Campaign Launch', 'Program Notes': 'Late note'})
        self.edited[1].update({'Date': date(2026, 6, 1), 'Action': 'Custom', 'Custom Action': 'Legal review', 'Program Notes': 'Review note'})
        removed = self.edited.pop(2)['_row_id']
        self.edited.append({'_row_id': None, 'Date': date(2026, 6, 10), 'Action': 'Custom', 'Custom Action': 'Midpoint', 'Program Notes': ''})
        with patch.object(self.repo, 'update_influencer_planning_step', wraps=self.repo.update_influencer_planning_step) as update:
            result = self.save(self.l.id)
        self.assertEqual(2, sum('step_title' in call.kwargs for call in update.call_args_list))
        self.assertEqual({'updated': 2, 'added': 1, 'removed': 1, 'owner_changed': 1, 'unchanged': 6}, result)
        self.assertEqual(self.l.id, self.campaign.manager_user_id)
        rows = self.service.workspace(self.actor, self.campaign.id)[1]
        self.assertEqual(['Legal review', 'Midpoint', 'Campaign Launch'], [r.step_title for r in rows[:3]])
        self.assertEqual(self.original[1].id, rows[0].id)
        self.assertEqual(self.original[0].id, rows[2].id)
        self.assertEqual([r.id for r in self.original[3:]], [r.id for r in rows[3:]])
        self.assertFalse(next(r for r in self.repo.influencer_planning_steps if r.id == removed).is_active)
        self.assertEqual(10, len(self.repo.influencer_planning_steps))
        self.refresh()
        self.assertEqual(0, self.save()['added'])

    def test_custom_text_equal_to_library_label_round_trips_as_custom(self):
        self.edited[0].update({'Action': 'Custom', 'Custom Action': 'Campaign Launch'})
        self.save()
        self.refresh()
        self.assertEqual('Custom', self.edited[0]['Action'])
        self.assertEqual('Campaign Launch', self.edited[0]['Custom Action'])
        self.assertEqual(0, self.save()['updated'])
        self.edited[0].update({'Action': 'Campaign Launch', 'Custom Action': ''})
        self.assertEqual(1, self.save()['updated'])
        self.refresh()
        self.assertEqual('Campaign Launch', self.edited[0]['Action'])
        self.assertEqual('', self.edited[0]['Custom Action'])

    def test_invalid_table_never_partially_updates_owner_or_rows(self):
        before = deepcopy(self.repo.influencer_planning_steps)
        self.edited[0]['Program Notes'] = 'Valid but must not save'
        for invalid in ({'Action': 'Custom', 'Custom Action': '  '}, {'Action': 'Arbitrary invalid choice'}, {'Action': 'Invoice Due', 'Custom Action': 'would be lost'}, {'Action': 'Invoice Due', 'Date': 'not a date'}):
            self.edited.append(invalid)
            with self.assertRaises(CampaignOpsError): self.save(self.l.id)
            self.edited.pop()
            self.assertEqual(before, self.repo.influencer_planning_steps)
            self.assertEqual(self.t.id, self.campaign.manager_user_id)
        self.edited.append({key: None for key in ('_row_id', *EDITOR_COLUMNS)})
        self.assertEqual(0, self.save()['added'])

    def test_all_legacy_date_constraints_validate_before_any_write(self):
        self.repo.influencer_planning_steps[-1].start_date = date(2026, 6, 10)
        self.refresh()
        self.edited[0]['Program Notes'] = 'Should remain unsaved'
        self.edited[-1]['Date'] = date(2026, 6, 1)
        with patch.object(self.repo, 'update_influencer_planning_step') as update, patch.object(self.repo, 'update_influencer_campaign') as owner:
            with self.assertRaises(CampaignOpsError): self.save(self.l.id)
            update.assert_not_called()
            owner.assert_not_called()

    def test_identity_cannot_be_spoofed_or_duplicated(self):
        for row_id in ('another-campaign-row', self.original[1].id):
            self.edited[0]['_row_id'] = row_id
            with self.assertRaises(CampaignOpsError): self.save()
        self.assertEqual(9, len(self.repo.influencer_planning_steps))

    def test_stale_rows_owner_or_stage_are_not_overwritten(self):
        for change in ('row', 'owner', 'stage', 'added', 'removed'):
            with self.subTest(change=change):
                repo, service, actor, t, l, program = fixture()
                campaign = service.create_campaign(actor, program, 'Stale', t.id)
                original = deepcopy(service.workspace(actor, campaign.id)[1])
                if change == 'row': repo.influencer_planning_steps[0].notes = 'Concurrent edit'
                if change == 'owner': campaign.manager_user_id = l.id
                if change == 'stage': service.advance(actor, campaign.id, 'planning')
                if change == 'added': service.save_row(actor, campaign.id, 'Invoice Due', '', None, '')
                if change == 'removed': service.remove_row(actor, campaign.id, original[0].id)
                with self.assertRaisesRegex(CampaignOpsError, 'changed since'):
                    service.save_changes(actor, campaign.id, t.id, [editor_record(r) for r in original], original, t.id, 'planning')

    def test_failure_uses_one_transaction_for_all_edits(self):
        self.edited[0]['Program Notes'] = 'A note'
        connection = MagicMock()
        with patch('core.campaign_ops.service.connect_to_database', return_value=connection), patch('core.campaign_ops.service.CampaignOpsRepository', return_value=self.repo), patch.object(self.repo, 'update_influencer_campaign', side_effect=RuntimeError('owner write failed')):
            with self.assertRaisesRegex(RuntimeError, 'owner write failed'):
                InfluencerTimelineService().save_changes(self.actor, self.campaign.id, self.l.id,
                    self.edited, self.original, self.original_owner, self.original_stage)
        connection.transaction.assert_called_once()
        self.assertIs(RuntimeError, connection.transaction.return_value.__exit__.call_args.args[0])

    def test_editor_configuration_and_removed_controls(self):
        app = AppTest.from_function(timeline_app).run()
        self.assertFalse(app.exception)
        self.assertEqual(['Lead Owner', 'Manager'], [s.label for s in app.selectbox[:2]])
        self.assertEqual(['**Date**', '**Action**', '**Done**', '**Program Notes**'],
            [w.value for w in app.markdown if w.value in ['**Date**', '**Action**', '**Done**', '**Program Notes**']])
        self.assertEqual(['Choose an action', *ACTION_LIBRARY], field(app, 'Action, row 1').options)
        self.assertEqual(9, len(app.date_input))
        self.assertTrue(all(w.value is None for w in app.date_input))
        self.assertTrue(all(not w.value for w in app.checkbox))
        self.assertFalse(app.dataframe)
        self.assertFalse(any('Custom Actions' in w.value for w in app.markdown))
        self.assertEqual(1, sum(b.label == 'Save Changes' for b in app.button))

    def test_buffered_multiple_cells_and_owner_save_once_reload_once(self):
        app = AppTest.from_function(timeline_app, default_timeout=20).run()
        repo, _, actor, t, l, _ = app.session_state.fixture
        campaign = repo.influencer_campaigns[0]
        apply_edits(app, {
            'edited_rows': {0: {'Date': '2026-06-01', 'Program Notes': 'One'}, 1: {'Action': 'Invoice Due', 'Program Notes': 'Two'}},
            'added_rows': [{'Action': 'Invoice Due'}], 'deleted_rows': [2]})
        select(app, 'Lead Owner').select(l.id)
        self.assertEqual(t.id, campaign.manager_user_id)
        self.assertTrue(all(r.notes is None for r in repo.influencer_planning_steps))
        original_workspace = InfluencerTimelineService.workspace
        with patch.object(InfluencerTimelineService, 'workspace', autospec=True, side_effect=original_workspace) as workspace, patch.object(repo, 'list_influencer_planning_steps', wraps=repo.list_influencer_planning_steps) as row_read:
            button(app, 'Save Changes').click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(l.id, campaign.manager_user_id)
        self.assertEqual('One', repo.influencer_planning_steps[0].notes)
        self.assertEqual('Two', repo.influencer_planning_steps[1].notes)
        self.assertEqual(10, len(repo.influencer_planning_steps))
        # One transaction read (include_inactive), one post-save workspace reload.
        self.assertEqual(2, row_read.call_count)
        self.assertEqual(1, workspace.call_count)

    def test_bulk_saved_custom_and_dates_survive_all_stage_moves(self):
        self.edited[0].update({'Date': date(2026, 9, 10), 'Action': 'Custom', 'Custom Action': 'Internal legal review', 'Program Notes': 'Waiting on client'})
        self.save(self.l.id)
        before = deepcopy(self.repo.influencer_planning_steps)
        for stage in ('planning', 'live', 'recapping'):
            self.service.advance(self.actor, self.campaign.id, stage)
            self.assertEqual(before, self.repo.influencer_planning_steps)
            self.assertEqual(self.l.id, self.campaign.manager_user_id)
        self.assertEqual('complete', self.campaign.influencer_stage)
        self.assertEqual([], self.service.list_campaigns(self.actor, 'recapping')[0])

    def test_bulk_save_preserves_permissions_and_allowed_owner_values(self):
        from core.campaign_ops.models import CampaignOpsUser
        outsider = CampaignOpsUser(id='outsider', display_name='Outsider', role='team_member')
        before = deepcopy(self.repo.influencer_planning_steps)
        with self.assertRaises(CampaignOpsError):
            self.service.save_changes(outsider, self.campaign.id, self.t.id,
                self.edited, self.original, self.original_owner, self.original_stage)
        with self.assertRaises(CampaignOpsError): self.save(self.actor.id)
        self.assertEqual(before, self.repo.influencer_planning_steps)

    def test_all_rows_can_be_removed_then_empty_editor_can_add_again(self):
        app = AppTest.from_function(timeline_app, default_timeout=20).run()
        repo, *_ = app.session_state.fixture
        campaign_id = repo.influencer_campaigns[0].id
        apply_edits(app, {
            'edited_rows': {}, 'deleted_rows': list(range(9)), 'added_rows': []})
        button(app, 'Save Changes').click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(0, len(app.date_input))
        self.assertTrue(all(not row.is_active for row in repo.influencer_planning_steps))
        apply_edits(app, {
            'edited_rows': {}, 'deleted_rows': [], 'added_rows': [{'Action': 'Campaign Launch'}]})
        button(app, 'Save Changes').click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(1, len(app.date_input))
        self.assertEqual(10, len(repo.influencer_planning_steps))
        self.assertEqual(10, repo.influencer_planning_steps[-1].sequence_order)

    def test_custom_inline_roundtrip_and_switch_to_standard(self):
        app = AppTest.from_function(timeline_app).run()
        repo, _, _, t, l, _ = app.session_state.fixture
        original_ids = [r.id for r in repo.influencer_planning_steps]
        edit(app, 0, **{'Action': 'Custom'})
        self.assertEqual('', field(app, 'Custom action, row 1').value)
        self.assertFalse(app.error)
        self.assertEqual(9, len(repo.influencer_planning_steps))
        edit(app, 0, **{'Custom Action': 'Internal legal review', 'Date': '2026-06-01', 'Done': True, 'Program Notes': 'Buffered'})
        select(app, 'Lead Owner').select(l.id)
        with patch.object(InfluencerTimelineService, 'save_changes', autospec=True, side_effect=InfluencerTimelineService.save_changes) as save:
            button(app, 'Save Changes').click().run()
        save.assert_called_once()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        row = repo.influencer_planning_steps[0]
        self.assertEqual('Internal legal review', row.step_title)
        self.assertEqual('timeline_custom', row.step_type)
        self.assertTrue(row.done)
        self.assertEqual('Internal legal review', field(app, 'Custom action, row 1').value)
        self.assertEqual('Buffered', row.notes)
        edit(app, 0, **{'Custom Action': 'Revised review', 'Date': '2026-06-02'})
        button(app, 'Save Changes').click().run()
        self.assertEqual('Revised review', row.step_title)
        edit(app, 0, **{'Action': 'Campaign Launch'})
        button(app, 'Save Changes').click().run()
        self.assertEqual('Campaign Launch', row.step_title)
        self.assertEqual('timeline_manual', row.step_type)
        self.assertFalse(any(w.label.startswith('Custom action') for w in app.text_input))
        self.assertEqual(original_ids, [r.id for r in repo.influencer_planning_steps])

    def test_multiple_inline_custom_rows_survive_delete_and_validation(self):
        app = AppTest.from_function(timeline_app).run()
        repo, *_ = app.session_state.fixture
        apply_edits(app, {'added_rows': [{'Action': 'Custom', 'Custom Action': 'First'}, {'Action': 'Custom'}]})
        token = draft_records(app)[-1]['_draft_id']
        button(app, 'Save Changes').click().run()
        self.assertTrue(app.error)
        self.assertEqual(9, len(repo.influencer_planning_steps))
        self.assertEqual('First', field(app, 'Custom action, row 10').value)
        edit(app, 10, **{'Custom Action': 'Second'})
        apply_edits(app, {'deleted_rows': [9]})
        self.assertEqual(token, draft_records(app)[-1]['_draft_id'])
        self.assertEqual('Second', field(app, 'Custom action, row 10').value)
        button(app, 'Save Changes').click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.error)
        self.assertEqual(10, len(repo.influencer_planning_steps))
        self.assertEqual('Second', repo.influencer_planning_steps[-1].step_title)
