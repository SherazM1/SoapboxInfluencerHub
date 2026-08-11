from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.campaign_ops.enums import UserRole
from scripts.dev.create_recap_validation_fixture import (
    ALLOW_ENV,
    CAMPAIGN_TITLE,
    PROGRAM_NAME,
    RESOURCE_FIXTURES,
    create_fixture,
    cleanup_fixture,
    require_guard,
)


class FakeRepository:
    def __init__(self) -> None:
        self.users = [
            SimpleNamespace(id="admin-1", display_name="Admin", role=UserRole.ADMINISTRATOR.value, is_active=True),
            SimpleNamespace(id="t-1", display_name="T", role=UserRole.TEAM_MEMBER.value, is_active=True),
        ]
        self.programs: list[SimpleNamespace] = []
        self.campaigns: list[SimpleNamespace] = []

    def list_active_users(self):
        return [user for user in self.users if user.is_active]

    def list_programs(self, active_only: bool = True, **_kwargs):
        return [program for program in self.programs if program.is_active or not active_only]

    def list_influencer_campaigns(self, include_inactive: bool = False, stage: str | None = None, **_kwargs):
        rows = [campaign for campaign in self.campaigns if include_inactive or campaign.is_active]
        if stage:
            rows = [campaign for campaign in rows if campaign.influencer_stage == stage]
        return rows


class FakeService:
    def __init__(self, repository: FakeRepository) -> None:
        self.repository = repository
        self.resources: list[SimpleNamespace] = []
        self.creators: list[SimpleNamespace] = []
        self.requirements: list[SimpleNamespace] = []
        self.launches: list[SimpleNamespace] = []

    def create_program(self, _actor_id, program_name, **kwargs):
        program = SimpleNamespace(id=f"program-{len(self.repository.programs)+1}", program_name=program_name, is_active=True, **kwargs)
        self.repository.programs.append(program)
        return program

    def reactivate_program(self, _actor, program_id):
        program = next(item for item in self.repository.programs if item.id == program_id)
        program.is_active = True
        return program

    def create_influencer_campaign(self, _actor, **kwargs):
        campaign = SimpleNamespace(
            id=f"campaign-{len(self.repository.campaigns)+1}",
            influencer_stage="planning",
            is_active=True,
            workstream_id="workstream-1",
            hold_reason=None,
            **kwargs,
        )
        self.repository.campaigns.append(campaign)
        return campaign

    def reactivate_influencer_campaign(self, _actor, campaign_id):
        campaign = self._campaign(campaign_id)
        campaign.is_active = True
        return campaign

    def deactivate_influencer_campaign(self, _actor, campaign_id):
        self._campaign(campaign_id).is_active = False

    def transition_influencer_campaign_to_live(self, _actor, campaign_id):
        campaign = self._campaign(campaign_id)
        campaign.influencer_stage = "live"
        return campaign

    def transition_influencer_campaign_to_recapping(self, _actor, campaign_id, recap_status=None):
        campaign = self._campaign(campaign_id)
        campaign.influencer_stage = "recapping"
        campaign.planning_status = recap_status
        return campaign

    def update_influencer_campaign(self, _actor, campaign_id, **kwargs):
        campaign = self._campaign(campaign_id)
        for key, value in kwargs.items():
            setattr(campaign, key, value)
        return campaign

    def create_or_update_influencer_recap_record(self, _actor, campaign_id, **kwargs):
        campaign = self._campaign(campaign_id)
        campaign.recap_record = SimpleNamespace(id="recap-1", influencer_campaign_id=campaign_id, **kwargs)
        return campaign.recap_record

    def list_program_resources(self, _actor, program_id, include_inactive=False):
        return [item for item in self.resources if item.program_id == program_id and (include_inactive or item.is_active)]

    def create_resource(self, _actor, program_id, title, resource_type, **kwargs):
        resource = SimpleNamespace(id=f"resource-{len(self.resources)+1}", program_id=program_id, title=title, resource_type=resource_type, is_active=True, **kwargs)
        self.resources.append(resource)
        return resource

    def reactivate_resource(self, _actor, resource_id):
        resource = self._by_id(self.resources, resource_id)
        resource.is_active = True
        return resource

    def update_resource_details(self, _actor, resource_id, **kwargs):
        resource = self._by_id(self.resources, resource_id)
        for key, value in kwargs.items():
            setattr(resource, key, value)
        return resource

    def deactivate_resource(self, _actor, resource_id):
        self._by_id(self.resources, resource_id).is_active = False

    def list_influencer_live_creators(self, _actor, campaign_id, include_inactive=False):
        return [item for item in self.creators if item.influencer_campaign_id == campaign_id and (include_inactive or item.is_active)]

    def create_influencer_live_creator(self, _actor, campaign_id, creator_name, **kwargs):
        creator = SimpleNamespace(id=f"creator-{len(self.creators)+1}", influencer_campaign_id=campaign_id, creator_name=creator_name, is_active=True, **kwargs)
        self.creators.append(creator)
        return creator

    def update_influencer_live_creator(self, _actor, _campaign_id, creator_id, **kwargs):
        creator = self._by_id(self.creators, creator_id)
        for key, value in kwargs.items():
            setattr(creator, key, value)
        return creator

    def list_influencer_recap_requirements(self, _actor, campaign_id, include_inactive=False):
        return [item for item in self.requirements if item.influencer_campaign_id == campaign_id and (include_inactive or item.is_active)]

    def create_influencer_recap_requirement(self, _actor, campaign_id, requirement_type, requirement_title, **kwargs):
        requirement = SimpleNamespace(id=f"requirement-{len(self.requirements)+1}", influencer_campaign_id=campaign_id, requirement_type=requirement_type, requirement_title=requirement_title, is_active=True, **kwargs)
        self.requirements.append(requirement)
        return requirement

    def reactivate_influencer_recap_requirement(self, _actor, _campaign_id, requirement_id):
        requirement = self._by_id(self.requirements, requirement_id)
        requirement.is_active = True
        return requirement

    def update_influencer_recap_requirement(self, _actor, _campaign_id, requirement_id, **kwargs):
        requirement = self._by_id(self.requirements, requirement_id)
        for key, value in kwargs.items():
            setattr(requirement, key, value)
        return requirement

    def deactivate_influencer_recap_requirement(self, _actor, _campaign_id, requirement_id):
        self._by_id(self.requirements, requirement_id).is_active = False

    def list_influencer_recap_launch_items(self, _actor, campaign_id, include_inactive=False):
        return [item for item in self.launches if item.influencer_campaign_id == campaign_id and (include_inactive or item.is_active)]

    def create_influencer_recap_launch_item(self, _actor, campaign_id, product_name, **kwargs):
        launch = SimpleNamespace(id=f"launch-{len(self.launches)+1}", influencer_campaign_id=campaign_id, product_name=product_name, is_active=True, **kwargs)
        self.launches.append(launch)
        return launch

    def reactivate_influencer_recap_launch_item(self, _actor, _campaign_id, launch_id):
        launch = self._by_id(self.launches, launch_id)
        launch.is_active = True
        return launch

    def update_influencer_recap_launch_item(self, _actor, _campaign_id, launch_id, **kwargs):
        launch = self._by_id(self.launches, launch_id)
        for key, value in kwargs.items():
            setattr(launch, key, value)
        return launch

    def deactivate_influencer_recap_launch_item(self, _actor, _campaign_id, launch_id):
        self._by_id(self.launches, launch_id).is_active = False

    def get_influencer_recap_workspace_summary(self, _actor, campaign_id):
        return SimpleNamespace(ready_to_close_state="Not Ready")

    def get_influencer_recap_campaign_detail(self, _actor, campaign_id):
        campaign = self._campaign(campaign_id)
        return SimpleNamespace(influencer_stage=campaign.influencer_stage)

    def _campaign(self, campaign_id):
        return self._by_id(self.repository.campaigns, campaign_id)

    @staticmethod
    def _by_id(items, item_id):
        return next(item for item in items if item.id == item_id)


