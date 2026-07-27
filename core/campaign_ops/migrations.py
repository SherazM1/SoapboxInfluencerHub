from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any

from core.campaign_ops.db import (
    CAMPAIGN_OPS_DATABASE_ENV_VAR,
    campaign_ops_schema_is_initialized,
    connect_to_campaign_ops_database,
    get_campaign_ops_database_url,
    psycopg,
    dict_row,
)
from core.campaign_ops.exceptions import CampaignOpsDatabaseError
from core.campaign_ops.seed_data import get_seed_users

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Summary of a Campaign Operations migration run."""

    applied_migrations: list[str]
    skipped_migrations: list[str]


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Summary of Campaign Operations seed execution."""

    verified_users: list[str]

    @property
    def seeded_users(self) -> list[str]:
        """Backward-compatible display name for verified seeded users."""
        return self.verified_users


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


def log_safe_database_error(
    stage: str,
    exc: BaseException,
    migration_name: str | None = None,
) -> None:
    """Log safe migration diagnostics without credentials."""
    diagnostic = getattr(exc, "diag", None)
    LOGGER.exception(
        "Campaign Operations initialization failed",
        extra={
            "stage": stage,
            "migration": migration_name,
            "exception_type": type(exc).__name__,
            "sqlstate": getattr(exc, "sqlstate", None),
            "constraint_name": getattr(diagnostic, "constraint_name", None),
            "safe_message": str(exc),
        },
    )


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
        connection.commit()
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
                log_safe_database_error("migration", exc, migration_name)
                raise CampaignOpsDatabaseError(
                    f"Campaign Operations migration failed: {migration_name}"
                ) from exc
        return MigrationResult(applied_migrations=applied, skipped_migrations=skipped)
    finally:
        connection.close()


def seed_campaign_ops_users() -> SeedResult:
    """Verify SQL migrations seeded required Campaign Operations users."""
    return verify_campaign_ops_seed_users()


def verify_campaign_ops_seed_users() -> SeedResult:
    """Verify required Campaign Operations users exist with exact role values."""
    connection = connect_to_database()
    users = get_seed_users()
    try:
        expected = {user.display_name: user.role.value for user in users}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select display_name, role
                from campaign_ops_users
                where display_name = any(%s) and is_active = true
                order by display_name
                """,
                (list(expected),),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        present = {str(row["display_name"]): str(row["role"]) for row in rows}
        missing = sorted(set(expected) - set(present))
        wrong_roles = sorted(
            display_name
            for display_name, role in present.items()
            if expected.get(display_name) != role
        )
        if missing or wrong_roles:
            details = []
            if missing:
                details.append("missing users: " + ", ".join(missing))
            if wrong_roles:
                details.append("incorrect roles: " + ", ".join(wrong_roles))
            raise CampaignOpsDatabaseError("; ".join(details))
        return SeedResult(verified_users=[user.display_name for user in users])
    except CampaignOpsDatabaseError as exc:
        log_safe_database_error("seed_verification", exc)
        raise CampaignOpsDatabaseError("Campaign Operations user seed verification failed.") from exc
    except Exception as exc:
        log_safe_database_error("seed_verification", exc)
        raise CampaignOpsDatabaseError("Campaign Operations user seed verification failed.") from exc
    finally:
        connection.close()


def verify_campaign_ops_initialization() -> None:
    """Verify required schema and seeded users exist after initialization."""
    connection = connect_to_database()
    try:
        if not campaign_ops_schema_is_initialized(connection):
            raise CampaignOpsDatabaseError("Campaign Operations schema verification failed.")
        expected_names = {user.display_name for user in get_seed_users()}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select display_name
                from campaign_ops_users
                where display_name = any(%s) and is_active = true
                """,
                (list(expected_names),),
            )
            present_names = {str(row["display_name"]) for row in cursor.fetchall()}
        missing_names = sorted(expected_names - present_names)
        if missing_names:
            raise CampaignOpsDatabaseError(
                "Campaign Operations seed verification failed for: "
                + ", ".join(missing_names)
            )
    except CampaignOpsDatabaseError:
        raise
    except Exception as exc:
        raise CampaignOpsDatabaseError(
            "Campaign Operations initialization verification failed."
        ) from exc
    finally:
        connection.close()


def initialize_campaign_ops_database() -> CampaignOpsInitializationResult:
    """Run migrations and seed required Campaign Operations users."""
    migration_result = run_campaign_ops_migrations()
    seed_result = verify_campaign_ops_seed_users()
    verify_campaign_ops_initialization()
    return CampaignOpsInitializationResult(migrations=migration_result, seed=seed_result)
