from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.campaign_ops.influencer import live_views
from app.campaign_ops.influencer.live_baseline import (
    compose_live_operational_sequence,
    live_quick_links,
    next_go_live_text,
    select_live_campaign_for_open,
    smart_live_sequence_preview,
)


class FakeColumn:
    def __init__(self, clicked: bool = False) -> None:
        self.clicked = clicked

    def checkbox(self, label: str, **kwargs) -> bool:
        return False

    def button(self, label: str, **kwargs) -> bool:
        return self.clicked and label == "Open Live Campaign"

    def selectbox(self, label: str, options, **kwargs):
        return list(options)[0]

    def text_input(self, label: str, value: str = "", **kwargs) -> str:
        return value

    def date_input(self, label: str, value=None, **kwargs):
        return value


class DummyExpander:
    def __enter__(self) -> "DummyExpander":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class InfluencerLiveBaselineTests(unittest.TestCase):
    def test_live_quick_links_include_supported_and_custom_resources(self) -> None:
        campaign = SimpleNamespace(
            track_sheet_url="https://example.com/track",
            influencer_brief_url="https://example.com/brief",
            click2cart_link_url="https://example.com/c2c",
            client_facing_live_doc_url="https://example.com/live",
            daily_impressions_url="https://example.com/daily",
            invoice_url="https://example.com/invoice",
            eop_survey_url="https://example.com/eop",
        )
        resources = [
            SimpleNamespace(resource_type="Walmart Link", title="Walmart", url="https://example.com/walmart", is_active=True),
            SimpleNamespace(resource_type="Retailer Link", title="Retailer", url="https://example.com/retailer", is_active=True),
            SimpleNamespace(resource_type="Influencer Education", title="Education", url="https://example.com/edu", is_active=True),
            SimpleNamespace(resource_type="Client Guidelines", title="Guidelines", url="https://example.com/guidelines", is_active=True),
            SimpleNamespace(resource_type="Custom", title="AZ & O'Reilly Click2Cart", url="https://example.com/custom", is_active=True),
            SimpleNamespace(resource_type="Custom", title="Missing", url=None, is_active=True),
        ]

        labels = [link.label for link in live_quick_links(campaign, resources)]

        self.assertIn("Track Sheet", labels)
        self.assertIn("Influencer Brief", labels)
        self.assertIn("Click2Cart Link", labels)
        self.assertIn("Walmart Link", labels)
        self.assertIn("Retailer Link", labels)
        self.assertIn("Client-Facing Live Doc", labels)
        self.assertIn("Daily Impressions", labels)
        self.assertIn("Invoice", labels)
        self.assertIn("EOP Survey", labels)
        self.assertIn("Influencer Education", labels)
        self.assertIn("Client Guidelines", labels)
        self.assertIn("AZ & O'Reilly Click2Cart", labels)
        self.assertNotIn("Missing", labels)

    def test_unified_sequence_sources_order_undated_and_duplicates(self) -> None:
        planning = [
            SimpleNamespace(id="p1", step_title="Application out", sequence_order=1, due_date=date(2026, 5, 1), start_date=None, completed_date=date(2026, 5, 1), status="complete", waiting_on=None, is_active=True),
            SimpleNamespace(id="p2", step_title="Undated planning note", sequence_order=2, due_date=None, start_date=None, completed_date=None, status="not_started", waiting_on=None, is_active=True),
        ]
        checkpoints = [
            SimpleNamespace(id="c1", checkpoint_title="Application out", sequence_order=1, due_date=date(2026, 5, 1), start_date=None, completed_date=None, status="not_started", waiting_on=None, is_active=True),
            SimpleNamespace(id="c2", checkpoint_title="Campaign wrap review", sequence_order=2, due_date=date(2026, 8, 31), start_date=None, completed_date=None, status="waiting", waiting_on="Client", is_active=True),
        ]
        waves = [
            SimpleNamespace(id="w1", wave_number=1, wave_name="First creator wave starts", planned_start_date=date(2026, 7, 24), actual_start_date=None, actual_end_date=None, status="not_started", waiting_on=None, is_active=True),
            SimpleNamespace(id="w2", wave_number=2, wave_name="Final creator wave starts", planned_start_date=None, actual_start_date=None, actual_end_date=None, status="not_started", waiting_on=None, is_active=True),
        ]

        rows = compose_live_operational_sequence(planning, checkpoints, waves)

        self.assertEqual(["Planning", "Wave", "Checkpoint", "Planning", "Wave"], [row.source for row in rows])
        self.assertEqual(1, len([row for row in rows if row.action == "Application out"]))
        self.assertIn("Undated planning note", [row.action for row in rows])
        self.assertIn("Final creator wave starts", [row.action for row in rows])

    def test_smart_preview_avoids_duplicates_and_full_sequence_is_deterministic(self) -> None:
        rows = compose_live_operational_sequence(
            [SimpleNamespace(id=f"p{i}", step_title=f"Planning {i}", sequence_order=i, due_date=date(2026, 5, i), start_date=None, completed_date=date(2026, 5, i) if i == 1 else None, status="complete" if i == 1 else "not_started", waiting_on=None, is_active=True) for i in range(1, 7)],
            [SimpleNamespace(id="c1", checkpoint_title="Waiting checkpoint", sequence_order=1, due_date=date(2026, 5, 9), start_date=None, completed_date=None, status="waiting", waiting_on="Client", is_active=True)],
            [SimpleNamespace(id="w1", wave_number=1, wave_name="Campaign wrap", planned_start_date=date(2026, 8, 31), actual_start_date=None, actual_end_date=None, status="not_started", waiting_on=None, is_active=True)],
        )

        preview = smart_live_sequence_preview(rows, today=date(2026, 5, 8), upcoming_limit=3)

        self.assertEqual(len({(row.source, row.source_id) for row in preview}), len(preview))
        self.assertLessEqual(len(preview), len(rows))
        self.assertEqual(rows, compose_live_operational_sequence(
            [SimpleNamespace(id=f"p{i}", step_title=f"Planning {i}", sequence_order=i, due_date=date(2026, 5, i), start_date=None, completed_date=date(2026, 5, i) if i == 1 else None, status="complete" if i == 1 else "not_started", waiting_on=None, is_active=True) for i in range(1, 7)],
            [SimpleNamespace(id="c1", checkpoint_title="Waiting checkpoint", sequence_order=1, due_date=date(2026, 5, 9), start_date=None, completed_date=None, status="waiting", waiting_on="Client", is_active=True)],
            [SimpleNamespace(id="w1", wave_number=1, wave_name="Campaign wrap", planned_start_date=date(2026, 8, 31), actual_start_date=None, actual_end_date=None, status="not_started", waiting_on=None, is_active=True)],
        ))

    def test_next_go_live_text_preserves_creator_derived_empty_state(self) -> None:
        self.assertEqual("8/10", next_go_live_text(date(2026, 8, 10), all_live=False))
        self.assertEqual("All scheduled creators are live", next_go_live_text(None, all_live=True))
        self.assertEqual("", next_go_live_text(None, all_live=False))

    def test_render_live_block_hold_no_sequence_and_open_action(self) -> None:
        campaign = SimpleNamespace(
            id="campaign-1",
            campaign_title="AGC at Walmart - BTS",
            manager_display_name="T",
            live_status="waiting_on_client",
            is_on_hold=True,
            hold_reason="Waiting on client feedback",
            highlighted_exception_count=0,
            latest_update=None,
            waiting_on=None,
            live_creator_count=0,
            planned_creator_count=0,
            active_wave_count=0,
            next_go_live_date=None,
            open_exception_count=0,
            paid_live_end_date=None,
            launch_date=None,
            wrap_date=None,
            invoice_date=None,
            invoice_status=None,
            track_sheet_url=None,
            influencer_brief_url=None,
            click2cart_link_url=None,
            client_facing_live_doc_url=None,
            daily_impressions_url=None,
            invoice_url=None,
            eop_survey_url=None,
        )
        rendered: list[str] = []
        state: dict[str, object] = {}
        with (
            patch.object(live_views.st, "session_state", state),
            patch.object(live_views.st, "markdown", side_effect=lambda body, **kwargs: rendered.append(body)),
            patch.object(live_views.st, "columns", return_value=[FakeColumn(), FakeColumn(clicked=True), FakeColumn()]),
            patch.object(live_views.st, "rerun"),
        ):
            live_views.render_live_block(campaign, [], [], [], [])

        html = "".join(rendered)
        self.assertIn("ON HOLD", html)
        self.assertIn("Hold reason: Waiting on client feedback", html)
        self.assertIn("No operational sequence items yet.", html)
        self.assertEqual("campaign-1", state["campaign_ops_selected_influencer_live_campaign_id"])

    def test_render_live_portfolio_empty_state(self) -> None:
        service = Mock()
        service.list_influencer_live_campaigns.return_value = []
        messages: list[str] = []
        with (
            patch.object(live_views.st, "columns", return_value=[FakeColumn(), FakeColumn(), FakeColumn(), FakeColumn(), FakeColumn()]),
            patch.object(live_views.st, "caption"),
            patch.object(live_views.st, "expander", return_value=DummyExpander()),
            patch.object(live_views.st, "info", side_effect=lambda message: messages.append(message)),
        ):
            live_views.render_live_portfolio(SimpleNamespace(id="u1"), service, None)

        self.assertEqual(["No live influencer campaigns match these filters."], messages)

    def test_select_live_campaign_for_open_helper(self) -> None:
        state: dict[str, object] = {}
        select_live_campaign_for_open(state, "campaign-1")
        self.assertEqual("campaign-1", state["campaign_ops_selected_influencer_live_campaign_id"])


if __name__ == "__main__":
    unittest.main()
