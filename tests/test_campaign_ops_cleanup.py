from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from app.campaign_ops.state import get_sections_for_user, update_viewer_state
from tests import test_campaign_ops_foundation as fixtures


def workspace_app(kind, portfolio=False, create=False):
    import streamlit as st
    from tests.test_campaign_ops_foundation import CampaignOpsFoundationTests
    from app.campaign_ops.influencer import views, live_views, recap_views
    from app.campaign_ops.content_management import views as content
    from app.campaign_ops.retail_media import views as retail
    from app.campaign_ops.insights import views as insights
    from app.campaign_ops.program_workspace import render_program_workspace

    if 'fixture' not in st.session_state:
        fixture = CampaignOpsFoundationTests()._prompt4c_fixture()
        repo, service, actor, _, _, program_id, _, _ = fixture
        repo.list_programs_assigned_to_user = lambda user_id, **filters: repo.list_program_portfolio(assigned_user_id=user_id, **filters)
        # This fixture has no retail or Insights child rows; supply its missing batch readers.
        for name in ('list_retail_media_channels_for_campaigns', 'list_retail_media_activations_for_campaigns', 'list_retail_media_creative_for_campaigns', 'list_retail_media_optimizations_for_campaigns', 'list_retail_media_milestone_rows_for_campaigns', 'list_insights_milestone_rows_for_projects'):
            setattr(repo, name, lambda ids: {item: [] for item in ids})
        if kind in ('planning', 'live', 'recap', 'creator', 'requirement', 'live_return'):
            record = service.create_influencer_campaign(actor, program_id=program_id, campaign_title='Render campaign', manager_user_id=actor.id)
            if kind != 'planning':
                service.transition_influencer_campaign_to_live(actor, record.id)
            if kind in ('creator', 'live_return'):
                service.create_influencer_live_creator(actor, record.id, 'Creator', impressions_reporting_required=True)
            if kind in ('recap', 'requirement', 'live_return'):
                service.transition_influencer_campaign_to_recapping(actor, record.id, allow_override=True)
            if kind == 'requirement':
                resource = service.create_resource(actor, program_id, 'Report', 'Custom', url='https://example.com/report')
                service.create_influencer_recap_requirement(actor, record.id, 'Client Recap', 'Final report', required=True, resource_id=resource.id)
        elif kind == 'content':
            record = service.create_content_program(actor, program_id=program_id, content_program_title='Content', owner_user_id=actor.id)
        elif kind == 'retail':
            record = service.create_retail_media_campaign(actor, program_id=program_id, campaign_title='Retail', owner_user_id=actor.id)
        elif kind == 'insights':
            record = service.create_insights_project(actor, program_id=program_id, project_title='Insights', owner_user_id=actor.id)
        else:
            record = None
        st.session_state.fixture = fixture
        st.session_state.record_id = record.id if record else program_id
    repo, service, actor, _, _, program_id, _, _ = st.session_state.fixture
    record_id = st.session_state.record_id
    renderers = {'planning': views.render_workspace, 'live': live_views.render_live_workspace,
                 'recap': recap_views.render_recap_workspace, 'content': content.render_workspace,
                 'retail': retail.render_workspace, 'insights': insights.render_insights_workspace}
    if create:
        if kind == 'planning':
            views.render_new_campaign(actor, service, repo.users)
        elif kind == 'content':
            content.render_new_program(actor, service, repo.users)
        elif kind == 'retail':
            retail.render_new_campaign(actor, service, repo.users)
        elif kind == 'insights':
            insights.render_new_project_form(actor, service, repo.users)
    elif portfolio:
        if kind in ('all', 'my'):
            from app.campaign_ops.program_list import render_all_programs, render_my_programs
            renderer = render_all_programs if kind == 'all' else render_my_programs
            renderer(st.session_state.fixture[3] if kind == 'my' else actor, service, repo.users, service.list_active_clients())
        elif kind == 'planning':
            views.render_portfolio(actor, service, None)
        elif kind == 'live':
            live_views.render_live_portfolio(actor, service, None)
        elif kind == 'recap':
            recap_views.render_recap_portfolio(actor, service, None)
        else:
            {'content': content, 'retail': retail, 'insights': insights}[kind].render_portfolio(actor, service)
    elif kind == 'program':
        from unittest.mock import patch
        with patch('app.campaign_ops.program_workspace.CampaignOpsService', return_value=service):
            render_program_workspace(actor, service, program_id)
    elif kind == 'creator':
        live_views.render_creator_blocker_editor(actor, service, service.get_influencer_campaign_detail(actor, record_id))
    elif kind == 'live_return':
        campaign = service.get_influencer_campaign_detail(actor, record_id)
        if campaign.influencer_stage == 'recapping':
            recap_views.render_live_blocker_return(actor, service, service.get_influencer_recap_workspace_summary(actor, record_id))
    elif kind == 'requirement':
        recap_views.render_requirement_blocker_editor(actor, service, service.get_influencer_campaign_detail(actor, record_id))
    else:
        renderers[kind](actor, service, repo.users, record_id)


