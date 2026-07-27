from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.pages import campaigns
from app.pages.campaigns import (
    format_initialization_result,
    render_initialization_control,
    viewer_can_initialize_in_setup,
)
from core.campaign_ops.db import (
    CampaignOpsSetupStatus,
    get_campaign_ops_database_url,
    get_campaign_ops_setup_status,
)
from core.campaign_ops.enums import (
    ProgramStatus,
    TaskStatus,
    UserRole,
    WorkstreamType,
)
from core.campaign_ops.exceptions import (
    CampaignOpsDatabaseError,
    CampaignOpsSetupRequiredError,
    CampaignOpsValidationError,
)
from core.campaign_ops.migrations import (
    CampaignOpsInitializationResult,
    MigrationResult,
    SeedResult,
    get_migration_names,
    initialize_campaign_ops_database,
    run_campaign_ops_migrations,
    verify_campaign_ops_seed_users,
)
from core.campaign_ops.models import (
    CampaignOpsUser,
    Program,
    ProgramAssignment,
    Task,
    TaskDependency,
)
from core.campaign_ops.permissions import (
    can_access_admin,
    can_archive_program,
    can_edit_program,
    can_view_program,
)
from core.campaign_ops.seed_data import get_seed_users
from core.campaign_ops.service import CampaignOpsService
from core.campaign_ops.repository import CampaignOpsRepository


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.rows: list[dict[str, str]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[str, ...] | None = None) -> None:
        normalized = " ".join(query.lower().split())
        if "raise failure" in normalized:
            raise RuntimeError("migration failed")
        if normalized.startswith("select version from schema_migrations"):
            self.rows = [{"version": version} for version in self.connection.applied_versions]
            return
        if normalized.startswith("select display_name, role from campaign_ops_users"):
            requested = set(params[0]) if params else set()
            self.rows = [
                {"display_name": user["display_name"], "role": user["role"]}
                for user in self.connection.users
                if user["display_name"] in requested and user.get("is_active", True)
            ]
            return
        if normalized.startswith("insert into schema_migrations") and params:
            self.connection.applied_versions.add(params[0])
            return
        if normalized.startswith("create table if not exists schema_migrations"):
            self.connection.bookkeeping_created = True
            return
        self.connection.executed_sql.append(query)

    def fetchall(self) -> list[dict[str, str]]:
        return self.rows

    def fetchone(self) -> dict[str, str] | None:
        return self.rows[0] if self.rows else None


class FakeTransaction:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "FakeTransaction":
        self.connection.transaction_count += 1
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.applied_versions: set[str] = set()
        self.executed_sql: list[str] = []
        self.bookkeeping_created = False
        self.commit_count = 0
        self.closed = False
        self.transaction_count = 0
        self.users: list[dict[str, str | bool]] = [
            {"display_name": "Bailey", "role": "administrator", "is_active": True},
            {"display_name": "T", "role": "team_member", "is_active": True},
            {"display_name": "L", "role": "team_member", "is_active": True},
        ]

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def commit(self) -> None:
        self.commit_count += 1

    def close(self) -> None:
        self.closed = True


class MissingTableCursor:
    def __enter__(self) -> "MissingTableCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _query: str, _params: tuple[str, ...] | None = None) -> None:
        raise RuntimeError("undefined table")


class MissingTableConnection:
    def cursor(self) -> MissingTableCursor:
        return MissingTableCursor()

    def close(self) -> None:
        return None


class FakeRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def create_program(self, program_name: str, actor_user_id: str | None = None, **_kwargs: object) -> Program:
        return Program(
            id="program-1",
            program_name=program_name,
            created_by=actor_user_id,
            updated_by=actor_user_id,
        )

    def append_event(self, **kwargs: str) -> None:
        self.events.append(kwargs)


