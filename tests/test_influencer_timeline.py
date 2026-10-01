from __future__ import annotations

from copy import deepcopy
from datetime import date
import unittest
from tests.operational_editor_helpers import apply_edits, edit, field, draft_records
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer_timeline import ACTION_LIBRARY, DEFAULT_ACTIONS, EDITOR_COLUMNS, InfluencerTimelineService, action_title, sort_timeline
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.repository import CampaignOpsRepository
from tests import test_campaign_ops_foundation as foundation


def fixture():
    repo, _, admin, t, l, program_id, _, _ = foundation.CampaignOpsFoundationTests()._prompt4c_fixture()
    primary = next(a for a in repo.assignments if a.is_primary and a.assignment_role == "program_owner")
    primary.user_id = t.id
    manager = CampaignOpsUser(id="55555555-5555-4555-8555-555555555555", display_name="Fixture Manager", role="team_member")
    repo.users.append(manager)
    workstream = next(w for w in repo.workstreams if w.program_id == program_id and w.workstream_type == "influencer")
    workstream.owner_user_id = manager.id
    existing_roster = repo.list_workflow_role_users
    repo.list_workflow_role_users = lambda workflow, role: [manager] if workflow == "influencer" and role == "manager" else existing_roster(workflow, role)
    repo.lock_influencer_timeline_program = repo.get_program
    repo.get_influencer_campaign_for_update = repo.get_influencer_campaign
    repo.list_influencer_timeline_campaigns = lambda stage: [c for c in repo.influencer_campaigns if c.is_active and c.influencer_stage == stage]
    return repo, InfluencerTimelineService(repo), admin, t, l, program_id


def timeline_app(empty=False):
    import streamlit as st
    from tests.test_influencer_timeline import fixture
    from app.campaign_ops.influencer.views import render_influencer
    if 'fixture' not in st.session_state:
        repo, service, admin, t, l, program_id = fixture()
        st.session_state.fixture = (repo, service, admin, t, l, program_id)
        if not empty:
            campaign = service.create_campaign(admin, program_id, 'Timeline campaign', t.id)
            st.session_state['campaign_ops_selected_influencer_campaign_id'] = campaign.id
    repo, service, admin, t, l, program_id = st.session_state.fixture
    render_influencer(admin, service, repo.users)


def button(app, label):
    return next(item for item in app.button if item.label == label)