class CleanupTests(unittest.TestCase):
    def test_navigation_and_retired_state(self):
        _, _, admin, member, _, _, _, _ = fixtures.CampaignOpsFoundationTests()._prompt4c_fixture()
        expected = ['All Programs', 'My Programs', 'Influencer', 'Retail Media', 'eCommerce / Content', 'Insights']
        for actor in (admin, member):
            self.assertEqual(expected, get_sections_for_user(actor, actor.display_name))
            for retired in ('Cross-Team Dashboard', 'My Work', 'Requests', 'Administration'):
                state = {'campaign_ops_section': retired, 'campaign_ops_request_filters': {}, 'campaign_ops_previous_viewer': actor.display_name}
                update_viewer_state(state, actor.display_name, actor)
                self.assertIn(state['campaign_ops_section'], expected)
                self.assertNotIn('campaign_ops_request_filters', state)
        state = {'campaign_ops_section': 'New Program', 'campaign_ops_previous_viewer': admin.display_name}
        update_viewer_state(state, admin.display_name, admin)
        self.assertEqual('New Program', state['campaign_ops_section'])
        update_viewer_state(state, member.display_name, member)
        self.assertEqual('My Programs', state['campaign_ops_section'])

    def test_retired_route_does_not_query_or_render(self):
        from app.pages import campaigns
        _, _, actor, _, _, _, _, _ = fixtures.CampaignOpsFoundationTests()._prompt4c_fixture()
        service = Mock()
        with patch.object(campaigns.st, 'session_state', {}), patch.object(campaigns.st, 'rerun') as rerun:
            campaigns.render_active_section('Requests', 'Bailey', actor, service, [])
        rerun.assert_called_once()
        self.assertEqual([], service.mock_calls)

    def test_remaining_workspaces_render(self):
        expected = {
            'program': ['Overview', 'Tasks', 'Timeline', 'Notes', 'Team', 'Activity'],
            'planning': ['Overview', 'Planning Sequence', 'Timeline', 'Program Notes', 'Activity'],
            'live': ['Overview', 'Live Checkpoints', 'Creator Waves', 'Exceptions', 'Timeline', 'Program Notes', 'Activity'],
            'recap': ['Overview', 'Recap Checklist', 'Timeline', 'Program Notes', 'Activity'],
            'content': ['Overview', 'Deliverables', 'Submission & Publication', 'Invoicing', 'Timeline', 'Notes', 'Activity'],
            'retail': ['Overview', 'Activations / Flights', 'Creative & Approvals', 'Timeline', 'Notes', 'Activity'],
            'insights': ['Overview', 'Timeline', 'Activity'],
        }
        for kind, tabs in expected.items():
            with self.subTest(kind=kind), patch('psycopg.connect', side_effect=AssertionError('Tests must not connect to a database')):
                app = AppTest.from_function(workspace_app, args=(kind,)).run(timeout=20)
                self.assertEqual([], list(app.exception))
                self.assertEqual(tabs, [tab.label for tab in app.tabs])

    def test_creator_blocker_can_be_resolved_without_tracker(self):
        app = AppTest.from_function(workspace_app, args=('creator',)).run()
        self.assertEqual([], list(app.exception))
        app.selectbox[1].select('complete')
        app.text_input[0].set_value('https://example.com/final')
        app.number_input[0].set_value(123)
        app.button[0].click().run()
        self.assertEqual([], list(app.exception))
        _, service, actor, *_ = app.session_state.fixture
        creator = service.list_influencer_live_creators(actor, app.session_state.record_id)[0]
        self.assertEqual('https://example.com/final', creator.content_url)
        self.assertEqual(123, creator.latest_impressions)
        self.assertTrue(creator.impressions_reporting_required)

    def test_recap_requirement_can_be_resolved_without_tracker(self):
        app = AppTest.from_function(workspace_app, args=('requirement',)).run()
        self.assertEqual([], list(app.exception))
        app.selectbox[1].select('complete')
        app.text_area[0].set_value('Report delivered')
        app.button[0].click().run()
        self.assertEqual([], list(app.exception))
        _, service, actor, *_ = app.session_state.fixture
        item = service.list_influencer_recap_requirements(actor, app.session_state.record_id)[0]
        self.assertEqual('complete', item.status)
        self.assertTrue(item.required)
        self.assertIsNotNone(item.resource_id)
        self.assertEqual('Report delivered', item.notes)

    def test_portfolios_render_with_one_open_control(self):
        for kind in ('all', 'my', 'planning', 'live', 'recap', 'content', 'retail', 'insights'):
            with self.subTest(kind=kind), patch('psycopg.connect', side_effect=AssertionError('No database in UI tests')):
                app = AppTest.from_function(workspace_app, args=(kind, True)).run(timeout=20)
                self.assertEqual([], list(app.exception))
                self.assertFalse(any('summary' in item.label.lower() for item in app.expander))
                self.assertTrue(any('Open' in button.label for button in app.button))

    def test_visible_navigation_buttons(self):
        _, _, actor, *_ = fixtures.CampaignOpsFoundationTests()._prompt4c_fixture()
        app = AppTest.from_function(navigation_app, args=(actor, 'Bailey')).run()
        self.assertEqual([], list(app.exception))
        self.assertEqual(get_sections_for_user(actor, 'Bailey'), [button.label for button in app.button])

    def test_recap_return_to_live_preserves_records_and_requires_click(self):
        app = AppTest.from_function(workspace_app, args=('live_return',)).run()
        self.assertEqual([], list(app.exception))
        _, service, actor, *_ = app.session_state.fixture
        campaign_id = app.session_state.record_id
        self.assertEqual('recapping', service.get_influencer_campaign_detail(actor, campaign_id).influencer_stage)
        before = service.get_influencer_recap_workspace_summary(actor, campaign_id).recap_record
        self.assertIsNotNone(before)
        app.button[0].click().run()
        self.assertEqual([], list(app.exception))
        self.assertEqual('live', service.get_influencer_campaign_detail(actor, campaign_id).influencer_stage)
        self.assertEqual(campaign_id, app.session_state['campaign_ops_selected_influencer_live_campaign_id'])
        self.assertEqual('Live', app.session_state['campaign_ops_influencer_view'])
        service.transition_influencer_campaign_to_recapping(actor, campaign_id, allow_override=True)
        self.assertEqual(before.id, service.get_influencer_recap_workspace_summary(actor, campaign_id).recap_record.id)

    def test_simplified_creation_forms_render(self):
        for kind in ('planning', 'content', 'retail', 'insights'):
            with self.subTest(kind=kind):
                app = AppTest.from_function(workspace_app, args=(kind, False, True)).run()
                self.assertEqual([], list(app.exception))
                self.assertTrue(any('Create' in button.label for button in app.button))
                self.assertEqual([], list(app.number_input))


def navigation_app(actor, viewer):
    from app.campaign_ops.components import render_section_navigation
    render_section_navigation(actor, viewer)