class CampaignOpsFoundationTests(unittest.TestCase):
    def test_enum_values_are_stable_storage_values(self) -> None:
        self.assertEqual(UserRole.ADMINISTRATOR.value, "administrator")
        self.assertEqual(ProgramStatus.ACTIVE.value, "active")
        self.assertEqual(WorkstreamType.RETAIL_MEDIA.value, "retail_media")
        self.assertEqual(TaskStatus.WAITING_ON_CLIENT.value, "waiting_on_client")

    def test_seed_users_are_exact_and_idempotent_definitions(self) -> None:
        users = get_seed_users()
        self.assertEqual([user.display_name for user in users], ["Bailey", "T", "L"])
        self.assertEqual([user.email for user in users], [None, None, None])
        self.assertEqual([user.role.value for user in users], ["administrator", "team_member", "team_member"])
        self.assertEqual(len({user.id for user in users}), 3)

    def test_seed_sql_uses_authoritative_enum_values_and_display_names(self) -> None:
        seed_sql = Path("db/migrations/002_campaign_ops_seed_users.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("'Bailey'", seed_sql)
        self.assertIn("'T'", seed_sql)
        self.assertIn("'L'", seed_sql)
        self.assertIn(f"'{UserRole.ADMINISTRATOR.value}'", seed_sql)
        self.assertIn(f"'{UserRole.TEAM_MEMBER.value}'", seed_sql)
        self.assertIn("lower(existing.display_name) = lower(seed_users.display_name)", seed_sql)

    def test_campaign_ops_database_url_is_isolated_from_database_url(self) -> None:
        with patch("core.campaign_ops.db.load_local_env", return_value=True):
            with patch.dict(
                "os.environ",
                {
                    "DATABASE_URL": "postgresql://historical",
                    "CAMPAIGN_OPS_DATABASE_URL": "postgresql://campaign-ops",
                },
                clear=True,
            ):
                self.assertEqual(
                    get_campaign_ops_database_url(),
                    "postgresql://campaign-ops",
                )

            with patch.dict(
                "os.environ",
                {"DATABASE_URL": "postgresql://historical"},
                clear=True,
            ):
                self.assertIsNone(get_campaign_ops_database_url())

    def test_reachable_database_missing_users_table_is_uninitialized(self) -> None:
        fake_connection = FakeConnection()
        with patch("core.campaign_ops.db.get_campaign_ops_database_url", return_value="postgresql://ops"):
            with patch("core.campaign_ops.db.psycopg", object()):
                with patch("core.campaign_ops.db.dict_row", object()):
                    with patch("core.campaign_ops.db.connect_to_campaign_ops_database", return_value=fake_connection):
                        with patch(
                            "core.campaign_ops.db.table_exists",
                            side_effect=lambda _conn, table_name: table_name == "schema_migrations",
                        ):
                            status = get_campaign_ops_setup_status()

        self.assertEqual(status.state, "uninitialized")
        self.assertTrue(status.connection_succeeded)
        self.assertFalse(status.schema_initialized)

    def test_initialized_status_requires_metadata_tables(self) -> None:
        fake_connection = FakeConnection()
        with patch("core.campaign_ops.db.get_campaign_ops_database_url", return_value="postgresql://ops"):
            with patch("core.campaign_ops.db.psycopg", object()):
                with patch("core.campaign_ops.db.dict_row", object()):
                    with patch("core.campaign_ops.db.connect_to_campaign_ops_database", return_value=fake_connection):
                        with patch("core.campaign_ops.db.table_exists", return_value=True):
                            status = get_campaign_ops_setup_status()

        self.assertEqual(status.state, "initialized")
        self.assertTrue(status.schema_initialized)

    def test_repository_converts_undefined_table_to_setup_error(self) -> None:
        repository = CampaignOpsRepository(connection=MissingTableConnection())
        with patch("core.campaign_ops.repository.is_undefined_table_error", return_value=True):
            with self.assertRaises(CampaignOpsSetupRequiredError):
                repository.get_user_by_display_name("Bailey")

    def test_temporary_setup_admin_is_bailey_only(self) -> None:
        self.assertTrue(viewer_can_initialize_in_setup("Bailey"))
        self.assertFalse(viewer_can_initialize_in_setup("T"))
        self.assertFalse(viewer_can_initialize_in_setup("L"))

    def test_uninitialized_status_prevents_viewer_repository_lookup(self) -> None:
        status = CampaignOpsSetupStatus(
            state="uninitialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=False,
            message="Not initialized.",
        )
        with patch("app.pages.campaigns.render_header"):
            with patch("app.pages.campaigns.hide_default_streamlit_sidebar_nav"):
                with patch("app.pages.campaigns.clear_legacy_workflow_session_state"):
                    with patch("app.pages.campaigns.render_initialization_message"):
                        with patch("app.pages.campaigns.render_temporary_viewer_selector", return_value=("Bailey", "Cross-Team Dashboard")):
                            with patch("app.pages.campaigns.get_campaign_ops_setup_status", return_value=status):
                                with patch("app.pages.campaigns.render_setup_state", side_effect=StopIteration):
                                    with patch("app.pages.campaigns.resolve_viewer_user") as resolve_viewer:
                                        with patch("app.pages.campaigns.st.set_page_config"):
                                            with patch("app.pages.campaigns.st.divider"):
                                                with self.assertRaises(StopIteration):
                                                    __import__(
                                                        "app.pages.campaigns",
                                                        fromlist=["main"],
                                                    ).main()
        resolve_viewer.assert_not_called()

    def test_permissions_by_role(self) -> None:
        admin = CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value)
        member = CampaignOpsUser(id="u2", display_name="T", role=UserRole.TEAM_MEMBER.value)
        viewer = CampaignOpsUser(id="u3", display_name="Reader", role=UserRole.VIEWER.value)
        program = Program(id="p1", program_name="Program")

        self.assertTrue(can_access_admin(admin))
        self.assertTrue(can_archive_program(admin))
        self.assertTrue(can_view_program(admin, program, []))
        self.assertFalse(can_access_admin(member))
        self.assertFalse(can_archive_program(member))
        self.assertFalse(can_view_program(member, program, []))
        self.assertTrue(can_view_program(viewer, program, [], explicit_program_ids={"p1"}))

    def test_program_owner_can_edit_program(self) -> None:
        member = CampaignOpsUser(id="u2", display_name="T", role=UserRole.TEAM_MEMBER.value)
        program = Program(id="p1", program_name="Program")
        assignment = ProgramAssignment(
            id="a1",
            program_id="p1",
            user_id="u2",
            assignment_role="program_owner",
        )
        self.assertTrue(can_edit_program(member, program, [assignment]))

    def test_models_validate_required_fields_and_enums(self) -> None:
        with self.assertRaises(CampaignOpsValidationError):
            Program(id="p1", program_name="")
        with self.assertRaises(CampaignOpsValidationError):
            Task(id="t1", program_id="p1", title="Task", status="bad_status")
        with self.assertRaises(CampaignOpsValidationError):
            TaskDependency(id="d1", task_id="t1", depends_on_task_id="t1")

    def test_migration_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "002_second.sql").write_text("select 2;", encoding="utf-8")
            (root / "001_first.sql").write_text("select 1;", encoding="utf-8")
            self.assertEqual(get_migration_names(root), ["001_first.sql", "002_second.sql"])

    def test_migration_bookkeeping_prevents_reapply(self) -> None:
        fake_connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "001_first.sql").write_text("select 1;", encoding="utf-8")
            (root / "002_second.sql").write_text("select 2;", encoding="utf-8")

            with patch(
                "core.campaign_ops.migrations.connect_to_database",
                return_value=fake_connection,
            ):
                first = run_campaign_ops_migrations(root)
                second = run_campaign_ops_migrations(root)

        self.assertTrue(fake_connection.bookkeeping_created)
        self.assertEqual(first.applied_migrations, ["001_first.sql", "002_second.sql"])
        self.assertEqual(second.skipped_migrations, ["001_first.sql", "002_second.sql"])
        self.assertEqual(fake_connection.transaction_count, 2)
        self.assertGreaterEqual(fake_connection.commit_count, 2)

    def test_migration_001_applied_with_002_pending_retries_only_002(self) -> None:
        fake_connection = FakeConnection()
        fake_connection.applied_versions.add("001_first.sql")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "001_first.sql").write_text("select 1;", encoding="utf-8")
            (root / "002_second.sql").write_text("select 2;", encoding="utf-8")

            with patch(
                "core.campaign_ops.migrations.connect_to_database",
                return_value=fake_connection,
            ):
                result = run_campaign_ops_migrations(root)

        self.assertEqual(result.skipped_migrations, ["001_first.sql"])
        self.assertEqual(result.applied_migrations, ["002_second.sql"])

    def test_failed_migration_is_not_recorded_and_remains_retryable(self) -> None:
        fake_connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "001_bad.sql").write_text("raise failure;", encoding="utf-8")

            with patch(
                "core.campaign_ops.migrations.connect_to_database",
                return_value=fake_connection,
            ):
                with patch("core.campaign_ops.migrations.LOGGER.exception"):
                    with self.assertRaises(CampaignOpsDatabaseError):
                        run_campaign_ops_migrations(root)

        self.assertNotIn("001_bad.sql", fake_connection.applied_versions)

    def test_seed_verification_succeeds_without_writing_duplicates(self) -> None:
        fake_connection = FakeConnection()
        with patch(
            "core.campaign_ops.migrations.connect_to_database",
            return_value=fake_connection,
        ):
            first = verify_campaign_ops_seed_users()
            second = verify_campaign_ops_seed_users()

        self.assertEqual(first.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(second.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(len(fake_connection.users), 3)

    def test_seed_verification_failure_is_wrapped_safely(self) -> None:
        fake_connection = FakeConnection()
        fake_connection.users = [
            {"display_name": "Bailey", "role": "administrator", "is_active": True},
        ]
        with patch(
            "core.campaign_ops.migrations.connect_to_database",
            return_value=fake_connection,
        ):
            with patch("core.campaign_ops.migrations.LOGGER.exception"):
                with self.assertRaisesRegex(
                    CampaignOpsDatabaseError,
                    "Campaign Operations user seed verification failed.",
                ):
                    verify_campaign_ops_seed_users()

    def test_initialization_result_reports_applied_skipped_and_verified_users(self) -> None:
        with patch(
            "core.campaign_ops.migrations.run_campaign_ops_migrations",
            return_value=MigrationResult(["001.sql"], ["002.sql"]),
        ):
            with patch("core.campaign_ops.migrations.verify_campaign_ops_initialization"):
                with patch(
                    "core.campaign_ops.migrations.verify_campaign_ops_seed_users"
                ) as verify_seed:
                    verify_seed.return_value.verified_users = ["Bailey", "T", "L"]
                    verify_seed.return_value.seeded_users = ["Bailey", "T", "L"]
                    result = initialize_campaign_ops_database()

        self.assertEqual(result.migrations.applied_migrations, ["001.sql"])
        self.assertEqual(result.migrations.skipped_migrations, ["002.sql"])
        self.assertEqual(result.seed.verified_users, ["Bailey", "T", "L"])

    def test_initialization_display_summary_with_applied_migrations(self) -> None:
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult(["001.sql"], ["002.sql"]),
            seed=SeedResult(["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.applied_migrations, ["001.sql"])
        self.assertEqual(summary.skipped_migrations, ["002.sql"])
        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(
            summary.initialized_status,
            "Campaign Operations database is initialized.",
        )

    def test_initialization_display_summary_with_only_skipped_migrations(self) -> None:
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult([], ["001.sql", "002.sql"]),
            seed=SeedResult(["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.applied_migrations, [])
        self.assertEqual(summary.skipped_migrations, ["001.sql", "002.sql"])
        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])

    def test_initialization_display_summary_accepts_direct_seeded_users(self) -> None:
        result = SimpleNamespace(
            applied_migrations=["001.sql"],
            skipped_migrations=[],
            seeded_users=["Bailey", "T", "L"],
            status="Campaign Operations database is initialized.",
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.seeded_users, ["Bailey", "T", "L"])
        self.assertEqual(summary.verified_users, [])

    def test_initialization_display_summary_reads_verified_users_from_seed_model(self) -> None:
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult([], []),
            seed=SeedResult(["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(result)

        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])

    def test_initialization_display_summary_handles_missing_optional_fields(self) -> None:
        summary = format_initialization_result({})

        self.assertEqual(summary.applied_migrations, [])
        self.assertEqual(summary.skipped_migrations, [])
        self.assertEqual(summary.seeded_users, [])
        self.assertEqual(summary.verified_users, [])
        self.assertEqual(
            summary.initialized_status,
            "Campaign Operations database is initialized.",
        )

    def test_initialization_success_formatting_does_not_raise_attribute_error(self) -> None:
        old_result = SimpleNamespace(
            migrations=SimpleNamespace(applied_migrations=[], skipped_migrations=["001.sql"]),
            seed=SimpleNamespace(seeded_users=["Bailey", "T", "L"]),
        )

        summary = format_initialization_result(old_result)

        self.assertEqual(summary.seeded_users, ["Bailey", "T", "L"])
        self.assertEqual(summary.verified_users, [])

    def test_already_initialized_database_path_loads_workspace(self) -> None:
        status = CampaignOpsSetupStatus(
            state="initialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=True,
            message="Campaign Operations database is initialized.",
        )
        with patch("app.pages.campaigns.render_header"):
            with patch("app.pages.campaigns.hide_default_streamlit_sidebar_nav"):
                with patch("app.pages.campaigns.clear_legacy_workflow_session_state"):
                    with patch("app.pages.campaigns.render_initialization_message"):
                        with patch("app.pages.campaigns.render_temporary_viewer_selector", return_value=("Bailey", "Cross-Team Dashboard")):
                            with patch("app.pages.campaigns.get_campaign_ops_setup_status", return_value=status):
                                with patch("app.pages.campaigns.render_setup_state") as render_setup:
                                    with patch("app.pages.campaigns.resolve_initialized_viewer", return_value=CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value)) as resolve_viewer:
                                        with patch("app.pages.campaigns.render_initialization_control"):
                                            with patch("app.pages.campaigns.render_section_navigation", return_value="Cross-Team Dashboard"):
                                                with patch("app.pages.campaigns.render_active_section") as render_active:
                                                    with patch("app.pages.campaigns.st.set_page_config"):
                                                        with patch("app.pages.campaigns.st.divider"):
                                                            campaigns.main()

        render_setup.assert_not_called()
        resolve_viewer.assert_called_once_with("Bailey")
        render_active.assert_called_once_with("Bailey", "Cross-Team Dashboard")

    def test_initialized_seeded_users_resolve_to_expected_roles(self) -> None:
        users = [
            CampaignOpsUser(id="u1", display_name="Bailey", role=UserRole.ADMINISTRATOR.value),
            CampaignOpsUser(id="u2", display_name="T", role=UserRole.TEAM_MEMBER.value),
            CampaignOpsUser(id="u3", display_name="L", role=UserRole.TEAM_MEMBER.value),
        ]

        self.assertEqual(
            [campaigns.get_viewer_role(user.display_name, user) for user in users],
            ["Administrator", "Team Member", "Team Member"],
        )

    def test_successful_initialization_stores_summary_and_triggers_rerun(self) -> None:
        status = CampaignOpsSetupStatus(
            state="initialized",
            database_url_detected=True,
            driver_available=True,
            connection_succeeded=True,
            schema_initialized=True,
            message="Campaign Operations database is initialized.",
        )
        result = CampaignOpsInitializationResult(
            migrations=MigrationResult([], ["001.sql", "002.sql"]),
            seed=SeedResult(["Bailey", "T", "L"]),
        )
        session_state: dict[str, object] = {
            "campaign_ops_initialization_error": "old error",
            "campaign_ops_initialization_result": "old result",
            "campaign_ops_viewer_id": "old-user",
        }

        with patch.object(campaigns.st, "session_state", session_state):
            with patch("app.pages.campaigns.st.expander"):
                with patch("app.pages.campaigns.st.caption"):
                    with patch("app.pages.campaigns.st.button", return_value=True):
                        with patch(
                            "app.pages.campaigns.initialize_campaign_ops_database",
                            return_value=result,
                        ):
                            with patch(
                                "app.pages.campaigns.st.rerun",
                                side_effect=RuntimeError("rerun"),
                            ):
                                with self.assertRaisesRegex(RuntimeError, "rerun"):
                                    render_initialization_control(
                                        "Bailey",
                                        CampaignOpsUser(
                                            id="u1",
                                            display_name="Bailey",
                                            role=UserRole.ADMINISTRATOR.value,
                                        ),
                                        status,
                                    )

        self.assertNotIn("campaign_ops_initialization_error", session_state)
        self.assertNotIn("campaign_ops_initialization_result", session_state)
        self.assertNotIn("campaign_ops_viewer_id", session_state)
        summary = session_state["campaign_ops_initialization_message"]
        self.assertEqual(summary.verified_users, ["Bailey", "T", "L"])
        self.assertEqual(summary.skipped_migrations, ["001.sql", "002.sql"])

    def test_service_create_program_appends_activity(self) -> None:
        repository = FakeRepository()
        service = CampaignOpsService(repository=repository)
        program = service.create_program(actor_user_id="u1", program_name="Program")

        self.assertEqual(program.program_name, "Program")
        self.assertEqual(len(repository.events), 1)
        self.assertEqual(repository.events[0]["event_type"], "program_created")


if __name__ == "__main__":
    unittest.main()
