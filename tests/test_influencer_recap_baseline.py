from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from app.campaign_ops.influencer import recap_views
from app.campaign_ops.influencer.recap_baseline import (
    all_influencers_live_state,
    closeout_status_items,
    group_recap_launch_items,
    ready_to_close_blockers,
    recap_quick_links,
    select_recap_campaign_for_open,
)


class FakeColumn:
    def __init__(self, clicked: bool = False) -> None:
        self.clicked = clicked

    def button(self, label: str, **kwargs) -> bool:
        return self.clicked and label == "Open Recap Campaign"


class InfluencerRecapBaselineTests(unittest.TestCase):
    def test_recap_quick_links_order_alias_custom_dedupe_and_launch_links(self) -> None:
        campaign = SimpleNamespace(
            track_sheet_url="https://example.com/track",
            influencer_brief_url="https://example.com/brief",
            click2cart_link_url="https://example.com/click",
            bitly_link_url="https://example.com/bitly",
            invoice_url="https://example.com/invoice",
            eop_survey_url="https://example.com/eop",
            live_content_tracker_url="https://example.com/live-content",
            recap_deck_url="https://example.com/deck",
            final_performance_data_url="https://example.com/performance",
            sales_lift_analysis_url="https://example.com/sales-lift",
        )
        resources = [
            SimpleNamespace(resource_type="Results Deck", title="Results", url="https://example.com/results", is_active=True),
            SimpleNamespace(resource_type="Client Recap Deck", title="Client Deck", url="https://example.com/client-deck", is_active=True),
            SimpleNamespace(resource_type="Client-Facing Influencer Review", title="Client Review", url="https://example.com/review", is_active=True),
            SimpleNamespace(resource_type="Custom", title="Custom Tracker", url="https://example.com/custom", is_active=True),
            SimpleNamespace(resource_type="Track Sheet", title="Duplicate Track", url="https://example.com/track", is_active=True),
            SimpleNamespace(resource_type="Custom", title="Needs URL", url=None, is_active=True),
        ]
        launches = [
            SimpleNamespace(product_name="Product A", retailer_name="7-Eleven", product_url="https://example.com/product", retailer_url="https://example.com/retailer", is_active=True),
        ]

        links = recap_quick_links(campaign, resources, launches)
        labels = [link.label for link in links]

        self.assertEqual("Track Sheet", labels[0])
        self.assertIn("Client-Facing Influencer Review", labels)
        self.assertIn("Results Deck", labels)
        self.assertIn("Client Recap Deck", labels)
        self.assertIn("Product A", labels)
        self.assertIn("7-Eleven", labels)
        self.assertIn("Custom Tracker", labels)
        self.assertNotIn("Needs URL", labels)
        self.assertEqual(len({(link.label, link.url) for link in links}), len(links))

    def test_group_launch_items_preserves_order_moms_dads_and_ungrouped(self) -> None:
        items = [
            SimpleNamespace(group_name="MOMS", product_name="Mom Product", is_active=True),
            SimpleNamespace(group_name="DADS", product_name="Dad Product", is_active=True),
            SimpleNamespace(group_name=None, product_name="Ungrouped", is_active=True),
            SimpleNamespace(group_name="MOMS", product_name="Inactive", is_active=False),
        ]

        groups = group_recap_launch_items(items)

        self.assertEqual(["MOMS", "DADS", None], [group.group_name for group in groups])
        self.assertEqual(["Mom Product"], [item.product_name for item in groups[0].items])
        self.assertEqual(["Ungrouped"], [item.product_name for item in groups[2].items])

    def test_closeout_status_uses_existing_aggregate_fields(self) -> None:
        campaign = SimpleNamespace(
            open_requirement_count=2,
            creator_closeout_status="in_progress",
            invoice_status="sent",
            invoice_date=date(2026, 9, 12),
            financial_close_status="open",
            eop_survey_status="complete",
            recap_deck_status="in_progress",
            sales_lift_analysis_required=True,
            sales_lift_analysis_status="waiting",
            total_creator_count=6,
            live_creator_count=4,
        )

        rows = {label: value for label, value, _group in closeout_status_items(campaign)}

        self.assertEqual("2 Open", rows["Open Requirements"])
        self.assertEqual("in_progress", rows["Creator Closeout"])
        self.assertEqual("sent 9/12", rows["Invoice"])
        self.assertEqual("Waiting", rows["Sales Lift"])
        self.assertEqual(("In Progress", "4 / 6 live"), all_influencers_live_state(campaign))

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

    def test_render_recap_block_hold_links_launches_updates_ready_and_open_action(self) -> None:
        campaign = SimpleNamespace(
            id="campaign-1",
            campaign_title="TEST Recap",
            manager_display_name="T",
            recap_status="ready_to_close",
            is_on_hold=True,
            hold_reason="Client pause",
            track_sheet_url="https://example.com/track",
            influencer_brief_url=None,
            click2cart_link_url=None,
            bitly_link_url=None,
            invoice_url=None,
            eop_survey_url=None,
            live_content_tracker_url=None,
            recap_deck_url=None,
            final_performance_data_url=None,
            sales_lift_analysis_url=None,
            open_requirement_count=0,
            creator_closeout_status="complete",
            invoice_status="sent",
            invoice_date=None,
            financial_close_status="complete",
            eop_survey_status="complete",
            recap_deck_status="complete",
            sales_lift_analysis_required=False,
            sales_lift_analysis_status=None,
            total_creator_count=1,
            live_creator_count=1,
            completed_creator_count=1,
            latest_update="Deck sent",
            waiting_on="Client recap",
            ready_to_close_state="Ready to Close",
            open_exception_count=0,
            open_checkpoint_count=0,
            paid_live_incomplete_count=0,
            missing_final_links_count=0,
            missing_final_impressions_count=0,
        )
        launches = [
            SimpleNamespace(group_name="MOMS", product_name="Product A", retailer_name="7-Eleven", online_launch_date=date(2026, 5, 4), in_store_launch_date=date(2026, 5, 9), launch_status="online_live", product_url="https://example.com/product", retailer_url=None, is_active=True),
        ]
        rendered: list[str] = []
        state: dict[str, object] = {}
        with (
            patch.object(recap_views.st, "session_state", state),
            patch.object(recap_views.st, "markdown", side_effect=lambda body, **kwargs: rendered.append(body)),
            patch.object(recap_views.st, "columns", return_value=[FakeColumn(clicked=True), FakeColumn()]),
            patch.object(recap_views.st, "rerun"),
        ):
            recap_views.render_recap_block(campaign, [], launches)

        html = "".join(rendered)
        self.assertIn("ON HOLD", html)
        self.assertIn("Hold reason: Client pause", html)
        self.assertIn("LINKED SHEETS", html)
        self.assertIn("CLOSEOUT STATUS", html.upper())
        self.assertIn("PRODUCT / RETAILER LAUNCHES", html.upper())
        self.assertIn("MOMS", html)
        self.assertIn("Latest Update", html)
        self.assertIn("Waiting On", html)
        self.assertIn("READY TO CLOSE", html.upper())
        self.assertEqual("campaign-1", state["campaign_ops_selected_influencer_recap_campaign_id"])

    def test_select_recap_campaign_for_open_helper(self) -> None:
        state: dict[str, object] = {}
        select_recap_campaign_for_open(state, "campaign-1")
        self.assertEqual("campaign-1", state["campaign_ops_selected_influencer_recap_campaign_id"])


if __name__ == "__main__":
    unittest.main()
