from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

from app.campaign_ops.content_management.baseline import (
    action_display_text,
    content_quick_links,
    current_status_text,
    group_fact_text,
    group_facts,
    grouped_content_actions,
    invoice_summary_rows,
    next_current_action,
    normalize_content_actions,
)
from app.campaign_ops.content_management.views import filter_programs


class ContentManagementBaselineTests(unittest.TestCase):
    def test_group_facts_preserve_sort_order_and_counts(self) -> None:
        groups = [
            SimpleNamespace(id="g2", group_name="3PG", expected_sku_count=228, graphics_per_sku=5, sort_order=2, is_active=True),
            SimpleNamespace(id="g1", group_name="FS", expected_sku_count=70, graphics_per_sku=None, sort_order=1, is_active=True),
            SimpleNamespace(id="g3", group_name="Inactive", expected_sku_count=1, graphics_per_sku=None, sort_order=0, is_active=False),
        ]

        facts = group_facts(groups)

        self.assertEqual([fact.name for fact in facts], ["FS", "3PG"])
        self.assertEqual(group_fact_text(facts), "FS 70 | 3PG 228")

    def test_content_quick_links_dedupe_and_include_audits_custom(self) -> None:
        program = SimpleNamespace(
            sku_list_url="https://example.com/skus",
            tracksheet_url="https://example.com/tracker",
            keyword_insights_url="https://example.com/keywords",
            creative_request_deck_url=None,
            pdp_request_deck_url=None,
            photography_url=None,
        )
        resources = [
            SimpleNamespace(resource_type="SKU List", title="SKU List", url="https://example.com/skus", is_active=True),
            SimpleNamespace(resource_type="Custom", title="Audits", url="https://example.com/audits", is_active=True),
            SimpleNamespace(resource_type="Custom", title="Other", url="https://example.com/other", is_active=True),
            SimpleNamespace(resource_type="Keyword Insights", title="Keyword Insights", url=None, is_active=True),
        ]

        scan_links = content_quick_links(program, resources)
        detail_links = content_quick_links(program, resources, include_custom=True)

        self.assertEqual([link.label for link in scan_links], ["SKU List", "Tracksheet", "Keyword Insights", "Audits"])
        self.assertEqual(len([link for link in scan_links if link.label == "SKU List"]), 1)
        self.assertIn("Other", [link.label for link in detail_links])

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
        grouped = grouped_content_actions(rows, group_facts(groups))
        next_row = next_current_action(rows)

        self.assertEqual(grouped[0][0], "FS")
        self.assertEqual(grouped[-1][0], "General")
        self.assertIn("Undated graphics", [row.action for row in rows])
        self.assertEqual(next_row.action, "Walmart | PDP")
        self.assertEqual(next_row.status, "Submitted")
        self.assertEqual(action_display_text(next_row), "8/5 | Walmart | PDP")
        delivered = next(row for row in rows if row.source_id == "d1")
        self.assertEqual(delivered.status, "Delivered")
        self.assertIn("Delivered", delivered.note or "")
        self.assertEqual(next_current_action([delivered], "Fallback milestone", date(2026, 8, 9)).action, "Fallback milestone")

    def test_current_status_and_invoice_summary_are_display_only(self) -> None:
        program = SimpleNamespace(content_status="monitoring", latest_update="Ready to submit")
        monitoring = [
            SimpleNamespace(update_text="Monitoring all SKUs", is_active=True),
        ]
        checkpoints = [
            SimpleNamespace(checkpoint_name="Q2 Invoice", invoice_date=None, due_date=date(2026, 8, 1), status=None, notes="", is_active=True),
            SimpleNamespace(checkpoint_name="Q1 Invoice", invoice_date=date(2026, 6, 15), due_date=None, status="sent", notes="sent", is_active=True),
            SimpleNamespace(checkpoint_name="Inactive", invoice_date=date(2026, 5, 1), due_date=None, status="sent", notes="", is_active=False),
        ]

        self.assertEqual(current_status_text(program, monitoring), "Monitoring | Monitoring all SKUs")
        self.assertEqual(
            invoice_summary_rows(checkpoints),
            [
                {"Date": "6/15", "Checkpoint": "Q1 Invoice", "Status": "Sent", "Notes": "sent"},
                {"Date": "8/1", "Checkpoint": "Q2 Invoice", "Status": "Pending", "Notes": "-"},
            ],
        )

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
