from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.pages.campaigns import viewer_can_initialize_in_setup
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
    CampaignOpsSetupRequiredError,
    CampaignOpsValidationError,
)
from core.campaign_ops.migrations import get_migration_names, run_campaign_ops_migrations
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
        if normalized.startswith("select version from schema_migrations"):
            self.rows = [{"version": version} for version in self.connection.applied_versions]
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

    def test_service_create_program_appends_activity(self) -> None:
        repository = FakeRepository()
        service = CampaignOpsService(repository=repository)
        program = service.create_program(actor_user_id="u1", program_name="Program")

        self.assertEqual(program.program_name, "Program")
        self.assertEqual(len(repository.events), 1)
        self.assertEqual(repository.events[0]["event_type"], "program_created")


if __name__ == "__main__":
    unittest.main()