def select(app, label):
    return next(item for item in app.selectbox if item.label == label)


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.repo, self.service, self.admin, self.t, self.l, self.program_id = fixture()
        self.campaign = self.service.create_campaign(self.admin, self.program_id, 'Timeline', self.t.id)

    def test_exact_defaults_and_library(self):
        expected = (
            'Application out to influencers',
            'Soapbox to send first round of influencers & brief for review',
            'Client to send brief and influencer feedback / approvals',
            'Soapbox to hire influencers', 'Influencer drafts are due',
            'Influencer resubmissions are due',
            'Soapbox to send first round of influencer content for review',
            'Client to send content feedback / approvals',
            'Influencers begin going live in waves',
        )
        self.assertEqual(expected, DEFAULT_ACTIONS)
        rows = self.service.workspace(self.admin, self.campaign.id)[1]
        self.assertEqual(list(expected), [r.step_title for r in rows])
        self.assertEqual(list(range(1, 10)), [r.sequence_order for r in rows])
        self.assertTrue(all(r.due_date is None and r.notes is None for r in rows))
        self.assertEqual(34, len(ACTION_LIBRARY))
        self.assertEqual(len(ACTION_LIBRARY), len(set(ACTION_LIBRARY)))
        self.assertTrue(set(expected) <= set(ACTION_LIBRARY))
        for optional in ('Client to send content / messaging guidelines', 'Soapbox to ship product(s) to influencers', 'Soapbox to send second round of influencer content for review, if needed'):
            self.assertIn(optional, ACTION_LIBRARY)
            self.assertNotIn(optional, DEFAULT_ACTIONS)
        for name in ('Apple', 'Dolores', 'Hasbro', 'VeSync', 'Taylor', 'Lauren'):
            self.assertFalse(any(name in action for action in ACTION_LIBRARY))
        self.assertEqual('Custom', ACTION_LIBRARY[-1])
        self.assertEqual('Internal kickoff', action_title('Custom', 'Internal kickoff'))
        for action, custom in [('Custom', ''), ('not in library', '')]:
            with self.assertRaises(CampaignOpsError): action_title(action, custom)

    def test_defaults_never_reseed_and_owner_is_canonical(self):
        ids = [r.id for r in self.service.workspace(self.admin, self.campaign.id)[1]]
        for owner in (self.l, self.t):
            self.service.change_owner(self.admin, self.campaign.id, owner.id)
            self.assertEqual(owner.id, self.campaign.manager_user_id)
            self.assertEqual(ids, [r.id for r in self.service.workspace(self.admin, self.campaign.id)[1]])
        self.service.remove_row(self.admin, self.campaign.id, ids[0])
        self.service.workspace(self.admin, self.campaign.id)
        self.assertEqual(9, len(self.repo.influencer_planning_steps))
        self.assertEqual(8, len(self.service.workspace(self.admin, self.campaign.id)[1]))
        with self.assertRaises(CampaignOpsError): self.service.change_owner(self.admin, self.campaign.id, self.admin.id)
        with self.assertRaises(CampaignOpsError): self.service.create_campaign(self.admin, self.program_id, 'Bad owner', self.admin.id)
        with self.assertRaises(CampaignOpsError): self.service.create_campaign(self.admin, self.program_id, 'Timeline', self.t.id)
        self.assertEqual(1, len(self.repo.influencer_campaigns))
        self.assertEqual(['Bailey', 'T', 'L'], [u.display_name for u in self.repo.users[:3]])

    def test_row_crud_dates_notes_and_order(self):
        rows = self.service.workspace(self.admin, self.campaign.id)[1]
        early, late = date(2026, 5, 1), date(2026, 5, 20)
        self.service.save_row(self.admin, self.campaign.id, 'Campaign Launch', '', late, 'Waiting on client', rows[0].id)
        self.service.save_row(self.admin, self.campaign.id, 'Invoice Due', '', early, 'Manual note', rows[1].id)
        custom = self.service.save_row(self.admin, self.campaign.id, 'Custom', 'Internal kickoff', date(2026, 5, 10), 'Kickoff note')
        ordered = self.service.workspace(self.admin, self.campaign.id)[1]
        self.assertEqual([rows[1].id, custom.id, rows[0].id], [r.id for r in ordered[:3]])
        self.assertEqual([r.id for r in rows[2:]], [r.id for r in ordered[3:]])
        self.service.save_row(self.admin, self.campaign.id, 'Custom', 'Revised kickoff', early, 'Revised note', custom.id)
        ordered = self.service.workspace(self.admin, self.campaign.id)[1]
        self.assertEqual([rows[1].id, custom.id], [r.id for r in ordered[:2]])
        self.assertEqual('Revised note', custom.notes)
        self.assertEqual(10, len(self.repo.influencer_planning_steps))
        self.service.save_row(self.admin, self.campaign.id, 'Custom', 'Revised kickoff', None, '', custom.id)
        self.assertEqual(custom.id, self.service.workspace(self.admin, self.campaign.id)[1][-1].id)
        self.service.remove_row(self.admin, self.campaign.id, custom.id)
        self.assertFalse(custom.is_active)
        self.assertEqual(10, len(self.repo.influencer_planning_steps))
        with self.assertRaises(CampaignOpsError): self.service.save_row(self.admin, self.campaign.id, 'Campaign Launch', '', None, '', custom.id)

    def test_sort_ties_are_deterministic(self):
        rows = self.service.workspace(self.admin, self.campaign.id)[1]
        rows[1].sequence_order = rows[0].sequence_order
        rows[0].due_date = rows[1].due_date = date(2026, 1, 1)
        self.assertEqual([r.id for r in sort_timeline(rows)], [r.id for r in sort_timeline(list(reversed(rows)))])

    def test_permission_boundaries_and_cross_campaign_row_rejection(self):
        outsider = CampaignOpsUser(id='outsider', display_name='Outsider', role='team_member')
        self.assertEqual([], self.service.list_campaigns(outsider, 'planning')[0])
        row = self.service.workspace(self.admin, self.campaign.id)[1][0]
        for operation in (
            lambda: self.service.workspace(outsider, self.campaign.id),
            lambda: self.service.change_owner(outsider, self.campaign.id, self.l.id),
            lambda: self.service.advance(outsider, self.campaign.id, 'planning'),
            lambda: self.service.save_row(outsider, self.campaign.id, 'Campaign Launch', '', None, ''),
            lambda: self.service.remove_row(outsider, self.campaign.id, row.id),
        ):
            with self.assertRaises(CampaignOpsError): operation()
        other = self.service.create_campaign(self.admin, self.program_id, 'Other', self.l.id)
        with self.assertRaises(CampaignOpsError): self.service.remove_row(self.admin, other.id, row.id)
        self.assertTrue(row.is_active)
        self.service.advance(self.t, self.campaign.id, 'planning')
        self.assertEqual('live', self.campaign.influencer_stage)

    def test_lightweight_batch_reads(self):
        with patch.object(self.repo, 'list_influencer_planning_steps_for_campaigns', wraps=self.repo.list_influencer_planning_steps_for_campaigns) as batch, patch.object(self.repo, 'get_influencer_campaign_detail', side_effect=AssertionError('No portfolio joins')), patch.object(self.repo, 'list_influencer_live_creators', side_effect=AssertionError('No creator reads')):
            self.service.list_campaigns(self.admin, 'planning')
            batch.assert_called_once_with([self.campaign.id])
            self.service.workspace(self.admin, self.campaign.id)
        repository = CampaignOpsRepository()
        with patch.object(repository, '_fetch_all', return_value=[]) as fetch:
            repository.list_influencer_timeline_campaigns('live')
            sql, params, _ = fetch.call_args.args
            self.assertNotIn('join', sql.lower())
            self.assertEqual(('live',), params)
        with patch.object(repository, '_fetch_one', return_value=None) as fetch:
            repository.get_influencer_campaign_for_update('id')
            self.assertIn('for update', fetch.call_args.args[0])
            repository.lock_influencer_timeline_program('program-id')
            self.assertIn('for update', fetch.call_args.args[0])
            self.assertEqual(('program-id',), fetch.call_args.args[1])

    def test_ui_owner_and_direct_columns_all_stages_confirmation(self):
        app = AppTest.from_function(timeline_app, default_timeout=20).run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(['Planning', 'Live', 'Recapping'], app.radio[0].options)
        self.assertEqual('Lead Owner', app.selectbox[0].label)
        repo, service, actor, t, l, _ = app.session_state.fixture
        select(app, 'Lead Owner').select(l.id)
        button(app, 'Save Changes').click().run()
        repo, service, actor, t, l, _ = app.session_state.fixture
        campaign = repo.influencer_campaigns[0]
        self.assertEqual(l.id, campaign.manager_user_id)
        for stage, label, target in [('planning', 'Move to Live', 'live'), ('live', 'Move to Recapping', 'recapping'), ('recapping', 'Mark Complete', 'complete')]:
            self.assertEqual(9, len(app.checkbox))
            self.assertEqual(9, len(app.date_input))
            button(app, label).click().run()
            self.assertEqual(stage, campaign.influencer_stage)
            button(app, 'Cancel').click().run()
            self.assertEqual(stage, campaign.influencer_stage)
            button(app, label).click().run()
            button(app, 'Confirm').click().run()
            self.assertEqual([], list(app.exception))
            self.assertEqual(target, campaign.influencer_stage)
            self.assertEqual(9, len(repo.influencer_planning_steps))
            self.assertEqual(1, len(repo.influencer_campaigns))
        self.assertEqual([], service.list_campaigns(actor, 'recapping')[0])
        self.assertEqual(l.id, campaign.manager_user_id)

    def test_ui_create_once_and_reopen(self):
        app = AppTest.from_function(timeline_app, args=(True,), default_timeout=20).run()
        select(app, 'Owner').select('T')
        next(item for item in app.text_input if item.label == 'Campaign').set_value('New campaign')
        button(app, 'Create Campaign').click().run()
        self.assertEqual([], list(app.exception))
        repo, *_ = app.session_state.fixture
        self.assertEqual(1, len(repo.influencer_campaigns))
        self.assertEqual(9, len(repo.influencer_planning_steps))
        app.run()
        button(app, 'Back to campaigns').click().run()
        button(app, 'Open').click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(9, len(repo.influencer_planning_steps))

    def test_ui_add_custom_edit_notes_date_and_remove(self):
        app = AppTest.from_function(timeline_app).run()
        repo, service, actor, *_ = app.session_state.fixture
        campaign_id = repo.influencer_campaigns[0].id
        apply_edits(app, {'added_rows': [{'Action': 'Custom', 'Custom Action': 'Manual action', 'Date': '2026-05-10', 'Program Notes': 'First note'}]})
        self.assertEqual(9, len(repo.influencer_planning_steps))
        button(app, 'Save Changes').click().run()
        rows = service.workspace(actor, campaign_id)[1]
        self.assertEqual('Manual action', rows[0].step_title)
        edit(app, 0, **{'Date': '2026-05-02', 'Program Notes': 'Changed note'})
        button(app, 'Save Changes').click().run()
        self.assertEqual('Changed note', rows[0].notes)
        self.assertEqual(date(2026, 5, 2), rows[0].due_date)
        apply_edits(app, {'deleted_rows': [0]})
        button(app, 'Save Changes').click().run()
        self.assertFalse(rows[0].is_active)
        self.assertEqual(9, len(app.date_input))

    def test_stage_lists_exclude_other_stages_inactive_and_complete(self):
        live = self.service.create_campaign(self.admin, self.program_id, 'Live campaign', self.l.id)
        recap = self.service.create_campaign(self.admin, self.program_id, 'Recap campaign', self.t.id)
        done = self.service.create_campaign(self.admin, self.program_id, 'Completed campaign', self.t.id)
        inactive = self.service.create_campaign(self.admin, self.program_id, 'Inactive campaign', self.t.id)
        for campaign, stages in ((live, ('planning',)), (recap, ('planning', 'live')), (done, ('planning', 'live', 'recapping'))):
            for stage in stages:
                self.service.advance(self.admin, campaign.id, stage)
        self.service.deactivate_influencer_campaign(self.admin, inactive.id)
        for stage, expected in [('planning', self.campaign), ('live', live), ('recapping', recap)]:
            visible, timelines = self.service.list_campaigns(self.admin, stage)
            self.assertEqual([expected.id], [c.id for c in visible])
            self.assertEqual({expected.id}, set(timelines))
        self.assertEqual(45, len(self.repo.influencer_planning_steps))

    def test_existing_campaigns_are_never_seeded_or_imported(self):
        old = self.service.create_influencer_campaign(self.admin, program_id=self.program_id,
            campaign_title='Existing', manager_user_id=self.l.id)
        self.assertEqual([], self.service.workspace(self.admin, old.id)[1])
        self.service.advance(self.admin, old.id, 'planning')
        self.service.create_influencer_live_checkpoint(self.admin, old.id, 'Historical checkpoint')
        self.service.create_influencer_creator_wave(self.admin, old.id, 1, wave_name='Historical wave')
        self.assertEqual([], self.service.workspace(self.admin, old.id)[1])
        self.service.advance(self.admin, old.id, 'live')
        self.assertEqual([], self.service.workspace(self.admin, old.id)[1])
        self.assertEqual(9, len(self.repo.influencer_planning_steps))

    def test_owner_does_not_add_assignments_or_grant_write_access(self):
        self.repo.assignments = [a for a in self.repo.assignments if a.user_id != self.l.id]
        before = deepcopy(self.repo.assignments)
        self.service.change_owner(self.admin, self.campaign.id, self.l.id)
        self.assertEqual(before, self.repo.assignments)
        self.assertEqual([], self.service.list_campaigns(self.l, 'planning')[0])
        with self.assertRaises(CampaignOpsError):
            self.service.workspace(self.l, self.campaign.id)
        with self.assertRaises(CampaignOpsError):
            self.service.advance(self.l, self.campaign.id, 'planning')
        with self.assertRaises(CampaignOpsError):
            self.service.save_row(self.l, self.campaign.id, 'Campaign Launch', '', None, '')

    def test_existing_hidden_row_data_and_date_constraint_remain(self):
        row = self.service.workspace(self.admin, self.campaign.id)[1][0]
        self.service.update_influencer_planning_step(self.admin, self.campaign.id, row.id,
            step_description='Historical description', start_date=date(2026, 5, 10), status='complete')
        with self.assertRaises(CampaignOpsError):
            self.service.save_row(self.admin, self.campaign.id, 'Campaign Launch', '', date(2026, 5, 1), 'note', row.id)
        self.service.save_row(self.admin, self.campaign.id, 'Campaign Launch', '', date(2026, 5, 20), 'note', row.id)
        self.assertEqual('Historical description', row.step_description)
        self.assertEqual('complete', row.status)
        self.assertEqual(date(2026, 5, 10), row.start_date)

    def test_create_uses_one_transaction_and_failure_propagates_for_rollback(self):
        connection = MagicMock()
        unbound = InfluencerTimelineService()
        with patch('core.campaign_ops.service.connect_to_database', return_value=connection), patch('core.campaign_ops.service.CampaignOpsRepository', return_value=self.repo), patch.object(self.repo, 'create_influencer_planning_step', side_effect=RuntimeError('write failed')):
            with self.assertRaisesRegex(RuntimeError, 'write failed'):
                unbound.create_campaign(self.admin, self.program_id, 'Atomic creation', self.t.id)
        connection.transaction.assert_called_once()
        exit_args = connection.transaction.return_value.__exit__.call_args.args
        self.assertIs(RuntimeError, exit_args[0])
        connection.close.assert_called_once()

    def test_empty_custom_action_does_not_persist_partial_row(self):
        app = AppTest.from_function(timeline_app).run()
        repo, *_ = app.session_state.fixture
        apply_edits(app, {'added_rows': [{'Action': 'Custom', 'Program Notes': 'Unsaved notes'}]})
        button(app, 'Save Changes').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('Enter a custom action' in e.value for e in app.error))
        self.assertEqual(9, len(repo.influencer_planning_steps))
        self.assertTrue(all(r.notes is None for r in repo.influencer_planning_steps))
