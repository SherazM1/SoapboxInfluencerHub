from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from app.campaign_ops.state import get_sections_for_user, update_viewer_state
from tests import test_campaign_ops_foundation as fixtures


def workspace_app(kind, portfolio=False, create=False):
    import streamlit as st
    from unittest.mock import patch
    from tests.test_campaign_ops_foundation import CampaignOpsFoundationTests
    from app.campaign_ops.content_management import views as content
    from app.campaign_ops.retail_media import views as retail
    from app.campaign_ops.insights import views as insights
    from app.campaign_ops.program_workspace import render_program_workspace
    repo, service, actor, member, _, program_id, _, _ = CampaignOpsFoundationTests()._prompt4c_fixture()
    repo.list_programs_assigned_to_user = lambda user_id, **filters: repo.list_program_portfolio(assigned_user_id=user_id, **filters)
    for name in ('list_retail_media_channels_for_campaigns', 'list_retail_media_activations_for_campaigns', 'list_retail_media_creative_for_campaigns', 'list_retail_media_optimizations_for_campaigns', 'list_retail_media_milestone_rows_for_campaigns', 'list_insights_milestone_rows_for_projects'):
        setattr(repo, name, lambda ids: {item: [] for item in ids})
    if kind == 'content':
        record = service.create_content_program(actor, program_id=program_id, content_program_title='Content', owner_user_id=actor.id)
    elif kind == 'retail':
        record = service.create_retail_media_campaign(actor, program_id=program_id, campaign_title='Retail', owner_user_id=actor.id)
    elif kind == 'insights':
        record = service.create_insights_project(actor, program_id=program_id, project_title='Insights', owner_user_id=actor.id)
    if portfolio and kind in ('all', 'my'):
        from app.campaign_ops.program_list import render_all_programs, render_my_programs
        (render_all_programs if kind == 'all' else render_my_programs)(actor if kind == 'all' else member, service, repo.users, service.list_active_clients())
    elif kind == 'program':
        with patch('app.campaign_ops.program_workspace.CampaignOpsService', return_value=service):
            render_program_workspace(actor, service, program_id)
    else:
        module = {'content': content, 'retail': retail, 'insights': insights}[kind]
        if portfolio:
            module.render_portfolio(actor, service)
        elif create:
            {'content': content.render_new_program, 'retail': retail.render_new_campaign, 'insights': insights.render_new_project_form}[kind](actor, service, repo.users)
        else:
            (insights.render_insights_workspace if kind == 'insights' else module.render_workspace)(actor, service, repo.users, record.id)


class CleanupTests(unittest.TestCase):
    def test_navigation_and_retired_state(self):
        _, _, admin, member, _, _, _, _ = fixtures.CampaignOpsFoundationTests()._prompt4c_fixture()
        expected = ['All Programs', 'My Programs', 'Influencer', 'Retail Media', 'eCommerce / Content', 'Insights', 'Social Media Management']
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
            'content': ['Overview', 'Deliverables', 'Submission & Publication', 'Invoicing', 'Timeline', 'Notes', 'Activity'],
            'retail': ['Overview', 'Activations / Flights', 'Creative & Approvals', 'Timeline', 'Notes', 'Activity'],
            'insights': ['Overview', 'Timeline', 'Activity'],
        }
        for kind, tabs in expected.items():
            with self.subTest(kind=kind), patch('psycopg.connect', side_effect=AssertionError('Tests must not connect to a database')):
                app = AppTest.from_function(workspace_app, args=(kind,)).run(timeout=20)
                self.assertEqual([], list(app.exception))
                self.assertEqual(tabs, [tab.label for tab in app.tabs])



    def test_portfolios_render_with_one_open_control(self):
        for kind in ('all', 'my', 'content', 'retail', 'insights'):
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


    def test_simplified_creation_forms_render(self):
        for kind in ('content', 'retail', 'insights'):
            with self.subTest(kind=kind):
                app = AppTest.from_function(workspace_app, args=(kind, False, True)).run()
                self.assertEqual([], list(app.exception))
                self.assertTrue(any('Create' in button.label for button in app.button))
                self.assertEqual([], list(app.number_input))


def navigation_app(actor, viewer):
    from app.campaign_ops.components import render_section_navigation
    render_section_navigation(actor, viewer)
