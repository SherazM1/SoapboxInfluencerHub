from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.campaign_ops.enums import CrossStage, ProgramStatus, RiskLevel, UserRole, WorkstreamType
from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsValidationError
from core.campaign_ops.influencer import (
    INFLUENCER_STAGE_LIVE,
    INFLUENCER_STAGE_RECAPPING,
    PLANNING_STATUS_BRIEF_DEVELOPMENT,
    RECAP_STATUS_COLLECTING_DATA,
)
from core.campaign_ops.repository import CampaignOpsRepository
from core.campaign_ops.service import CampaignOpsService

ALLOW_ENV = "ALLOW_RECAP_VALIDATION_FIXTURE"
PROGRAM_NAME = "RECAP VALIDATION PROGRAM"
CAMPAIGN_TITLE = "RECAP VALIDATION - DO NOT USE"
FIXTURE_MARKER = "recap-validation-fixture"
LATEST_UPDATE = "Sent validation invoice to client 7/6"
WAITING_ON = "Client approval of validation recap deck"

RESOURCE_FIXTURES = [
    ("Track Sheet", "Track Sheet", "https://example.com/track-sheet"),
    ("Influencer Brief", "Influencer Brief", "https://example.com/influencer-brief"),
    ("Click2Cart Link", "Click2Cart Link", "https://example.com/click2cart"),
    ("Bitly Link", "Bitly Link", "https://example.com/bitly"),
    ("Invoice", "Invoice", "https://example.com/invoice"),
    ("EOP Survey", "EOP Survey", "https://example.com/eop-survey"),
    ("Client-Facing Influencer Review", "Client-Facing Influencer Review", "https://example.com/client-facing-review"),
    ("Live Content Tracker", "Live Content Tracker", "https://example.com/live-content-tracker"),
    ("Recap Deck", "Recap Deck", "https://example.com/recap-deck"),
    ("Final Performance Data", "Final Performance Data", "https://example.com/final-performance-data"),
    ("Sales Lift Analysis", "Sales Lift Analysis", "https://example.com/sales-lift-analysis"),
]

CREATOR_NAMES = [
    "Validation Creator 1",
    "Validation Creator 2",
    "Validation Creator 3",
    "Validation Creator 4",
]

REQUIREMENT_FIXTURES = [
    ("Recap Deck", "Recap Deck Finalization", "in_progress"),
    ("Invoice", "Financial Close", "waiting"),
]

LAUNCH_FIXTURES = [
    {
        "group_name": "MOMS",
        "product_name": "Validation Product A",
        "retailer_name": "Walmart",
        "online_launch_date": date(2026, 7, 1),
        "in_store_launch_date": date(2026, 7, 8),
        "launch_status": "live",
        "product_url": "https://example.com/product-a",
        "retailer_url": "https://example.com/walmart-a",
        "notes": "Validation launch item for Recap baseline",
        "sort_order": 1,
    },
    {
        "group_name": "DADS",
        "product_name": "Validation Product B",
        "retailer_name": "7-Eleven",
        "online_launch_date": date(2026, 7, 3),
        "in_store_launch_date": None,
        "launch_status": "online_live",
        "product_url": "https://example.com/product-b",
        "retailer_url": "https://example.com/7-eleven-b",
        "notes": "Validation launch item for Recap baseline",
        "sort_order": 2,
    },
]


@dataclass(slots=True)
class FixtureResult:
    program_id: str | None = None
    program_name: str = PROGRAM_NAME
    campaign_id: str | None = None
    campaign_name: str = CAMPAIGN_TITLE
    manager_name: str | None = None
    influencer_stage: str | None = None
    recap_status: str | None = None
    resource_count: int = 0
    requirement_count: int = 0
    creator_count: int = 0
    launch_item_count: int = 0
    ready_to_close: str | None = None
    deactivated: list[str] | None = None


def guard_allows_mutation(env: dict[str, str] | None = None) -> bool:
    return (env or os.environ).get(ALLOW_ENV) == "1"


def require_guard(env: dict[str, str] | None = None) -> None:
    if not guard_allows_mutation(env):
        print(f"{ALLOW_ENV}=1 is required. No database changes were made.")
        raise SystemExit(2)