class RecapValidationFixtureTests(unittest.TestCase):
    def test_guard_blocks_without_explicit_env(self) -> None:
        with self.assertRaises(SystemExit):
            require_guard({})
        require_guard({ALLOW_ENV: "1"})

    def test_create_mode_is_idempotent_and_does_not_duplicate_records(self) -> None:
        repository = FakeRepository()
        service = FakeService(repository)

        first = create_fixture(service, repository)
        second = create_fixture(service, repository)

        self.assertEqual(first.campaign_id, second.campaign_id)
        self.assertEqual([PROGRAM_NAME], [program.program_name for program in repository.programs])
        self.assertEqual([CAMPAIGN_TITLE], [campaign.campaign_title for campaign in repository.campaigns])
        self.assertEqual(len(RESOURCE_FIXTURES), len(service.resources))
        self.assertEqual(2, len(service.requirements))
        self.assertEqual(2, len(service.launches))
        self.assertEqual(4, len(service.creators))
        self.assertEqual("Not Ready", second.ready_to_close)

    def test_cleanup_soft_deactivates_only_validation_fixture_records(self) -> None:
        repository = FakeRepository()
        service = FakeService(repository)
        create_fixture(service, repository)
        service.resources.append(SimpleNamespace(id="resource-real", program_id="other", title="Real", resource_type="Custom", url="https://example.com/real", notes=None, is_active=True))

        result = cleanup_fixture(service, repository)

        self.assertTrue(result.deactivated)
        self.assertFalse(repository.campaigns[0].is_active)
        self.assertTrue(all(not item.is_active for item in service.resources if item.program_id == repository.programs[0].id))
        self.assertTrue(service._by_id(service.resources, "resource-real").is_active)
        self.assertTrue(all(not item.is_active for item in service.requirements))
        self.assertTrue(all(not item.is_active for item in service.launches))


if __name__ == "__main__":
    unittest.main()
