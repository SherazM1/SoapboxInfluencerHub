from __future__ import annotations

import sqlite3
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DB_PATH = Path(__file__).resolve().parents[1] / "data" / "campaign_reports.sqlite3"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY,
                report_id TEXT UNIQUE NOT NULL,
                client_name TEXT NOT NULL,
                report_date TEXT NOT NULL,
                organic_impressions INTEGER NOT NULL DEFAULT 0,
                paid_impressions INTEGER NOT NULL DEFAULT 0,
                organic_engagements INTEGER NOT NULL DEFAULT 0,
                paid_engagements INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_report_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_content_items (
                id INTEGER PRIMARY KEY,
                report_id TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT '',
                creator_handle TEXT NOT NULL DEFAULT '',
                content_title TEXT NOT NULL DEFAULT '',
                content_description TEXT NOT NULL DEFAULT '',
                live_url TEXT NOT NULL,
                image_url TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (report_id) REFERENCES reports(report_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_report_content_items_report_id
            ON report_content_items(report_id)
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_slug
            ON reports(slug)
            WHERE slug IS NOT NULL
            """
        )
        ensure_content_item_columns(conn)


def ensure_report_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]: row for row in conn.execute("PRAGMA table_info(reports)").fetchall()
    }
    if "slug" not in columns:
        conn.execute("ALTER TABLE reports ADD COLUMN slug TEXT")


def ensure_content_item_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(report_content_items)").fetchall()
    }
    optional_columns = {
        "creator_handle": "TEXT NOT NULL DEFAULT ''",
        "content_title": "TEXT NOT NULL DEFAULT ''",
        "content_description": "TEXT NOT NULL DEFAULT ''",
        "image_path": "TEXT",
        "uploaded_image_path": "TEXT",
    }
    for column_name, column_type in optional_columns.items():
        if column_name not in columns:
            conn.execute(
                f"ALTER TABLE report_content_items ADD COLUMN {column_name} {column_type}"
            )


def generate_report_id() -> str:
    return f"rpt-{uuid.uuid4().hex[:10]}"


def slug_base(client_name: str, report_date: str) -> str:
    name = (client_name or "").lower()
    name = re.sub(r"['`]", "", name)
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-") or "report"
    if report_date:
        return f"{name}-{report_date}"
    return name


def generate_report_slug(
    conn: sqlite3.Connection, client_name: str, report_date: str
) -> str:
    base = slug_base(client_name, report_date)
    for _ in range(20):
        slug = f"{base}-{secrets.token_hex(2)}"
        exists = conn.execute(
            "SELECT 1 FROM reports WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not exists:
            return slug
    return f"{base}-{secrets.token_hex(3)}"


def list_reports() -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT report_id, slug, client_name, report_date, updated_at
            FROM reports
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_report(report_id: str) -> dict[str, Any] | None:
    return get_report_by_column("report_id", report_id)


def get_report_by_slug(slug: str) -> dict[str, Any] | None:
    return get_report_by_column("slug", slug)


def get_report_by_column(column_name: str, value: str) -> dict[str, Any] | None:
    if column_name not in {"report_id", "slug"}:
        raise ValueError("Unsupported report lookup column.")
    if not value:
        return None
    init_db()
    with get_connection() as conn:
        report = conn.execute(
            f"SELECT * FROM reports WHERE {column_name} = ?",
            (value,),
        ).fetchone()
        if report is None:
            return None
        items = conn.execute(
            """
            SELECT
                platform,
                live_url,
                image_url,
                image_path,
                uploaded_image_path,
                creator_handle,
                content_title,
                content_description,
                sort_order
            FROM report_content_items
            WHERE report_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (report["report_id"],),
        ).fetchall()
    data = dict(report)
    data["content_items"] = [dict(item) for item in items]
    return data


def save_report(report: dict[str, Any], content_items: list[dict[str, Any]]) -> str:
    init_db()
    report_id = report.get("report_id") or generate_report_id()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT created_at, slug FROM reports WHERE report_id = ?",
            (report_id,),
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        slug = existing["slug"] if existing and existing["slug"] else None
        if not slug:
            slug = generate_report_slug(
                conn, report.get("client_name", ""), report.get("report_date", "")
            )
        conn.execute(
            """
            INSERT INTO reports (
                report_id, slug, client_name, report_date, organic_impressions,
                paid_impressions, organic_engagements, paid_engagements,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_id) DO UPDATE SET
                slug = COALESCE(reports.slug, excluded.slug),
                client_name = excluded.client_name,
                report_date = excluded.report_date,
                organic_impressions = excluded.organic_impressions,
                paid_impressions = excluded.paid_impressions,
                organic_engagements = excluded.organic_engagements,
                paid_engagements = excluded.paid_engagements,
                updated_at = excluded.updated_at
            """,
            (
                report_id,
                slug,
                report["client_name"].strip(),
                report["report_date"],
                int(report["organic_impressions"]),
                int(report["paid_impressions"]),
                int(report["organic_engagements"]),
                int(report["paid_engagements"]),
                created_at,
                now,
            ),
        )
        conn.execute("DELETE FROM report_content_items WHERE report_id = ?", (report_id,))
        for index, item in enumerate(content_items):
            conn.execute(
                """
                INSERT INTO report_content_items (
                    report_id, platform, creator_handle, content_title,
                    content_description, live_url, image_url, image_path,
                    uploaded_image_path, sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    (item.get("platform") or "").strip(),
                    (item.get("creator_handle") or "").strip(),
                    (item.get("content_title") or "").strip(),
                    (item.get("content_description") or "").strip(),
                    item["live_url"].strip(),
                    (item.get("image_url") or "").strip() or None,
                    (item.get("image_path") or "").strip() or None,
                    (item.get("uploaded_image_path") or "").strip() or None,
                    index,
                ),
            )
    return report_id


def delete_report(report_id: str) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM report_content_items WHERE report_id = ?", (report_id,))
        conn.execute("DELETE FROM reports WHERE report_id = ?", (report_id,))
