from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.campaign_ops.db import (
    CAMPAIGN_OPS_DATABASE_ENV_VAR,
    connect_to_campaign_ops_database,
    get_campaign_ops_database_url,
    psycopg,
    dict_row,
)
from core.campaign_ops.exceptions import CampaignOpsDatabaseError
from core.campaign_ops.seed_data import get_seed_users

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Summary of a Campaign Operations migration run."""

    applied_migrations: list[str]
    skipped_migrations: list[str]


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Summary of Campaign Operations seed execution."""

    seeded_users: list[str]


@dataclass(frozen=True, slots=True)
class CampaignOpsInitializationResult:
    """Summary of full Campaign Operations initialization."""

    migrations: MigrationResult
    seed: SeedResult


def list_migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    """Return Campaign Operations migration files in deterministic order."""
    if not migrations_dir.exists():
        raise CampaignOpsDatabaseError("Campaign Operations migrations directory is missing.")
    return sorted(migrations_dir.glob("*.sql"), key=lambda path: path.name)


def get_migration_names(migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Return ordered Campaign Operations migration filenames."""
    return [path.name for path in list_migration_files(migrations_dir)]


def get_required_database_url() -> str:
    """Return a configured database URL or raise a safe domain error."""
    database_url = get_campaign_ops_database_url()
    if not database_url:
        raise CampaignOpsDatabaseError(f"{CAMPAIGN_OPS_DATABASE_ENV_VAR} is not configured.")
    if psycopg is None or dict_row is None:
        raise CampaignOpsDatabaseError("PostgreSQL driver is not installed.")
    return database_url


def connect_to_database() -> Any:
    """Open a Postgres connection for Campaign Operations."""
    return connect_to_campaign_ops_database()


def ensure_schema_migrations_table(connection: Any) -> None:
    """Create migration bookkeeping table if needed."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            create table if not exists schema_migrations (
                version text primary key,
                applied_at timestamptz not null default now()
            )
            """
        )


def fetch_applied_migrations(connection: Any) -> set[str]:
    """Fetch already-applied migration filenames."""
    with connection.cursor() as cursor:
        cursor.execute("select version from schema_migrations")
        return {str(row["version"]) for row in cursor.fetchall()}


def record_migration(connection: Any, migration_name: str) -> None:
    """Record a completed migration."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            insert into schema_migrations (version)
            values (%s)
            on conflict (version) do nothing
            """,
            (migration_name,),
        )


def run_campaign_ops_migrations(
    migrations_dir: Path = MIGRATIONS_DIR,
) -> MigrationResult:
    """Apply pending Campaign Operations migrations transactionally."""
    migration_files = list_migration_files(migrations_dir)
    connection = connect_to_database()
    applied: list[str] = []
    skipped: list[str] = []
    try:
        ensure_schema_migrations_table(connection)
        connection.commit()
        completed = fetch_applied_migrations(connection)
        for migration_file in migration_files:
            migration_name = migration_file.name
            if migration_name in completed:
                skipped.append(migration_name)
                continue
            try:
                with connection.transaction():
                    with connection.cursor() as cursor:
                        cursor.execute(migration_file.read_text(encoding="utf-8"))
                    record_migration(connection, migration_name)
                applied.append(migration_name)
            except Exception as exc:
                raise CampaignOpsDatabaseError(
                    f"Campaign Operations migration failed: {migration_name}"
                ) from exc
        return MigrationResult(applied_migrations=applied, skipped_migrations=skipped)
    finally:
        connection.close()


def seed_campaign_ops_users() -> SeedResult:
    """Seed initial Campaign Operations users idempotently."""
    connection = connect_to_database()
    users = get_seed_users()
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                for user in users:
                    cursor.execute(
                        """
                        insert into campaign_ops_users (id, display_name, email, role, is_active)
                        values (%s, %s, %s, %s, true)
                        on conflict (id) do update set
                            display_name = excluded.display_name,
                            email = excluded.email,
                            role = excluded.role,
                            is_active = excluded.is_active
                        """,
                        (user.id, user.display_name, user.email, user.role.value),
                    )
        return SeedResult(seeded_users=[user.display_name for user in users])
    except Exception as exc:
        raise CampaignOpsDatabaseError("Campaign Operations user seeding failed.") from exc
    finally:
        connection.close()


def initialize_campaign_ops_database() -> CampaignOpsInitializationResult:
    """Run migrations and seed required Campaign Operations users."""
    migration_result = run_campaign_ops_migrations()
    seed_result = seed_campaign_ops_users()
    return CampaignOpsInitializationResult(migrations=migration_result, seed=seed_result)