def create_fixture(service: CampaignOpsService, repository: CampaignOpsRepository) -> FixtureResult:
    actor = select_actor(repository)
    manager = select_manager(repository)
    program = find_program(repository) or service.create_program(
        actor.id if actor else None,
        PROGRAM_NAME,
        primary_workstream_type=WorkstreamType.INFLUENCER.value,
        status=ProgramStatus.ACTIVE.value,
        cross_stage=CrossStage.RECAPPING.value,
        risk_level=RiskLevel.UNRATED.value,
        description=f"{FIXTURE_MARKER}: safe visual QA program.",
        latest_update="Validation fixture program for Recap baseline QA.",
    )
    if not program.is_active and actor:
        program = service.reactivate_program(actor, program.id)

    campaign = find_campaign(repository, program.id)
    if campaign is None:
        campaign = service.create_influencer_campaign(
            actor,
            program_id=program.id,
            campaign_title=CAMPAIGN_TITLE,
            manager_user_id=manager.id if manager else None,
            planning_status=PLANNING_STATUS_BRIEF_DEVELOPMENT,
            target_creator_count=4,
            approved_creator_count=4,
            contracted_creator_count=4,
            latest_update=LATEST_UPDATE,
            waiting_on=WAITING_ON,
            invoice_date=date(2026, 7, 6),
            invoice_status="sent",
            is_on_hold=False,
        )
    elif not campaign.is_active:
        campaign = service.reactivate_influencer_campaign(actor, campaign.id)

    if campaign.influencer_stage == "planning":
        campaign = service.transition_influencer_campaign_to_live(actor, campaign.id)
    if campaign.influencer_stage == INFLUENCER_STAGE_LIVE:
        ensure_creators(service, actor, campaign.id, can_write=True)
        campaign = service.transition_influencer_campaign_to_recapping(
            actor,
            campaign.id,
            recap_status=RECAP_STATUS_COLLECTING_DATA,
        )

    if campaign.influencer_stage != INFLUENCER_STAGE_RECAPPING:
        raise CampaignOpsValidationError(f"Fixture campaign must be Recapping; found {campaign.influencer_stage}.")

    service.update_influencer_campaign(
        actor,
        campaign.id,
        manager_user_id=manager.id if manager else campaign.manager_user_id,
        influencer_stage=INFLUENCER_STAGE_RECAPPING,
        planning_status=RECAP_STATUS_COLLECTING_DATA,
        latest_update=LATEST_UPDATE,
        waiting_on=WAITING_ON,
        is_on_hold=False,
        hold_reason=None,
        invoice_date=date(2026, 7, 6),
        invoice_status="sent",
        invoice_amount=0,
        target_creator_count=4,
        approved_creator_count=4,
        contracted_creator_count=4,
    )
    recap_record = service.create_or_update_influencer_recap_record(
        actor,
        campaign.id,
        recap_status=RECAP_STATUS_COLLECTING_DATA,
        latest_update=LATEST_UPDATE,
        waiting_on=WAITING_ON,
        reporting_due_date=date(2026, 7, 12),
        draft_recap_due_date=date(2026, 7, 15),
        client_recap_date=date(2026, 7, 22),
        sales_lift_analysis_required=True,
        sales_lift_analysis_status="in_progress",
        final_performance_data_status="complete",
        creator_closeout_status="in_progress",
        eop_survey_status="complete",
        invoice_status="sent",
        financial_close_status="waiting",
        lessons_learned=f"{FIXTURE_MARKER}: fixture row for visual QA only.",
    )

    resources = ensure_resources(service, actor, program.id, campaign.workstream_id)
    creators = ensure_creators(service, actor, campaign.id, can_write=False)
    requirements = ensure_requirements(service, actor, campaign.id)
    launches = ensure_launch_items(service, actor, campaign.id)
    summary = service.get_influencer_recap_workspace_summary(actor, campaign.id)
    detail = service.get_influencer_recap_campaign_detail(actor, campaign.id)

    return FixtureResult(
        program_id=program.id,
        campaign_id=campaign.id,
        manager_name=manager.display_name if manager else None,
        influencer_stage=detail.influencer_stage,
        recap_status=recap_record.recap_status,
        resource_count=len(resources),
        requirement_count=len([item for item in requirements if item.is_active]),
        creator_count=len([item for item in creators if item.is_active]),
        launch_item_count=len([item for item in launches if item.is_active]),
        ready_to_close=summary.ready_to_close_state,
    )


