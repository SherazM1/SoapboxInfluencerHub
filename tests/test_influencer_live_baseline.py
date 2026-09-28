import unittest
from copy import deepcopy
from datetime import date
from core.campaign_ops.exceptions import CampaignOpsError
from tests.test_influencer_timeline import fixture

class InfluencerLiveBaselineTests(unittest.TestCase):
    def test_same_campaign_timeline_and_owner_across_stages(self):
        repo, service, actor, t, l, program = fixture()
        campaign = service.create_campaign(actor, program, 'Lifecycle', t.id)
        row = service.workspace(actor, campaign.id)[1][0]
        service.save_row(actor, campaign.id, 'Campaign Launch', '', date(2026, 7, 1), 'Manual notes', row.id)
        rows = deepcopy(repo.influencer_planning_steps)
        for stage, target in [('planning', 'live'), ('live', 'recapping'), ('recapping', 'complete')]:
            self.assertEqual([campaign.id], [c.id for c in service.list_campaigns(actor, stage)[0]])
            service.advance(t, campaign.id, stage)
            self.assertEqual([], service.list_campaigns(actor, stage)[0])
            self.assertEqual(target, campaign.influencer_stage)
            self.assertEqual(t.id, campaign.manager_user_id)
            self.assertEqual(rows, repo.influencer_planning_steps)
            self.assertEqual(1, len(repo.influencer_campaigns))
            with self.assertRaises(CampaignOpsError): service.advance(actor, campaign.id, stage)
        self.assertEqual(3, len([e for e in repo.events if e['event_type'] == 'influencer_timeline_stage_changed']))
