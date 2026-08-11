from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.campaign_ops.influencer import views
from app.campaign_ops.influencer.planning_baseline import (
    campaign_quick_links,
    compact_date,
    next_sequence_step,
    planning_sequence_preview,
    select_campaign_for_open,
)
from core.campaign_ops.enums import UserRole
from core.campaign_ops.models import CampaignOpsUser
from core.campaign_ops.repository import CampaignOpsRepository


INFLUENCER_VIEW_FILES = [
    Path("app/campaign_ops/influencer/views.py"),
    Path("app/campaign_ops/influencer/live_views.py"),
    Path("app/campaign_ops/influencer/recap_views.py"),
]


class DummyTab:
    def __enter__(self) -> "DummyTab":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeColumn:
    def __init__(self) -> None:
        self.links: list[tuple[str, str]] = []
        self.metrics: list[tuple[str, str]] = []

    def link_button(self, label: str, url: str) -> None:
        self.links.append((label, url))

    def metric(self, label: str, value: str) -> None:
        self.metrics.append((label, value))

    def button(self, label: str, **kwargs) -> bool:
        return False

    def text_input(self, label: str, value: str = "") -> str:
        return value

    def selectbox(self, label: str, options, **kwargs):
        return list(options)[0]


class DummyForm:
    def __enter__(self) -> "DummyForm":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class InfluencerPlanningRuntimeTests(unittest.TestCase):
    def test_workspace_notes_tab_uses_program_workspace_summary(self) -> None:
        actor = CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value)
        summary = SimpleNamespace(id="summary")
        campaign = SimpleNamespace(
            id="campaign-1",
            program_id="program-1",
            workstream_id="workstream-1",
            campaign_title="Runtime Test Campaign",
            is_on_hold=False,
            client_name="Client",
            program_name="Program",
            manager_display_name="T",
            planning_status="not_started",
            next_planning_step=None,
            next_planning_step_due_date=None,
            launch_date=None,
            wrap_date=None,
            invoice_date=None,
            invoice_status=None,
        )
        service = Mock()
        service.get_influencer_campaign_detail.return_value = campaign
        service.get_program_workspace_summary.return_value = summary

        with (
            patch.object(views.st, "button", return_value=False),
            patch.object(views.st, "markdown"),
            patch.object(views.st, "caption"),
            patch.object(views.st, "info"),
            patch.object(views.st, "tabs", return_value=[DummyTab() for _ in range(9)]),
            patch.object(views, "render_overview") as render_overview,
            patch.object(views, "render_steps") as render_steps,
            patch.object(views, "render_approvals") as render_approvals,
            patch.object(views, "render_content_rounds") as render_content_rounds,
            patch.object(views, "render_creator_summary") as render_creator_summary,
            patch.object(views, "render_timeline") as render_timeline,
            patch.object(views, "render_resources") as render_resources,
            patch.object(views, "render_notes") as render_notes,
            patch.object(views, "render_activity") as render_activity,
        ):
            views.render_workspace(actor, service, [actor], campaign.id)

        service.get_program_workspace_summary.assert_called_once_with(actor, campaign.program_id)
        render_overview.assert_called_once_with(actor, service, [actor], campaign)
        render_steps.assert_called_once_with(actor, service, [actor], campaign)
        render_approvals.assert_called_once_with(actor, service, campaign)
        render_content_rounds.assert_called_once_with(actor, service, campaign)
        render_creator_summary.assert_called_once_with(actor, service, campaign)
        render_timeline.assert_called_once_with(actor, service, campaign)
        render_resources.assert_called_once_with(actor, service, campaign)
        render_notes.assert_called_once_with(actor, service, summary)
        render_activity.assert_called_once_with(actor, service, campaign)

    def test_quick_resource_links_do_not_pass_streamlit_keys(self) -> None:
        actor = CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value)
        campaign = SimpleNamespace(
            id="campaign-1",
            program_id="program-1",
            workstream_id="workstream-1",
            track_sheet_url="https://example.com/track",
            influencer_brief_url=None,
            bitly_link_url=None,
            invoice_url=None,
            eop_survey_url=None,
            campaign_brief_url=None,
            click2cart_link_url=None,
        )
        service = Mock()
        service.get_program_workspace_summary.return_value = SimpleNamespace(id="summary")
        service.list_program_resources.return_value = []

        with (
            patch.object(views.st, "columns", side_effect=lambda count: [FakeColumn() for _ in range(count)]),
            patch.object(views.st, "dataframe"),
            patch.object(views.st, "form", return_value=DummyForm()),
            patch.object(views.st, "form_submit_button", return_value=False),
        ):
            views.render_resources(actor, service, campaign)

    def test_quick_link_normalization_uses_workbook_order_and_omits_missing_urls(self) -> None:
        campaign = SimpleNamespace(
            track_sheet_url="https://example.com/track",
            influencer_brief_url=None,
            bitly_link_url="https://example.com/bitly",
            click2cart_link_url="https://example.com/c2c",
            invoice_url=None,
            eop_survey_url="https://example.com/eop",
            influencer_education_url="https://example.com/edu",
            campaign_brief_url=None,
        )

        links = campaign_quick_links(campaign)

        self.assertEqual(["Track Sheet", "Bitly Link", "Click2Cart Link", "EOP Survey", "Influencer Education"], [link.label for link in links])
        self.assertNotIn("Invoice", [link.label for link in links])

    def test_sequence_preview_preserves_sequence_order_undated_rows_and_avoids_duplicates(self) -> None:
        steps = [
            SimpleNamespace(id="1", step_title="Send brief", sequence_order=1, due_date=date(2026, 5, 28), completed_date=date(2026, 5, 28), status="complete", is_active=True),
            SimpleNamespace(id="2", step_title="2 weeks required: client review", sequence_order=2, due_date=None, completed_date=None, status="not_started", is_active=True),
            SimpleNamespace(id="3", step_title="Client approvals due", sequence_order=3, due_date=date(2026, 6, 11), completed_date=None, status="waiting", is_active=True),
            SimpleNamespace(id="4", step_title="Hire and secure scripts", sequence_order=4, due_date=date(2026, 6, 12), completed_date=None, status="not_started", is_active=True),
            SimpleNamespace(id="5", step_title="Content due", sequence_order=5, due_date=date(2026, 7, 1), completed_date=None, status="not_started", is_active=True),
            SimpleNamespace(id="6", step_title="Launch", sequence_order=6, due_date=date(2026, 9, 1), completed_date=None, status="not_started", is_active=True),
            SimpleNamespace(id="7", step_title="Campaign wraps", sequence_order=7, due_date=date(2026, 10, 31), completed_date=None, status="not_started", is_active=True),
            SimpleNamespace(id="8", step_title="Inactive", sequence_order=8, due_date=date(2026, 11, 1), completed_date=None, status="not_started", is_active=False),
        ]

        preview = planning_sequence_preview(steps, today=date(2026, 6, 12), upcoming_limit=2)

        self.assertEqual(["1", "2", "3", "4", "5", "6", "7"], [step.id for step in preview])
        self.assertEqual(len({step.id for step in preview}), len(preview))
        self.assertEqual(["1", "2", "3", "4", "5", "6", "7"], [step.id for step in [step for step in steps if step.is_active]])

    def test_next_sequence_step_excludes_completed_and_inactive_steps(self) -> None:
        steps = [
            SimpleNamespace(id="1", step_title="Complete", due_date=date(2026, 8, 1), completed_date=date(2026, 8, 1), status="complete", is_active=True),
            SimpleNamespace(id="2", step_title="Inactive", due_date=date(2026, 8, 2), completed_date=None, status="not_started", is_active=False),
            SimpleNamespace(id="3", step_title="Next by sequence", due_date=None, completed_date=None, status="not_started", is_active=True),
        ]

        self.assertEqual("3", next_sequence_step(steps).id)
        self.assertEqual("", compact_date(None))
        self.assertEqual("8/12", compact_date(date(2026, 8, 12), reference_year=2026))
        self.assertEqual("1/5/2027", compact_date(date(2027, 1, 5), reference_year=2026))

    def test_repository_next_planning_step_sql_uses_sequence_first_ordering(self) -> None:
        source = inspect.getsource(CampaignOpsRepository.list_influencer_campaigns)
        self.assertIn("order by influencer_campaign_id, sequence_order asc, due_date asc nulls last, created_at asc", source)

    def test_campaign_block_renders_hold_reason_empty_steps_and_open_action_helper(self) -> None:
        campaign = SimpleNamespace(
            id="campaign-1",
            campaign_title="DOLORES TUNA BTS",
            manager_display_name="T",
            planning_status="influencer_approval",
            is_on_hold=True,
            hold_reason="Waiting on client approvals",
            latest_update=None,
            waiting_on=None,
            launch_date=None,
            wrap_date=None,
            track_sheet_url=None,
            influencer_brief_url=None,
            bitly_link_url=None,
            click2cart_link_url=None,
            invoice_url=None,
            eop_survey_url=None,
            influencer_education_url=None,
            campaign_brief_url=None,
        )
        rendered: list[str] = []
        with (
            patch.object(views.st, "markdown", side_effect=lambda body, **kwargs: rendered.append(body)),
            patch.object(views.st, "columns", return_value=[FakeColumn(), FakeColumn(), FakeColumn()]),
        ):
            views.render_campaign_block(campaign, [])

        html = "".join(rendered)
        self.assertIn("ON HOLD", html)
        self.assertIn("Hold reason: Waiting on client approvals", html)
        self.assertIn("No planning steps yet.", html)

        state: dict[str, object] = {}
        select_campaign_for_open(state, "campaign-1")
        self.assertEqual("campaign-1", state["campaign_ops_selected_influencer_campaign_id"])

    def test_unknown_planning_statuses_fall_back_to_valid_options(self) -> None:
        self.assertEqual(0, views.option_index(["not_started", "in_progress"], "legacy", "not_started"))
        self.assertEqual(1, views.option_index(["planning", "live"], "live", "planning"))
        self.assertEqual(0, views.option_index(["planning", "live"], None, "missing"))

    def test_influencer_view_runtime_call_patterns_are_valid(self) -> None:
        failures: list[str] = []
        for path in INFLUENCER_VIEW_FILES:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func_name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if func_name == "safe_text" and len(node.args) > 1:
                    failures.append(f"{path}:{node.lineno} calls safe_text with {len(node.args)} positional args")
                if func_name == "link_button" and any(keyword.arg == "key" for keyword in node.keywords):
                    failures.append(f"{path}:{node.lineno} passes unsupported key= to st.link_button")
                if func_name == "render_notes" and len(node.args) != 3:
                    failures.append(f"{path}:{node.lineno} calls render_notes with {len(node.args)} positional args")
        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()
