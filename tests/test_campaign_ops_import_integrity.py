from __future__ import annotations

import ast
import importlib
import inspect
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


CAMPAIGN_OPS_IMPORT_ROOTS = (
    ROOT / "app" / "pages",
    ROOT / "app" / "campaign_ops",
    ROOT / "core" / "campaign_ops",
)

REQUIRED_TRACKED_FILES = (
    "app/pages/campaigns.py",
    "app/campaign_ops/cross_team/views.py",
    "app/campaign_ops/cross_team/formatting.py",
    "app/campaign_ops/ui/components.py",
    "app/campaign_ops/ui/formatting.py",
    "app/campaign_ops/ui/badges.py",
    "app/campaign_ops/ui/navigation.py",
    "app/campaign_ops/ui/styles.py",
    "app/campaign_ops/reporting_requests/views.py",
    "app/campaign_ops/insights/views.py",
    "app/campaign_ops/retail_media/views.py",
    "app/campaign_ops/content_management/views.py",
    "app/campaign_ops/influencer/views.py",
    "app/campaign_ops/influencer/live_views.py",
    "app/campaign_ops/influencer/recap_views.py",
    "core/campaign_ops/models.py",
    "core/campaign_ops/repository.py",
    "core/campaign_ops/service.py",
)

REQUIRED_MIGRATIONS = tuple(
    f"db/migrations/{index:03d}_campaign_ops"
    for index in range(1, 12)
)

REQUIRED_MODEL_SYMBOLS = (
    "CampaignOpsUser",
    "CrossTeamDashboardSummary",
    "DashboardMetricSet",
    "NeedsAttentionRow",
    "WaitingOnRow",
    "WorkloadByPersonRow",
    "UpcomingMilestoneRow",
    "DashboardProgramRow",
    "DashboardWorkflowCard",
    "InfluencerDashboardCard",
    "RetailMediaDashboardCard",
    "ContentDashboardCard",
    "InsightsDashboardCard",
    "RequestDashboardCard",
    "ReportingRequestListRow",
    "InsightsPortfolioRow",
    "RetailMediaPortfolioRow",
    "ContentPortfolioRow",
    "InfluencerPlanningPortfolioRow",
    "InfluencerLivePortfolioRow",
    "InfluencerRecapPortfolioRow",
)

REQUIRED_UI_MODULES = (
    "core.campaign_ops.models",
    "core.campaign_ops.repository",
    "core.campaign_ops.service",
    "app.campaign_ops.ui.components",
    "app.campaign_ops.cross_team.views",
    "app.campaign_ops.reporting_requests.views",
    "app.campaign_ops.insights.views",
    "app.campaign_ops.retail_media.views",
    "app.campaign_ops.content_management.views",
    "app.campaign_ops.influencer.views",
    "app.campaign_ops.influencer.live_views",
    "app.campaign_ops.influencer.recap_views",
    "app.campaign_ops.program_workspace",
    "app.pages.campaigns",
    "app.main",
)

REQUIRED_SERVICE_METHODS = (
    "get_cross_team_dashboard_summary",
    "list_program_portfolio",
    "list_user_programs",
    "get_program_workspace_summary",
    "list_reporting_requests",
    "get_reporting_request_detail",
    "list_insights_projects",
    "list_retail_media_campaigns",
    "list_content_programs",
    "list_influencer_campaigns",
    "list_influencer_live_campaigns",
    "list_influencer_recap_campaigns",
)

REQUIRED_REPOSITORY_METHODS = (
    "list_program_portfolio",
    "list_programs_assigned_to_user",
    "list_dashboard_task_rows",
    "list_dashboard_milestone_rows",
    "list_dashboard_resource_rows",
    "list_reporting_requests",
    "list_insights_projects",
    "list_retail_media_campaigns",
    "list_content_programs",
    "list_influencer_campaigns",
    "list_influencer_live_campaigns",
    "list_influencer_recap_campaigns",
)


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


class CampaignOpsImportIntegrityTests(unittest.TestCase):
    def test_required_campaign_ops_files_are_tracked(self) -> None:
        tracked = set(
            subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
        )
        for path in REQUIRED_TRACKED_FILES:
            self.assertIn(path, tracked)
        for prefix in REQUIRED_MIGRATIONS:
            self.assertTrue(any(path.startswith(prefix) for path in tracked), prefix)

    def test_campaign_ops_from_imports_resolve(self) -> None:
        failures: list[str] = []
        for root in CAMPAIGN_OPS_IMPORT_ROOTS:
            for path in root.rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                package = _module_name(path).rsplit(".", 1)[0]
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ImportFrom) or node.module is None:
                        continue
                    module_name = node.module
                    if node.level:
                        module_name = importlib.util.resolve_name("." * node.level + node.module, package)
                    if not (
                        module_name.startswith("app.")
                        or module_name.startswith("core.")
                        or module_name.startswith("tests.")
                    ):
                        continue
                    try:
                        module = importlib.import_module(module_name)
                    except Exception as exc:  # pragma: no cover - failure message is the assertion payload
                        failures.append(f"{path}:{node.lineno}: import {module_name}: {exc}")
                        continue
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        if not hasattr(module, alias.name):
                            failures.append(f"{path}:{node.lineno}: {module_name}.{alias.name}")
        self.assertEqual([], failures)

    def test_required_model_symbols_exist(self) -> None:
        models = importlib.import_module("core.campaign_ops.models")
        for symbol in REQUIRED_MODEL_SYMBOLS:
            self.assertTrue(hasattr(models, symbol), symbol)
        self.assertIs(models.InfluencerDashboardCard, models.DashboardWorkflowCard)
        self.assertIs(models.RetailMediaDashboardCard, models.DashboardWorkflowCard)
        self.assertIs(models.ContentDashboardCard, models.DashboardWorkflowCard)
        self.assertIs(models.InsightsDashboardCard, models.DashboardWorkflowCard)
        self.assertIs(models.RequestDashboardCard, models.DashboardWorkflowCard)

    def test_campaign_ops_ui_modules_import(self) -> None:
        for module_name in REQUIRED_UI_MODULES:
            with self.subTest(module=module_name):
                importlib.import_module(module_name)

    def test_required_service_and_repository_methods_exist(self) -> None:
        service = importlib.import_module("core.campaign_ops.service").CampaignOpsService
        repository = importlib.import_module("core.campaign_ops.repository").CampaignOpsRepository
        for method_name in REQUIRED_SERVICE_METHODS:
            self.assertTrue(callable(getattr(service, method_name, None)), method_name)
            self.assertIn("self", inspect.signature(getattr(service, method_name)).parameters)
        for method_name in REQUIRED_REPOSITORY_METHODS:
            self.assertTrue(callable(getattr(repository, method_name, None)), method_name)
            self.assertIn("self", inspect.signature(getattr(repository, method_name)).parameters)


if __name__ == "__main__":
    unittest.main()
