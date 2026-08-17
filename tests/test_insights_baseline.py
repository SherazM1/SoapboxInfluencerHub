from __future__ import annotations

import unittest
from datetime import date, datetime
from types import SimpleNamespace

from app.campaign_ops.insights.baseline import (
    current_status_text,
    deliverable_display_text,
    insights_quick_links,
    next_insights_deliverable,
    normalize_insights_deliverables,
)


def obj(**kwargs):
    return SimpleNamespace(**kwargs)


class InsightsBaselineTests(unittest.TestCase):
    def test_quick_links_use_workbook_labels_and_omit_missing_urls(self) -> None:
        project = obj(
            tracksheet_url="https://example.com/tracksheet",
            results_deck_url="",
            raw_data_url="https://example.com/raw-key",
        )

        links = insights_quick_links(project)

        self.assertEqual(
            [(link.label, link.url) for link in links],
            [
                ("Tracksheet", "https://example.com/tracksheet"),
                ("Raw Data Key", "https://example.com/raw-key"),
            ],
        )

    def test_quick_links_dedupe_by_label_and_url(self) -> None:
        project = obj(
            tracksheet_url="https://example.com/same",
            results_deck_url="https://example.com/same",
            raw_data_url="https://example.com/same",
        )

        links = insights_quick_links(project)

        self.assertEqual([link.label for link in links], ["Tracksheet", "Results Deck", "Raw Data Key"])

    def test_current_status_uses_latest_update_before_status_label(self) -> None:
        project = obj(latest_update="Working on draft survey - 7/17", insights_status="drafting_survey")
        self.assertEqual(current_status_text(project), "Working on draft survey - 7/17")

        project.latest_update = None
        self.assertEqual(current_status_text(project), "Drafting Survey")

    def test_next_deliverable_scopes_by_type_or_workstream_and_excludes_unrelated(self) -> None:
        project = obj(workstream_id="insights-ws")
        insights_type = obj(id="m1", title="Deliver draft to client", target_date=date(2026, 7, 21), start_date=None, end_date=None, status="not_started", completed_at=None, milestone_type="Insights", workstream_id=None, is_active=True)
        insights_workstream = obj(id="m2", title="Review concepts", target_date=date(2026, 7, 20), start_date=None, end_date=None, status="not_started", completed_at=None, milestone_type=None, workstream_id="insights-ws", is_active=True)
        unrelated = obj(id="m3", title="Content files due", target_date=date(2026, 7, 19), start_date=None, end_date=None, status="not_started", completed_at=None, milestone_type="Content Management", workstream_id="content-ws", is_active=True)

        rows = normalize_insights_deliverables([insights_type, insights_workstream, unrelated], project)

        self.assertEqual([row.title for row in rows], ["Review concepts", "Deliver draft to client"])

    def test_next_deliverable_filters_inactive_completed_and_uses_undated_fallback(self) -> None:
        project = obj(workstream_id="insights-ws")
        completed = obj(id="m1", title="Complete", target_date=date(2026, 7, 19), start_date=None, end_date=None, status="completed", completed_at=datetime(2026, 7, 19), milestone_type="Insights", workstream_id=None, is_active=True)
        inactive = obj(id="m2", title="Inactive", target_date=date(2026, 7, 20), start_date=None, end_date=None, status="not_started", completed_at=None, milestone_type="Insights", workstream_id=None, is_active=False)
        undated = obj(id="m3", title="Undated deliverable", target_date=None, start_date=None, end_date=None, status="not_started", completed_at=None, milestone_type="Insights", workstream_id=None, is_active=True)

        selected = next_insights_deliverable([completed, inactive, undated], project)

        self.assertIsNotNone(selected)
        self.assertEqual(selected.title, "Undated deliverable")
        self.assertEqual(deliverable_display_text(selected), "Undated deliverable")

    def test_no_next_deliverable_state_is_short(self) -> None:
        self.assertEqual(deliverable_display_text(None), "No open deliverable.")


if __name__ == "__main__":
    unittest.main()