def cleanup_fixture(service: CampaignOpsService, repository: CampaignOpsRepository) -> FixtureResult:
    actor = select_actor(repository)
    program = find_program(repository)
    campaign = find_campaign(repository, program.id) if program else None
    result = FixtureResult(program_id=program.id if program else None, campaign_id=campaign.id if campaign else None, deactivated=[])
    if program is None or campaign is None:
        return result

    for resource in service.list_program_resources(actor, program.id, include_inactive=True):
        if getattr(resource, "is_active", False) and is_fixture_resource(resource):
            service.deactivate_resource(actor, resource.id)
            result.deactivated.append(f"resource:{resource.title}")

    if campaign.influencer_stage == INFLUENCER_STAGE_RECAPPING:
        for requirement in service.list_influencer_recap_requirements(actor, campaign.id, include_inactive=True):
            if requirement.is_active and requirement.requirement_title in {title for _rtype, title, _status in REQUIREMENT_FIXTURES}:
                service.deactivate_influencer_recap_requirement(actor, campaign.id, requirement.id)
                result.deactivated.append(f"requirement:{requirement.requirement_title}")
        for item in service.list_influencer_recap_launch_items(actor, campaign.id, include_inactive=True):
            if item.is_active and item.product_name in {fixture["product_name"] for fixture in LAUNCH_FIXTURES}:
                service.deactivate_influencer_recap_launch_item(actor, campaign.id, item.id)
                result.deactivated.append(f"launch_item:{item.product_name}")

    if campaign.is_active:
        service.deactivate_influencer_campaign(actor, campaign.id)
        result.deactivated.append(f"campaign:{campaign.campaign_title}")
    return result


def select_actor(repository: CampaignOpsRepository) -> Any | None:
    users = repository.list_active_users()
    return next((user for user in users if user.role == UserRole.ADMINISTRATOR.value), users[0] if users else None)


def select_manager(repository: CampaignOpsRepository) -> Any | None:
    users = repository.list_active_users()
    return next((user for user in users if user.display_name == "T"), users[0] if users else None)


def find_program(repository: CampaignOpsRepository) -> Any | None:
    return next((program for program in repository.list_programs(active_only=False) if program.program_name == PROGRAM_NAME), None)


def find_campaign(repository: CampaignOpsRepository, program_id: str) -> Any | None:
    return next((row for row in repository.list_influencer_campaigns(include_inactive=True, stage=None) if row.program_id == program_id and row.campaign_title == CAMPAIGN_TITLE), None)


def ensure_resources(service: CampaignOpsService, actor: Any | None, program_id: str, workstream_id: str | None) -> list[Any]:
    existing = service.list_program_resources(actor, program_id, include_inactive=True)
    by_title = {resource.title: resource for resource in existing}
    ensured: list[Any] = []
    for resource_type, title, url in RESOURCE_FIXTURES:
        current = by_title.get(title)
        if current is None:
            try:
                current = service.create_resource(actor, program_id, title=title, resource_type=resource_type, workstream_id=workstream_id, url=url, notes=FIXTURE_MARKER)
            except CampaignOpsValidationError:
                current = service.create_resource(actor, program_id, title=title, resource_type="Custom", workstream_id=workstream_id, url=url, notes=f"{FIXTURE_MARKER}: {resource_type}")
        else:
            if not current.is_active:
                current = service.reactivate_resource(actor, current.id)
            current = service.update_resource_details(actor, current.id, title=title, resource_type=resource_type, workstream_id=workstream_id, url=url, notes=FIXTURE_MARKER)
        ensured.append(current)
    return ensured


def ensure_creators(service: CampaignOpsService, actor: Any | None, campaign_id: str, *, can_write: bool) -> list[Any]:
    existing = {creator.creator_name: creator for creator in service.list_influencer_live_creators(actor, campaign_id, include_inactive=True)}
    if not can_write:
        missing = [name for name in CREATOR_NAMES if name not in existing]
        if missing:
            raise CampaignOpsValidationError("Validation creators are missing and cannot be created after the campaign has moved to Recapping.")
        return [existing[name] for name in CREATOR_NAMES]
    ensured: list[Any] = []
    for index, name in enumerate(CREATOR_NAMES, start=1):
        payload = {
            "live_status": "paid_live_complete",
            "actual_live_date": date(2026, 7, 1),
            "paid_live_end_date": date(2026, 7, 6),
            "content_url": f"https://example.com/validation-creator-{index}",
            "impressions_reporting_required": True,
            "latest_impressions": 1000 + index,
            "last_impressions_update_date": date(2026, 7, 6),
        }
        current = existing.get(name)
        if current is None:
            current = service.create_influencer_live_creator(actor, campaign_id, name, **payload)
        else:
            current = service.update_influencer_live_creator(actor, campaign_id, current.id, creator_name=name, **payload)
        ensured.append(current)
    return ensured


