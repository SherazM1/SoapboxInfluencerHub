from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from core.campaign_ops.db import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS,
    DEFAULT_STATEMENT_TIMEOUT_MS,
    connect_to_campaign_ops_database,
)
from core.campaign_ops.performance import campaign_ops_query_counter
from core.campaign_ops.repository import DEFAULT_ACTIVITY_LIMIT, DEFAULT_NOTE_LIMIT, CampaignOpsRepository


class FakeCursor:
    def __init__(self, rows: list[dict[str, object]] | None = None, fail: bool = False) -> None:
        self.rows = rows or []
        self.fail = fail
        self.rowcount = len(self.rows)
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        if self.fail:
            raise RuntimeError("controlled failure")
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, object]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor | None = None) -> None:
        self.cursor_obj = cursor or FakeCursor()
        self.closed = False
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def close(self) -> None:
        self.closed = True

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class CampaignOpsPerformanceTests(unittest.TestCase):
    def test_connection_uses_campaign_ops_timeouts_and_application_name(self) -> None:
        fake_psycopg = Mock()
        fake_psycopg.connect.return_value = object()
        with patch("core.campaign_ops.db.get_campaign_ops_database_url", return_value="postgresql://ops"):
            with patch("core.campaign_ops.db.psycopg", fake_psycopg):
                with patch("core.campaign_ops.db.dict_row", object()):
                    connect_to_campaign_ops_database()
        _args, kwargs = fake_psycopg.connect.call_args
        self.assertEqual(DEFAULT_CONNECT_TIMEOUT_SECONDS, kwargs["connect_timeout"])
        self.assertEqual("kkg_influencerhub_campaign_ops", kwargs["application_name"])
        self.assertIn(f"statement_timeout={DEFAULT_STATEMENT_TIMEOUT_MS}", kwargs["options"])
        self.assertIn(
            f"idle_in_transaction_session_timeout={DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS}",
            kwargs["options"],
        )

    def test_repository_closes_owned_connection_after_successful_read(self) -> None:
        connection = FakeConnection(FakeCursor([{"id": "u1", "display_name": "Bailey", "role": "administrator", "is_active": True}]))
        with patch("core.campaign_ops.repository.connect_to_database", return_value=connection):
            user = CampaignOpsRepository().get_user_by_display_name("Bailey")
        self.assertEqual("Bailey", user.display_name)
        self.assertTrue(connection.closed)

    def test_repository_closes_owned_connection_after_exception(self) -> None:
        connection = FakeConnection(FakeCursor(fail=True))
        with patch("core.campaign_ops.repository.connect_to_database", return_value=connection):
            with self.assertRaises(Exception):
                CampaignOpsRepository().get_user_by_display_name("Bailey")
        self.assertTrue(connection.closed)

    def test_repository_rolls_back_owned_write_after_failure(self) -> None:
        connection = FakeConnection(FakeCursor(fail=True))
        with patch("core.campaign_ops.repository.connect_to_database", return_value=connection):
            with self.assertRaises(Exception):
                CampaignOpsRepository().create_client("TEST - failure")
        self.assertTrue(connection.rolled_back)
        self.assertTrue(connection.closed)

    def test_query_counter_counts_execute_once_and_rows_separately(self) -> None:
        rows = [
            {"id": "u1", "display_name": "Bailey", "role": "administrator", "is_active": True},
            {"id": "u2", "display_name": "T", "role": "team_member", "is_active": True},
        ]
        repository = CampaignOpsRepository(connection=FakeConnection(FakeCursor(rows)))
        with campaign_ops_query_counter("list_active_users") as stats:
            repository.list_active_users()
        self.assertEqual(1, stats.query_count)
        self.assertEqual(2, stats.row_count)

    def test_note_and_activity_defaults_are_bounded(self) -> None:
        self.assertEqual(100, DEFAULT_NOTE_LIMIT)
        self.assertEqual(100, DEFAULT_ACTIVITY_LIMIT)
