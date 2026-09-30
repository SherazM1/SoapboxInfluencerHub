from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from core.campaign_ops.exceptions import CampaignOpsPermissionError, CampaignOpsValidationError
from core.campaign_ops.permissions import ACCESS_DENIED, can_view_program, program_access_allowed
from core.campaign_ops.program_routing import ProgramRoutingService
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.influencer_timeline import InfluencerTimelineService, editor_record
from tests.test_campaign_ops_roster_new_program import RosterRepository, button, selectbox
from tests.test_campaign_ops_new_program_flow import page_app


class ProgramAccessTests(unittest.TestCase):
    def setUp(self):
        self.repo = RosterRepository()
        self.service = CampaignOpsService(self.repo)
        self.router = ProgramRoutingService(self.repo)
        self.timeline = InfluencerTimelineService(self.repo)
        self.users = {u.display_name: u for u in self.repo.users}
        self.admin = self.users['Bailey']
        self.programs = {}
        self.records = {}
        for name, workflow, lead, manager in (
            ('First', 'influencer', 'Taylor', 'Allyn'),
            ('Second', 'influencer', 'Lauren', 'Carly'),
            ('Social', 'smm', 'Ava', 'Maren'),
            ('Content', 'ecommerce', 'Emma', 'Kate'),
            ('Retail', 'retail_media', 'Chloe', 'Chloe'),
            ('Research', 'insights', 'Emma', 'Kate'),
        ):
            pid = self.service.create_program_with_workstreams_and_assignments(
                self.admin, name, new_client_name='Access fixture', primary_workstream_type=workflow,
                primary_owner_user_id=self.users[lead].id,
                workstream_lead_user_ids={workflow: self.users[manager].id})
            self.programs[name] = pid
            if workflow == 'influencer':
                record = self.timeline.create_campaign(self.admin, pid, name, self.users[lead].id)
            elif workflow == 'retail_media':
                record = self.service.create_retail_media_campaign(self.admin, program_id=pid,
                    campaign_title=name, owner_user_id=self.users[manager].id)
            elif workflow == 'ecommerce':
                record = self.service.create_content_program(self.admin, program_id=pid,
                    content_program_title=name, owner_user_id=self.users[manager].id)
            elif workflow == 'insights':
                record = self.service.create_insights_project(self.admin, program_id=pid,
                    project_title=name, owner_user_id=self.users[manager].id)
            else:
                continue
            self.records[name] = record

    def visible(self, name):
        return {r.id for r in self.router.list_registry(self.users[name])}

    def test_admin_lead_manager_and_dual_role_matrix_same_for_both_lists(self):
        expected = {'Bailey': set(self.programs), 'Jordon': set(self.programs),
            'Taylor': {'First'}, 'Lauren': {'Second'}, 'Ava': {'Social'},
            'Allyn': {'First'}, 'Maren': {'Social'}, 'Carly': {'Second'},
            'Emma': {'Content', 'Research'}, 'Kate': {'Content', 'Research'}, 'Chloe': {'Retail'}}
        for user, names in expected.items():
            with self.subTest(user=user):
                wanted = {self.programs[name] for name in names}
                rows = self.router.list_registry(self.users[user])
                self.assertEqual(wanted, {r.id for r in rows})
                self.assertEqual(len(wanted), len(rows))
                self.assertEqual(wanted, {r.id for r in self.service.list_user_programs(self.users[user])})
                for pid in self.programs.values():
                    if pid in wanted:
                        self.router.resolve(self.users[user], pid)
                    else:
                        with self.assertRaisesRegex(CampaignOpsPermissionError, ACCESS_DENIED):
                            self.router.resolve(self.users[user], pid)

    def test_union_and_no_duplicate_rows(self):
        pid = self.programs['First']
        ws = self.repo.list_workstreams_by_program(pid)[0]
        self.service.reassign_workstream_lead(self.admin, pid, ws.id, self.users['Ava'].id)
        self.assertEqual({pid, self.programs['Social']}, self.visible('Ava'))
        self.service.reassign_primary_program_owner(self.admin, pid, self.users['Ava'].id)
        self.assertEqual(2, len(self.router.list_registry(self.users['Ava'])))

    def test_unrelated_assignments_secondary_ownership_and_roster_are_not_grants(self):
        pid = self.programs['First']
        outsider = self.users['Maren']
        for role in ('contributor', 'reviewer', 'approver', 'viewer', 'admin_oversight', 'program_owner'):
            self.repo.create_assignment(pid, outsider.id, role, is_primary=False)
        secondary = self.repo.create_workstream(pid, 'retail_media', owner_user_id=outsider.id)
        self.repo.create_assignment(pid, outsider.id, 'workstream_lead', workstream_id=secondary.id)
        self.assertNotIn(pid, self.visible('Maren'))
        self.assertIn(outsider.id, {u.id for u in self.repo.list_workflow_role_users('influencer', 'manager')})
        # An active workstream lead on the primary workstream is a valid grant independently of owner_user_id.
        primary = next(w for w in self.repo.workstreams if w.program_id == pid and w.workstream_type == 'influencer')
        grant = self.repo.create_assignment(pid, outsider.id, 'workstream_lead', workstream_id=primary.id)
        self.assertIn(pid, self.visible('Maren'))
        grant.is_active = False
        self.assertNotIn(pid, self.visible('Maren'))

    def test_workstream_owner_without_assignment_is_a_valid_manager(self):
        pid = self.programs['First']
        for assignment in self.repo.assignments:
            if assignment.program_id == pid and assignment.user_id == self.users['Allyn'].id:
                assignment.is_active = False
        self.assertIn(pid, self.visible('Allyn'))
        self.router.resolve(self.users['Allyn'], pid)

    def test_renaming_display_names_does_not_change_access(self):
        before = {u.id: self.visible(name) for name, u in self.users.items() if u.is_active}
        for user in self.users.values():
            user.display_name = 'Same arbitrary display name'
        for user in self.users.values():
            if not user.is_active:
                continue
            self.assertEqual(before[user.id], {r.id for r in self.router.list_registry(user)})

    def test_all_child_records_share_program_access_and_no_legacy_owner_bypass(self):
        getters = {'First': self.service.get_influencer_campaign_detail,
            'Content': self.service.get_content_program_detail, 'Retail': self.service.get_retail_media_campaign_detail,
            'Research': self.service.get_insights_project_detail}
        permitted = {'First': ('Taylor', 'Allyn'), 'Content': ('Emma', 'Kate'),
                     'Retail': ('Chloe',), 'Research': ('Emma', 'Kate')}
        for name, getter in getters.items():
            for user in ('Bailey', 'Jordon', *permitted[name]):
                with self.subTest(workflow=name, actor=user):
                    self.assertEqual(self.records[name].id, getter(self.users[user], self.records[name].id).id)
            with self.assertRaises(CampaignOpsPermissionError):
                getter(self.users['Maren'], self.records[name].id)
        self.records['First'].manager_user_id = self.users['Maren'].id
        with self.assertRaises(CampaignOpsPermissionError):
            self.service.get_influencer_campaign_detail(self.users['Maren'], self.records['First'].id)
        self.assertEqual([], self.timeline.list_campaigns(self.users['Maren'], 'planning')[0])

    def test_workflow_lists_do_not_return_unpermitted_children(self):
        self.assertEqual([self.records['First'].id], [r.id for r in self.service.list_influencer_campaigns(self.users['Allyn'])])
        self.assertEqual([], self.service.list_retail_media_campaigns(self.users['Allyn']))
        self.assertEqual([], self.service.list_content_programs(self.users['Allyn']))
        self.assertEqual([], self.service.list_insights_projects(self.users['Allyn']))
        self.assertEqual([self.records['Content'].id], [r.id for r in self.service.list_content_programs(self.users['Kate'])])
        self.assertEqual('Social Media Management', self.router.resolve(self.users['Maren'], self.programs['Social']).section)

    def test_mutations_and_parent_id_spoofing_for_each_workflow(self):
        cases = [('First', self.service.update_influencer_campaign, 'Allyn'),
                 ('Content', self.service.update_content_program, 'Kate'),
                 ('Retail', self.service.update_retail_media_campaign, 'Chloe'),
                 ('Research', self.service.update_insights_project, 'Kate')]
        for name, update, manager in cases:
            record = self.records[name]
            with self.subTest(name=name):
                with self.assertRaises(CampaignOpsPermissionError):
                    update(self.users['Maren'], record.id, latest_update='Forbidden')
                with self.assertRaises(CampaignOpsPermissionError):
                    update(self.users['Maren'], record.id, program_id=self.programs['Social'], latest_update='Spoofed')
                self.assertNotIn(record.latest_update, ('Forbidden', 'Spoofed'))
                update(self.users[manager], record.id, latest_update='Allowed operational edit')
                self.assertEqual('Allowed operational edit', record.latest_update)
                update(self.admin, record.id, latest_update='Admin edit')
                self.assertEqual('Admin edit', record.latest_update)

    def test_assignment_admin_restrictions_are_preserved(self):
        pid = self.programs['First']
        ws = self.repo.list_workstreams_by_program(pid)[0]
        for action in (
            lambda: self.service.reassign_primary_program_owner(self.users['Allyn'], pid, self.users['Maren'].id),
            lambda: self.service.reassign_workstream_lead(self.users['Allyn'], pid, ws.id, self.users['Maren'].id),
            lambda: self.service.update_workstream_details(self.users['Allyn'], pid, ws.id, owner_user_id=self.users['Maren'].id),
            lambda: self.timeline.change_owner(self.users['Allyn'], self.records['First'].id, self.users['Lauren'].id),
            lambda: self.service.archive_program(self.users['Allyn'], pid),
        ):
            with self.assertRaises(CampaignOpsPermissionError):
                action()

    def test_reassignment_immediately_revokes_and_grants_without_cache_reset(self):
        pid = self.programs['First']
        ws = self.repo.list_workstreams_by_program(pid)[0]
        self.repo.create_assignment(pid, self.users['Allyn'].id, 'contributor')
        self.service.reassign_workstream_lead(self.admin, pid, ws.id, self.users['Maren'].id)
        self.assertNotIn(pid, self.visible('Allyn'))
        self.assertIn(pid, self.visible('Maren'))
        with self.assertRaises(CampaignOpsPermissionError):
            self.timeline.workspace(self.users['Allyn'], self.records['First'].id)
        self.service.reassign_primary_program_owner(self.admin, pid, self.users['Ava'].id)
        self.assertNotIn(pid, self.visible('Taylor'))
        self.assertIn(pid, self.visible('Ava'))
        self.timeline.workspace(self.users['Ava'], self.records['First'].id)

    def test_archived_and_inactive_actor_rules(self):
        pid = self.programs['First']
        self.service.archive_program(self.admin, pid)
        for user in ('Bailey', 'Jordon', 'Taylor', 'Allyn'):
            self.assertNotIn(pid, self.visible(user))
            with self.assertRaises(CampaignOpsPermissionError):
                self.router.resolve(self.users[user], pid)
        self.assertEqual([], self.timeline.list_campaigns(self.users['Allyn'], 'planning')[0])
        # Explicit administrator archive tooling remains available.
        self.assertEqual(pid, self.service.get_program_workspace_summary(self.admin, pid).program.id)
        self.users['Jordon'].is_active = False
        with self.assertRaises(CampaignOpsPermissionError):
            self.router.list_registry(self.users['Jordon'])

    def test_forged_prefetch_and_batch_rows_do_not_bypass_child_authorization(self):
        forged = deepcopy(self.records['Second'])
        forged.program_id = self.programs['First']
        with self.assertRaises(CampaignOpsPermissionError):
            self.timeline.workspace(self.users['Allyn'], forged.id, routed_campaign=forged)
        with self.assertRaises(CampaignOpsPermissionError):
            self.service.get_influencer_live_manager_board_data(self.users['Allyn'], [forged])
        forged_content = SimpleNamespace(id=self.records['Content'].id, program_id=self.programs['First'])
        with self.assertRaises(CampaignOpsPermissionError):
            self.service.get_content_baseline_board_data(self.users['Allyn'], [forged_content])

    def test_unauthorized_save_and_stage_transition_make_no_writes(self):
        campaign = self.records['First']
        rows = deepcopy(self.repo.list_influencer_planning_steps(campaign.id))
        edited = [editor_record(r) for r in rows]
        edited[0]['Program Notes'] = 'Forbidden'
        events = len(self.repo.events)
        with self.assertRaises(CampaignOpsPermissionError):
            self.timeline.save_changes(self.users['Maren'], campaign.id, self.users['Taylor'].id,
                edited, rows, self.users['Taylor'].id, 'planning')
        with self.assertRaises(CampaignOpsPermissionError):
            self.timeline.advance(self.users['Maren'], campaign.id, 'planning')
        self.assertEqual(events, len(self.repo.events))
        self.assertEqual(rows, self.repo.list_influencer_planning_steps(campaign.id))
        self.timeline.advance(self.users['Allyn'], campaign.id, 'planning')
        self.assertEqual('live', campaign.influencer_stage)

    def test_session_id_manipulation_denied_and_cached_editor_revoked(self):
        app = AppTest.from_function(page_app).run()
        app.session_state.roster_repo = self.repo
        app.run()
        selectbox(app, 'Viewing as').select('Allyn').run()
        self.assertEqual(1, len([w for w in app.button if w.label == 'Open']))
        button(app, 'My Programs').click().run()
        self.assertFalse(any(w.label == 'Filters' for w in app.expander))
        self.assertEqual(1, len([w for w in app.button if w.label == 'Open']))
        app.session_state['campaign_ops_selected_program_id'] = self.programs['Second']
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any(ACCESS_DENIED in w.value for w in app.error))
        self.assertEqual('All Programs', app.session_state['campaign_ops_section'])
        button(app, 'Open').click().run()
        self.assertTrue(any(w.label == 'Save Changes' for w in app.button))
        ws = self.repo.list_workstreams_by_program(self.programs['First'])[0]
        self.service.reassign_workstream_lead(self.admin, self.programs['First'], ws.id, self.users['Maren'].id)
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(any(w.label == 'Save Changes' for w in app.button))
        self.assertTrue(any(w.value == ACCESS_DENIED for w in app.warning))
        self.assertNotIn('campaign_ops_selected_influencer_campaign_id', app.session_state.filtered_state)
