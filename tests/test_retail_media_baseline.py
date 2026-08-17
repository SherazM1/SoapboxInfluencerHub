from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import date, datetime

from app.campaign_ops.retail_media.baseline import (
    action_display_text,
    current_status_text,
    next_current_retail_media_action,
    normalize_retail_media_actions,
    over_budget,
    retail_media_quick_links,
    spend_budget_values,
)


@dataclass
class Obj:
    id: str


def obj(**kwargs):
    item = Obj(kwargs.pop("id", "id"))
    for key, value in kwargs.items():
        setattr(item, key, value)
    return item


class RetailMediaBaselineTests(unittest.TestCase):
    def test_quick_links_are_ordered_deduped_and_omit_missing_urls(self) -> None:
        campaign = obj(
            id="rm-1",
            tracksheet_url="https://example.com/track",
            budget_tracker_url="",
            optimization_log_url="https://example.com/opt",
        )
        resources = [
            obj(id="r1", resource_type="WPSR Weekly Update", title="Update WPSR Weekly", url="https://example.com/wpsr", is_active=True),
            obj(id="r2", resource_type="Budget Tracker", title="Budget Tracker", url=None, is_active=True),
            obj(id="r3", resource_type="Media Plan / Budget", title="Media Plan / Budget", url="https://example.com/media", is_active=True),
            obj(id="r4", resource_type="Custom", title="Summer Tracksheet", url="https://example.com/summer", is_active=True),
            obj(id="r5", resource_type="Tracksheet", title="Tracksheet", url="https://example.com/track", is_active=True),
            obj(id="r6", resource_type="RM Strategy", title="RM Strategy", url="https://example.com/strategy", is_active=False),
        ]

        links = retail_media_quick_links(campaign, resources, include_custom=True)

        self.assertEqual(
            [(link.label, link.url) for link in links],
            [
                ("Tracksheet", "https://example.com/track"),
                ("Update WPSR Weekly", "https://example.com/wpsr"),
                ("Media Plan / Budget", "https://example.com/media"),
                ("Optimization Log", "https://example.com/opt"),
                ("Summer Tracksheet", "https://example.com/summer"),
            ],
        )

    def test_normalizes_actions_and_excludes_unrelated_program_milestones(self) -> None:
        channel = obj(id="ch-1", channel_type="Onsite Display")
        activation = obj(id="a1", activation_name="Launch", channel_id="ch-1", start_date=date(2026, 8, 10), end_date=None, status="in_progress", waiting_on=None, latest_update="Build complete", completed_at=None, hard_deadline=True, is_active=True)
        creative = obj(id="c1", creative_name="Creative due for review", creative_type=None, channel_id="ch-1", due_date=date(2026, 8, 8), submitted_date=None, approved_date=None, approval_status="client_review", submission_status="not_submitted", platform_status=None, notes="With client", is_active=True)
        optimization = obj(id="o1", update_text="Adjusted search bids", update_date=date(2026, 8, 12), optimization_type="Search", channel_id="ch-1", is_active=True)
        retail_milestone = obj(id="m1", title="Campaign wraps", target_date=date(2026, 9, 10), start_date=None, end_date=None, status="not_started", completed_at=None, hard_deadline=False, milestone_type="Retail Media", is_active=True)
        unrelated = obj(id="m2", title="Content files due", target_date=date(2026, 8, 5), start_date=None, end_date=None, status="not_started", completed_at=None, hard_deadline=False, milestone_type="Content Management", is_active=True)

        rows = normalize_retail_media_actions(
            activations=[activation],
            creative=[creative],
            optimizations=[optimization],
            milestones=[retail_milestone, unrelated],
            channels=[channel],
        )

        self.assertEqual([row.source for row in rows], ["Creative", "Activation", "Optimization", "Milestone"])
        self.assertEqual(rows[0].status, "In Review")
        self.assertEqual(rows[1].channel_label, "Onsite Display")
        self.assertEqual(rows[2].status, "Update")
        self.assertTrue(rows[2].complete)
        self.assertNotIn("Content files due", [row.action for row in rows])
        self.assertEqual("8/10 | Launch | Onsite Display", action_display_text(rows[1]))

    def test_next_current_action_prioritizes_waiting_over_overdue_and_upcoming(self) -> None:
        waiting = obj(id="a1", activation_name="Client feedback", channel_id=None, start_date=date(2026, 8, 20), end_date=None, status="in_progress", waiting_on="Client", latest_update=None, completed_at=None, hard_deadline=False, is_active=True)
        overdue = obj(id="a2", activation_name="Build campaigns", channel_id=None, start_date=date(2026, 8, 10), end_date=None, status="in_progress", waiting_on=None, latest_update=None, completed_at=None, hard_deadline=False, is_active=True)
        upcoming = obj(id="a3", activation_name="Campaign wraps", channel_id=None, start_date=date(2026, 8, 30), end_date=None, status="not_started", waiting_on=None, latest_update=None, completed_at=None, hard_deadline=False, is_active=True)
        rows = normalize_retail_media_actions(activations=[upcoming, overdue, waiting], creative=[], optimizations=[], milestones=[])

        selected = next_current_retail_media_action(rows, today=date(2026, 8, 17))

        self.assertIsNotNone(selected)
        self.assertEqual(selected.action, "Client feedback")
        self.assertEqual(selected.status, "Waiting")

    def test_next_current_action_uses_overdue_upcoming_then_undated(self) -> None:
        overdue = obj(id="a1", activation_name="Build campaigns", channel_id=None, start_date=date(2026, 8, 10), end_date=None, status="in_progress", waiting_on=None, latest_update=None, completed_at=None, hard_deadline=False, is_active=True)
        upcoming = obj(id="a2", activation_name="Campaign wraps", channel_id=None, start_date=date(2026, 8, 30), end_date=None, status="not_started", waiting_on=None, latest_update=None, completed_at=None, hard_deadline=False, is_active=True)
        rows = normalize_retail_media_actions(activations=[upcoming, overdue], creative=[], optimizations=[], milestones=[])
        self.assertEqual(next_current_retail_media_action(rows, today=date(2026, 8, 17)).action, "Build campaigns")

        completed = obj(id="a3", activation_name="Old launch", channel_id=None, start_date=date(2026, 8, 10), end_date=None, status="complete", waiting_on=None, latest_update=None, completed_at=datetime(2026, 8, 11), hard_deadline=False, is_active=True)
        undated = obj(id="a4", activation_name="Awaiting assets", channel_id=None, start_date=None, end_date=None, status="in_progress", waiting_on=None, latest_update=None, completed_at=None, hard_deadline=False, is_active=True)
        rows = normalize_retail_media_actions(activations=[completed, undated], creative=[], optimizations=[], milestones=[])
        self.assertEqual(next_current_retail_media_action(rows, today=date(2026, 8, 17)).action, "Awaiting assets")

    def test_budget_spend_fallback_and_current_status_paused(self) -> None:
        campaign = obj(
            id="rm-1",
            overall_budget=None,
            total_spend=None,
            channel_budget_total=1000,
            channel_spend_total=1200,
            retail_media_status="live",
            is_paused=True,
            pause_reason="Creative with client",
            waiting_on="Client creative approval",
        )

        self.assertEqual(spend_budget_values(campaign), (1000, 1200))
        self.assertTrue(over_budget(campaign))
        self.assertEqual(current_status_text(campaign), "PAUSED | Creative with client")


if __name__ == "__main__":
    unittest.main()
