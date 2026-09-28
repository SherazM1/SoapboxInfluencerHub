import inspect
import unittest
from datetime import date
from app.campaign_ops.influencer.planning_baseline import compact_date
from core.campaign_ops.repository import CampaignOpsRepository

class InfluencerPlanningRuntimeTests(unittest.TestCase):
    def test_existing_repository_sequence_semantics_are_unchanged(self):
        self.assertIn("order by influencer_campaign_id, sequence_order asc, due_date asc nulls last, created_at asc", inspect.getsource(CampaignOpsRepository.list_influencer_campaigns))

    def test_shared_compact_date_is_preserved(self):
        self.assertEqual("", compact_date(None))
        self.assertEqual("5/10", compact_date(date(2026, 5, 10)))
        self.assertEqual("5/10/2027", compact_date(date(2027, 5, 10), reference_year=2026))
