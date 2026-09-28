from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.campaign_ops.influencer.recap_baseline import ready_to_close_blockers, select_recap_campaign_for_open


class FakeColumn:
    def __init__(self, clicked: bool = False) -> None:
        self.clicked = clicked

    def button(self, label: str, **kwargs) -> bool:
        return self.clicked and label == "Open Recap Campaign"


class InfluencerRecapBaselineTests(unittest.TestCase):


    def test_ready_to_close_blockers_cover_workspace_parity_inputs(self) -> None:
        campaign = SimpleNamespace(
            open_exception_count=1,
            open_checkpoint_count=2,
            open_requirement_count=3,
            paid_live_incomplete_count=4,
            missing_final_links_count=5,
            missing_final_impressions_count=6,
        )

        blockers = ready_to_close_blockers(campaign)

        self.assertEqual(["1 unresolved exception(s)", "2 open checkpoint(s)", "3 open requirement(s)"], blockers)


    def test_select_recap_campaign_for_open_helper(self) -> None:
        state: dict[str, object] = {}
        select_recap_campaign_for_open(state, "campaign-1")
        self.assertEqual("campaign-1", state["campaign_ops_selected_influencer_recap_campaign_id"])


if __name__ == "__main__":
    unittest.main()