def ensure_requirements(service: CampaignOpsService, actor: Any | None, campaign_id: str) -> list[Any]:
    existing = {item.requirement_title: item for item in service.list_influencer_recap_requirements(actor, campaign_id, include_inactive=True)}
    ensured: list[Any] = []
    for requirement_type, title, status in REQUIREMENT_FIXTURES:
        payload = {"required": True, "status": status, "due_date": date(2026, 7, 18), "waiting_on": WAITING_ON, "notes": FIXTURE_MARKER}
        current = existing.get(title)
        if current is None:
            current = service.create_influencer_recap_requirement(actor, campaign_id, requirement_type, title, **payload)
        else:
            if not current.is_active:
                current = service.reactivate_influencer_recap_requirement(actor, campaign_id, current.id)
            current = service.update_influencer_recap_requirement(actor, campaign_id, current.id, requirement_type=requirement_type, requirement_title=title, **payload)
        ensured.append(current)
    return ensured


def ensure_launch_items(service: CampaignOpsService, actor: Any | None, campaign_id: str) -> list[Any]:
    existing = {item.product_name: item for item in service.list_influencer_recap_launch_items(actor, campaign_id, include_inactive=True)}
    ensured: list[Any] = []
    for fixture in LAUNCH_FIXTURES:
        product_name = str(fixture["product_name"])
        payload = {key: value for key, value in fixture.items() if key != "product_name"}
        current = existing.get(product_name)
        if current is None:
            current = service.create_influencer_recap_launch_item(actor, campaign_id, product_name, **payload)
        else:
            if not current.is_active:
                current = service.reactivate_influencer_recap_launch_item(actor, campaign_id, current.id)
            current = service.update_influencer_recap_launch_item(actor, campaign_id, current.id, product_name=product_name, **payload)
        ensured.append(current)
    return ensured


def is_fixture_resource(resource: Any) -> bool:
    return resource.title in {title for _rtype, title, _url in RESOURCE_FIXTURES} or FIXTURE_MARKER in str(getattr(resource, "notes", "") or "")


def print_create_result(result: FixtureResult) -> None:
    print(f"Program: {result.program_id} | {result.program_name}")
    print(f"Influencer Campaign: {result.campaign_id} | {result.campaign_name}")
    print(f"Manager assigned: {result.manager_name or '-'}")
    print(f"Influencer stage: {result.influencer_stage}")
    print(f"Recap status: {result.recap_status}")
    print(f"Resources: {result.resource_count}")
    print(f"Requirements: {result.requirement_count}")
    print(f"Creators: {result.creator_count}")
    print(f"Launch items: {result.launch_item_count}")
    print(f"Ready to Close: {result.ready_to_close}")
    print("Inspect: Influencer > Recapping > T - Recapping")
    print("Fixture created/updated successfully. Safe to rerun.")


def print_cleanup_result(result: FixtureResult) -> None:
    print(f"Program: {result.program_id or '-'} | {result.program_name}")
    print(f"Influencer Campaign: {result.campaign_id or '-'} | {result.campaign_name}")
    if result.deactivated:
        print("Deactivated:")
        for item in result.deactivated:
            print(f"- {item}")
    else:
        print("No active validation fixture records needed cleanup.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or cleanup the Recap visual QA validation fixture.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create", action="store_true", help="Create or update the validation fixture.")
    mode.add_argument("--cleanup", action="store_true", help="Soft deactivate the validation fixture records.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, env: dict[str, str] | None = None, service: CampaignOpsService | None = None, repository: CampaignOpsRepository | None = None) -> int:
    args = parse_args(argv)
    require_guard(env)
    repository = repository or CampaignOpsRepository()
    service = service or CampaignOpsService()
    try:
        if args.create:
            print_create_result(create_fixture(service, repository))
        else:
            print_cleanup_result(cleanup_fixture(service, repository))
    except CampaignOpsError as exc:
        print(f"Fixture failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
