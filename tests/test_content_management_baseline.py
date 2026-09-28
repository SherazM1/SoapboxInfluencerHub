from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from app.campaign_ops.content_management.baseline import action_display_text, next_current_action, normalize_content_actions
from app.campaign_ops.content_management.views import filter_programs


class ContentManagementBaselineTests(unittest.TestCase):


    def test_action_normalization_grouping_status_and_ordering(self) -> None:
        groups = [SimpleNamespace(id="g1", group_name="FS", expected_sku_count=70, sort_order=1, is_active=True)]
        deliverables = [
            SimpleNamespace(id="d1", sku_group_id="g1", deliverable_name="PDP copy", due_date=date(2026, 8, 3), delivered_date=date(2026, 8, 4), approved_date=None, status="delivered", approval_status=None, waiting_on=None, notes=None, is_active=True),
            SimpleNamespace(id="d2", sku_group_id=None, deliverable_name="Undated graphics", due_date=None, delivered_date=None, approved_date=None, status="in_progress", approval_status=None, waiting_on=None, notes=None, is_active=True),
        ]
        submissions = [
            SimpleNamespace(id="s1", sku_group_id="g1", retailer_or_platform="Walmart", submission_type="PDP", expected_live_date=date(2026, 8, 5), submitted_date=date(2026, 8, 2), approved_date=None, published_date=None, live_url=None, status="submitted", issue_text=None, waiting_on="Client", is_active=True)
        ]
        monitoring = [
            SimpleNamespace(id="m1", sku_group_id="g1", update_date=date(2026, 8, 6), update_text="Live checks complete", update_type="Audit", publication_state="monitoring", is_active=True)
        ]
        milestones = [
            SimpleNamespace(id="ms1", title="Submit PDP sweep", target_date=date(2026, 8, 1), start_date=None, end_date=None, status="in_progress", completed_at=None, is_active=True)
        ]

        rows = normalize_content_actions(groups=groups, deliverables=deliverables, submissions=submissions, monitoring_updates=monitoring, milestones=milestones)
        next_row = next_current_action(rows)

        self.assertIn("Undated graphics", [row.action for row in rows])
        self.assertEqual(next_row.action, "Walmart | PDP")
        self.assertEqual(next_row.status, "Submitted")
        self.assertEqual(action_display_text(next_row), "8/5 | Walmart | PDP")
        delivered = next(row for row in rows if row.source_id == "d1")
        self.assertEqual(delivered.status, "Delivered")
        self.assertIn("Delivered", delivered.note or "")
        self.assertEqual(next_current_action([delivered], "Fallback milestone", date(2026, 8, 9)).action, "Fallback milestone")


    def test_existing_portfolio_filters_are_preserved(self) -> None:
        rows = [
            SimpleNamespace(content_program_title="Incomm Walmart", program_name="Shared A", client_name="Incomm", latest_update="Ready", owner_user_id="u1", content_status="client_review", group_names=["FS", "3PG"], issue_count=0, maintenance_end_date=None, is_active=True),
            SimpleNamespace(content_program_title="Odwalla", program_name="Shared B", client_name="Odwalla", latest_update="", owner_user_id="u2", content_status="monitoring", group_names=["Jumex"], issue_count=2, maintenance_end_date=date(2026, 9, 1), is_active=False),
        ]

        self.assertEqual([row.content_program_title for row in filter_programs(rows, {"owner_user_id": "u1"})], ["Incomm Walmart"])
        self.assertEqual([row.content_program_title for row in filter_programs(rows, {"client_name": "Odwalla"})], ["Odwalla"])
        self.assertEqual([row.content_program_title for row in filter_programs(rows, {"content_status": "monitoring"})], ["Odwalla"])
        self.assertEqual([row.content_program_title for row in filter_programs(rows, {"sku_group": "3pg"})], ["Incomm Walmart"])
        self.assertEqual([row.content_program_title for row in filter_programs(rows, {"issue_state": "Has issues"})], ["Odwalla"])
        self.assertEqual([row.content_program_title for row in filter_programs(rows, {"maintenance_state": "No maintenance end"})], ["Incomm Walmart"])


if __name__ == "__main__":
    unittest.main()
