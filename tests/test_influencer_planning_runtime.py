from __future__ import annotations

import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.campaign_ops.influencer import views
from core.campaign_ops.enums import UserRole
from core.campaign_ops.models import CampaignOpsUser


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
