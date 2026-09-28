import unittest
from copy import deepcopy
from tests.test_influencer_timeline import fixture

class InfluencerRecapBaselineTests(unittest.TestCase):
    def test_retired_readiness_does_not_block_and_old_records_are_unchanged(self):
        repo, service, actor, t, l, program = fixture()
        campaign = service.create_campaign(actor, program, 'Legacy records', t.id)
        service.advance(actor, campaign.id, 'planning')
        creator = service.create_influencer_live_creator(actor, campaign.id, 'Historical creator', impressions_reporting_required=True)
        checkpoint = service.create_influencer_live_checkpoint(actor, campaign.id, 'Open checkpoint')
        wave = service.create_influencer_creator_wave(actor, campaign.id, 1, wave_name='Existing wave')
        exception = service.create_influencer_live_exception(actor, campaign.id, 'Open exception')
        before = deepcopy((creator, checkpoint, wave, exception))
        service.advance(t, campaign.id, 'live')
        recap = service.create_or_update_influencer_recap_record(actor, campaign.id, latest_update='Historical recap')
        requirement = service.create_influencer_recap_requirement(actor, campaign.id, 'Client Recap', 'Unfinished requirement', required=True)
        old_recap = deepcopy((recap, requirement))
        service.advance(t, campaign.id, 'recapping')
        self.assertEqual('complete', campaign.influencer_stage)
        self.assertTrue(campaign.is_active)
        self.assertEqual(before, (creator, checkpoint, wave, exception))
        self.assertEqual(old_recap, (recap, requirement))
        self.assertEqual(9, len(service.workspace(actor, campaign.id)[1]))
