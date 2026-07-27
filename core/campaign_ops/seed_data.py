from __future__ import annotations

from dataclasses import dataclass

from core.campaign_ops.enums import UserRole

BAILEY_USER_ID = "11111111-1111-4111-8111-111111111111"
T_USER_ID = "22222222-2222-4222-8222-222222222222"
L_USER_ID = "33333333-3333-4333-8333-333333333333"


@dataclass(frozen=True, slots=True)
class SeedUser:
    """Idempotent Campaign Operations user seed definition."""

    id: str
    display_name: str
    role: UserRole
    email: str | None = None


SEED_USERS = [
    SeedUser(id=BAILEY_USER_ID, display_name="Bailey", role=UserRole.ADMINISTRATOR),
    SeedUser(id=T_USER_ID, display_name="T", role=UserRole.TEAM_MEMBER),
    SeedUser(id=L_USER_ID, display_name="L", role=UserRole.TEAM_MEMBER),
]


def get_seed_users() -> list[SeedUser]:
    """Return initial internal users without invented names or emails."""
    return list(SEED_USERS)
