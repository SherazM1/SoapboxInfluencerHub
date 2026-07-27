from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:
    from psycopg.types.json import Jsonb
except Exception:  # pragma: no cover
    Jsonb = None

from core.campaign_ops.enums import (
    AssignmentRole,
    CrossStage,
    ProgramStatus,
    RiskLevel,
    TaskStatus,
    WaitingOn,
    WorkstreamType,
)
from core.campaign_ops.db import is_undefined_table_error
from core.campaign_ops.exceptions import (
    CampaignOpsDatabaseError,
    CampaignOpsNotFoundError,
    CampaignOpsSetupRequiredError,
)
from core.campaign_ops.migrations import connect_to_database
from core.campaign_ops.models import (
    ActivityEvent,
    CampaignOpsUser,
    Client,
    Program,
    ProgramAssignment,
    ProgramPortfolioRow,
    ProgramNote,
    Resource,
    Task,
    Workstream,
    enum_value,
    require_text,
)


def jsonb_value(value: dict[str, Any] | None) -> Any:
    """Adapt a dictionary for jsonb writes."""
    data = value or {}
    return Jsonb(data) if Jsonb is not None else data


def normalize_id(value: Any) -> str | None:
    """Normalize DB UUID values to strings for models."""
    return str(value) if value is not None else None


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize UUID-like DB row values for model construction."""
    normalized = dict(row)
    for key, value in list(normalized.items()):
        if key.endswith("_id") or key in {"id", "created_by", "updated_by"}:
            normalized[key] = normalize_id(value)
    return normalized


def normalize_optional_list(value: Any) -> list[str]:
    """Normalize aggregate arrays from Postgres to string lists."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if isinstance(value, tuple):
        return [str(item) for item in value if item is not None]
    return [str(value)]


class CampaignOpsRepository:
    """Postgres repository for Campaign Operations records."""

    def __init__(self, connection: Any | None = None) -> None:
        self.connection = connection

    @contextmanager
    def connection_scope(self) -> Iterator[tuple[Any, bool]]:
        """Yield a database connection and whether this repository owns it."""
        if self.connection is not None:
            yield self.connection, False
            return
        connection = connect_to_database()
        try:
            yield connection, True
        finally:
            connection.close()

    def _fetch_one(
        self,
        query: str,
        params: tuple[Any, ...],
        model_type: type,
    ) -> Any | None:
        try:
            with self.connection_scope() as (connection, _owns_connection):
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
        except Exception as exc:
            if is_undefined_table_error(exc):
                raise CampaignOpsSetupRequiredError(
                    "Campaign Operations database schema is not initialized."
                ) from exc
            raise CampaignOpsDatabaseError("Campaign Operations query failed.") from exc
        return model_type(**normalize_row(row)) if row else None

    def _fetch_all(
        self,
        query: str,
        params: tuple[Any, ...],
        model_type: type,
    ) -> list[Any]:
        try:
            with self.connection_scope() as (connection, _owns_connection):
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
        except Exception as exc:
            if is_undefined_table_error(exc):
                raise CampaignOpsSetupRequiredError(
                    "Campaign Operations database schema is not initialized."
                ) from exc
            raise CampaignOpsDatabaseError("Campaign Operations query failed.") from exc
        return [model_type(**normalize_row(row)) for row in rows]

    def _fetch_raw_all(
        self,
        query: str,
        params: tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        try:
            with self.connection_scope() as (connection, _owns_connection):
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    rows = cursor.fetchall()
        except Exception as exc:
            if is_undefined_table_error(exc):
                raise CampaignOpsSetupRequiredError(
                    "Campaign Operations database schema is not initialized."
                ) from exc
            raise CampaignOpsDatabaseError("Campaign Operations query failed.") from exc
        return [dict(row) for row in rows]

    def _portfolio_row_from_db(self, row: dict[str, Any]) -> ProgramPortfolioRow:
        normalized = normalize_row(row)
        return ProgramPortfolioRow(
            id=str(normalized["id"]),
            program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"),
            primary_workstream_type=normalized.get("primary_workstream_type"),
            workstream_types=normalize_optional_list(normalized.get("workstream_types")),
            status=str(normalized["status"]),
            cross_stage=str(normalized["cross_stage"]),
            risk_level=str(normalized["risk_level"]),
            priority=normalized.get("priority"),
            primary_owner_user_id=normalize_id(normalized.get("primary_owner_user_id")),
            primary_owner_name=normalized.get("primary_owner_name"),
            assigned_user_ids=normalize_optional_list(normalized.get("assigned_user_ids")),
            assigned_user_names=normalize_optional_list(normalized.get("assigned_user_names")),
            start_date=normalized.get("start_date"),
            target_end_date=normalized.get("target_end_date"),
            updated_at=normalized.get("updated_at"),
            is_active=bool(normalized.get("is_active", True)),
            assignment_role=normalized.get("assignment_role"),
            assigned_workstream_type=normalized.get("assigned_workstream_type"),
        )

    def _write_returning(
        self,
        query: str,
        params: tuple[Any, ...],
        model_type: type,
    ) -> Any:
        with self.connection_scope() as (connection, owns_connection):
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                if owns_connection:
                    connection.commit()
            except Exception as exc:
                if owns_connection:
                    connection.rollback()
                if is_undefined_table_error(exc):
                    raise CampaignOpsSetupRequiredError(
                        "Campaign Operations database schema is not initialized."
                    ) from exc
                raise CampaignOpsDatabaseError("Campaign Operations write failed.") from exc
        if row is None:
            raise CampaignOpsNotFoundError("Campaign Operations record was not found.")
        return model_type(**normalize_row(row))

    def _execute(self, query: str, params: tuple[Any, ...]) -> None:
        with self.connection_scope() as (connection, owns_connection):
            try:
                with connection.cursor() as cursor:
                    cursor.execute(query, params)
                    if cursor.rowcount == 0:
                        raise CampaignOpsNotFoundError("Campaign Operations record was not found.")
                if owns_connection:
                    connection.commit()
            except CampaignOpsNotFoundError:
                if owns_connection:
                    connection.rollback()
                raise
            except Exception as exc:
                if owns_connection:
                    connection.rollback()
                if is_undefined_table_error(exc):
                    raise CampaignOpsSetupRequiredError(
                        "Campaign Operations database schema is not initialized."
                    ) from exc
                raise CampaignOpsDatabaseError("Campaign Operations write failed.") from exc

    def list_active_users(self) -> list[CampaignOpsUser]:
        return self._fetch_all(
            """
            select * from campaign_ops_users
            where is_active = true
            order by display_name asc
            """,
            (),
            CampaignOpsUser,
        )

    def get_user_by_id(self, user_id: str) -> CampaignOpsUser | None:
        return self._fetch_one(
            "select * from campaign_ops_users where id = %s",
            (user_id,),
            CampaignOpsUser,
        )

    def get_user_by_display_name(self, display_name: str) -> CampaignOpsUser | None:
        return self._fetch_one(
            """
            select * from campaign_ops_users
            where lower(display_name) = lower(%s) and is_active = true
            """,
            (display_name,),
            CampaignOpsUser,
        )

    def create_client(self, name: str, actor_user_id: str | None = None) -> Client:
        return self._write_returning(
            """
            insert into campaign_ops_clients (name, created_by, updated_by)
            values (%s, %s, %s)
            returning *
            """,
            (require_text(name, "name"), actor_user_id, actor_user_id),
            Client,
        )

    def list_active_clients(self) -> list[Client]:
        return self._fetch_all(
            """
            select * from campaign_ops_clients
            where is_active = true
            order by name asc
            """,
            (),
            Client,
        )

    def get_client_by_normalized_name(self, name: str) -> Client | None:
        return self._fetch_one(
            """
            select * from campaign_ops_clients
            where lower(name) = lower(%s) and is_active = true
            """,
            (require_text(name, "name"),),
            Client,
        )

    def get_client(self, client_id: str) -> Client | None:
        return self._fetch_one(
            "select * from campaign_ops_clients where id = %s",
            (client_id,),
            Client,
        )

    def update_client(
        self,
        client_id: str,
        name: str,
        actor_user_id: str | None = None,
    ) -> Client:
        return self._write_returning(
            """
            update campaign_ops_clients
            set name = %s, updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (require_text(name, "name"), actor_user_id, client_id),
            Client,
        )

    def deactivate_client(self, client_id: str, actor_user_id: str | None = None) -> None:
        self._execute(
            """
            update campaign_ops_clients
            set is_active = false, updated_by = %s
            where id = %s and is_active = true
            """,
            (actor_user_id, client_id),
        )

    def create_program(
        self,
        program_name: str,
        actor_user_id: str | None = None,
        client_id: str | None = None,
        primary_workstream_type: str | None = None,
        status: str = ProgramStatus.DRAFT.value,
        cross_stage: str = CrossStage.DRAFT.value,
        risk_level: str = RiskLevel.UNRATED.value,
        priority: str | None = None,
        description: str | None = None,
        latest_update: str | None = None,
        start_date: Any | None = None,
        target_end_date: Any | None = None,
    ) -> Program:
        if primary_workstream_type is not None:
            primary_workstream_type = enum_value(
                WorkstreamType,
                primary_workstream_type,
                "primary_workstream_type",
            )
        return self._write_returning(
            """
            insert into campaign_ops_programs (
                program_name, client_id, primary_workstream_type, status, cross_stage,
                risk_level, priority, description, latest_update, start_date,
                target_end_date, created_by, updated_by
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                require_text(program_name, "program_name"),
                client_id,
                primary_workstream_type,
                enum_value(ProgramStatus, status, "status"),
                enum_value(CrossStage, cross_stage, "cross_stage"),
                enum_value(RiskLevel, risk_level, "risk_level"),
                priority,
                description,
                latest_update,
                start_date,
                target_end_date,
                actor_user_id,
                actor_user_id,
            ),
            Program,
        )

    def get_program(self, program_id: str) -> Program | None:
        return self._fetch_one(
            "select * from campaign_ops_programs where id = %s",
            (program_id,),
            Program,
        )

    def get_program_client(self, program_id: str) -> Client | None:
        return self._fetch_one(
            """
            select c.*
            from campaign_ops_programs p
            join campaign_ops_clients c on c.id = p.client_id
            where p.id = %s
            """,
            (program_id,),
            Client,
        )

    def list_program_portfolio(
        self,
        search: str | None = None,
        program_name: str | None = None,
        client_name: str | None = None,
        client_id: str | None = None,
        primary_workstream_type: str | None = None,
        connected_workstream_type: str | None = None,
        cross_stage: str | None = None,
        status: str | None = None,
        risk_level: str | None = None,
        primary_owner_user_id: str | None = None,
        assigned_user_id: str | None = None,
        active_state: str = "active",
        permitted_user_id: str | None = None,
        sort_by: str = "recently_updated",
    ) -> list[ProgramPortfolioRow]:
        """Return portfolio rows with owner, workstream, and assignment aggregates."""
        clauses: list[str] = []
        params: list[Any] = []
        if active_state == "active":
            clauses.append("p.is_active = true")
        elif active_state == "archived":
            clauses.append("p.is_active = false")
        if search:
            clauses.append("(p.program_name ilike %s or c.name ilike %s)")
            pattern = f"%{search.strip()}%"
            params.extend([pattern, pattern])
        if program_name:
            clauses.append("p.program_name ilike %s")
            params.append(f"%{program_name.strip()}%")
        if client_name:
            clauses.append("c.name ilike %s")
            params.append(f"%{client_name.strip()}%")
        if client_id:
            clauses.append("p.client_id = %s")
            params.append(client_id)
        if primary_workstream_type:
            clauses.append("p.primary_workstream_type = %s")
            params.append(enum_value(WorkstreamType, primary_workstream_type, "primary_workstream_type"))
        if connected_workstream_type:
            clauses.append(
                """
                exists (
                    select 1 from campaign_ops_workstreams wf
                    where wf.program_id = p.id
                      and wf.is_active = true
                      and wf.workstream_type = %s
                )
                """
            )
            params.append(enum_value(WorkstreamType, connected_workstream_type, "connected_workstream_type"))
        if cross_stage:
            clauses.append("p.cross_stage = %s")
            params.append(enum_value(CrossStage, cross_stage, "cross_stage"))
        if status:
            clauses.append("p.status = %s")
            params.append(enum_value(ProgramStatus, status, "status"))
        if risk_level:
            clauses.append("p.risk_level = %s")
            params.append(enum_value(RiskLevel, risk_level, "risk_level"))
        if primary_owner_user_id:
            clauses.append("po.user_id = %s")
            params.append(primary_owner_user_id)
        if assigned_user_id:
            clauses.append("aa.user_ids @> array[%s]::uuid[]")
            params.append(assigned_user_id)
        if permitted_user_id:
            clauses.append("aa.user_ids @> array[%s]::uuid[]")
            params.append(permitted_user_id)

        order_by = {
            "program_name": "p.program_name asc",
            "client": "c.name asc nulls last, p.program_name asc",
            "risk": "p.risk_level asc, p.updated_at desc",
            "cross_stage": "p.cross_stage asc, p.updated_at desc",
            "program_status": "p.status asc, p.updated_at desc",
            "start_date": "p.start_date asc nulls last, p.updated_at desc",
            "target_end_date": "p.target_end_date asc nulls last, p.updated_at desc",
            "recently_updated": "p.updated_at desc, p.program_name asc",
        }.get(sort_by, "p.updated_at desc, p.program_name asc")
        where_clause = "where " + " and ".join(clauses) if clauses else ""
        query = f"""
            with workstream_agg as (
                select program_id, array_agg(workstream_type order by workstream_type) as workstream_types
                from campaign_ops_workstreams
                where is_active = true
                group by program_id
            ),
            assignment_agg as (
                select
                    a.program_id,
                    array_agg(distinct a.user_id) as user_ids,
                    array_agg(distinct u.display_name order by u.display_name) as user_names
                from campaign_ops_assignments a
                join campaign_ops_users u on u.id = a.user_id
                where a.is_active = true and u.is_active = true
                group by a.program_id
            ),
            primary_owner as (
                select distinct on (a.program_id)
                    a.program_id,
                    a.user_id,
                    u.display_name
                from campaign_ops_assignments a
                join campaign_ops_users u on u.id = a.user_id
                where a.is_active = true
                  and a.is_primary = true
                  and a.assignment_role = %s
                order by a.program_id, a.updated_at desc
            )
            select
                p.id,
                p.program_name,
                c.name as client_name,
                p.primary_workstream_type,
                coalesce(wa.workstream_types, array[]::text[]) as workstream_types,
                p.status,
                p.cross_stage,
                p.risk_level,
                p.priority,
                po.user_id as primary_owner_user_id,
                po.display_name as primary_owner_name,
                coalesce(aa.user_ids, array[]::uuid[]) as assigned_user_ids,
                coalesce(aa.user_names, array[]::text[]) as assigned_user_names,
                p.start_date,
                p.target_end_date,
                p.updated_at,
                p.is_active,
                null::text as assignment_role,
                null::text as assigned_workstream_type
            from campaign_ops_programs p
            left join campaign_ops_clients c on c.id = p.client_id
            left join workstream_agg wa on wa.program_id = p.id
            left join assignment_agg aa on aa.program_id = p.id
            left join primary_owner po on po.program_id = p.id
            {where_clause}
            order by {order_by}
        """
        rows = self._fetch_raw_all(query, (AssignmentRole.PROGRAM_OWNER.value, *params))
        return [self._portfolio_row_from_db(row) for row in rows]

    def list_programs_assigned_to_user(
        self,
        user_id: str,
        primary_workstream_type: str | None = None,
        connected_workstream_type: str | None = None,
        cross_stage: str | None = None,
        status: str | None = None,
        risk_level: str | None = None,
        active_state: str = "active",
    ) -> list[ProgramPortfolioRow]:
        """Return programs where the user has an active program or workstream assignment."""
        rows = self.list_program_portfolio(
            primary_workstream_type=primary_workstream_type,
            connected_workstream_type=connected_workstream_type,
            cross_stage=cross_stage,
            status=status,
            risk_level=risk_level,
            active_state=active_state,
            assigned_user_id=user_id,
            sort_by="recently_updated",
        )
        assignment_rows = self._fetch_raw_all(
            """
            select
                a.program_id,
                a.assignment_role,
                w.workstream_type as assigned_workstream_type
            from campaign_ops_assignments a
            left join campaign_ops_workstreams w on w.id = a.workstream_id
            where a.user_id = %s and a.is_active = true
            order by a.is_primary desc, a.updated_at desc
            """,
            (user_id,),
        )
        by_program = {str(row["program_id"]): row for row in assignment_rows}
        for row in rows:
            assignment = by_program.get(row.id)
            if assignment:
                row.assignment_role = assignment.get("assignment_role")
                row.assigned_workstream_type = assignment.get("assigned_workstream_type")
        return rows

    def list_programs(
        self,
        active_only: bool = True,
        status: str | None = None,
        cross_stage: str | None = None,
        risk_level: str | None = None,
        client_id: str | None = None,
        assigned_user_id: str | None = None,
    ) -> list[Program]:
        clauses = []
        params: list[Any] = []
        join_clause = ""
        if active_only:
            clauses.append("p.is_active = true")
        if status:
            clauses.append("p.status = %s")
            params.append(enum_value(ProgramStatus, status, "status"))
        if cross_stage:
            clauses.append("p.cross_stage = %s")
            params.append(enum_value(CrossStage, cross_stage, "cross_stage"))
        if risk_level:
            clauses.append("p.risk_level = %s")
            params.append(enum_value(RiskLevel, risk_level, "risk_level"))
        if client_id:
            clauses.append("p.client_id = %s")
            params.append(client_id)
        if assigned_user_id:
            join_clause = """
            join campaign_ops_assignments a on a.program_id = p.id
            """
            clauses.append("a.user_id = %s")
            clauses.append("a.is_active = true")
            params.append(assigned_user_id)
        where_clause = " where " + " and ".join(clauses) if clauses else ""
        query = (
            "select distinct p.* from campaign_ops_programs p "
            + join_clause
            + where_clause
            + " order by p.updated_at desc, p.program_name asc"
        )
        return self._fetch_all(query, tuple(params), Program)

    def update_program(
        self,
        program_id: str,
        actor_user_id: str | None = None,
        program_name: str | None = None,
        status: str | None = None,
        cross_stage: str | None = None,
        risk_level: str | None = None,
        priority: str | None = None,
        description: str | None = None,
        latest_update: str | None = None,
        target_end_date: Any | None = None,
    ) -> Program:
        return self._write_returning(
            """
            update campaign_ops_programs
            set
                program_name = coalesce(%s, program_name),
                status = coalesce(%s, status),
                cross_stage = coalesce(%s, cross_stage),
                risk_level = coalesce(%s, risk_level),
                priority = coalesce(%s, priority),
                description = coalesce(%s, description),
                latest_update = coalesce(%s, latest_update),
                target_end_date = coalesce(%s, target_end_date),
                updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (
                require_text(program_name, "program_name") if program_name is not None else None,
                enum_value(ProgramStatus, status, "status") if status is not None else None,
                enum_value(CrossStage, cross_stage, "cross_stage") if cross_stage is not None else None,
                enum_value(RiskLevel, risk_level, "risk_level") if risk_level is not None else None,
                priority,
                description,
                latest_update,
                target_end_date,
                actor_user_id,
                program_id,
            ),
            Program,
        )

    def archive_program(self, program_id: str, actor_user_id: str | None = None) -> Program:
        return self._write_returning(
            """
            update campaign_ops_programs
            set
                status = %s,
                is_active = false,
                archived_at = now(),
                updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (ProgramStatus.ARCHIVED.value, actor_user_id, program_id),
            Program,
        )

    def create_workstream(
        self,
        program_id: str,
        workstream_type: str,
        actor_user_id: str | None = None,
        owner_user_id: str | None = None,
        status: str = ProgramStatus.ACTIVE.value,
        cross_stage: str = CrossStage.PLANNING.value,
        risk_level: str = RiskLevel.UNRATED.value,
        waiting_on: str = WaitingOn.NONE.value,
        next_action: str | None = None,
        next_due_date: Any | None = None,
        latest_update: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> Workstream:
        return self._write_returning(
            """
            insert into campaign_ops_workstreams (
                program_id, workstream_type, status, cross_stage, risk_level,
                owner_user_id, next_action, next_due_date, waiting_on, latest_update,
                metadata_json, created_by, updated_by
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                program_id,
                enum_value(WorkstreamType, workstream_type, "workstream_type"),
                enum_value(ProgramStatus, status, "status"),
                enum_value(CrossStage, cross_stage, "cross_stage"),
                enum_value(RiskLevel, risk_level, "risk_level"),
                owner_user_id,
                next_action,
                next_due_date,
                enum_value(WaitingOn, waiting_on, "waiting_on"),
                latest_update,
                jsonb_value(metadata_json),
                actor_user_id,
                actor_user_id,
            ),
            Workstream,
        )

    def list_workstreams_by_program(self, program_id: str) -> list[Workstream]:
        return self._fetch_all(
            """
            select * from campaign_ops_workstreams
            where program_id = %s and is_active = true
            order by workstream_type asc
            """,
            (program_id,),
            Workstream,
        )

    def update_workstream(
        self,
        workstream_id: str,
        actor_user_id: str | None = None,
        status: str | None = None,
        cross_stage: str | None = None,
        risk_level: str | None = None,
        owner_user_id: str | None = None,
        next_action: str | None = None,
        next_due_date: Any | None = None,
        waiting_on: str | None = None,
        latest_update: str | None = None,
    ) -> Workstream:
        return self._write_returning(
            """
            update campaign_ops_workstreams
            set
                status = coalesce(%s, status),
                cross_stage = coalesce(%s, cross_stage),
                risk_level = coalesce(%s, risk_level),
                owner_user_id = coalesce(%s, owner_user_id),
                next_action = coalesce(%s, next_action),
                next_due_date = coalesce(%s, next_due_date),
                waiting_on = coalesce(%s, waiting_on),
                latest_update = coalesce(%s, latest_update),
                updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (
                enum_value(ProgramStatus, status, "status") if status is not None else None,
                enum_value(CrossStage, cross_stage, "cross_stage") if cross_stage is not None else None,
                enum_value(RiskLevel, risk_level, "risk_level") if risk_level is not None else None,
                owner_user_id,
                next_action,
                next_due_date,
                enum_value(WaitingOn, waiting_on, "waiting_on") if waiting_on is not None else None,
                latest_update,
                actor_user_id,
                workstream_id,
            ),
            Workstream,
        )

    def deactivate_workstream(self, workstream_id: str, actor_user_id: str | None = None) -> None:
        self._execute(
            """
            update campaign_ops_workstreams
            set is_active = false, updated_by = %s
            where id = %s and is_active = true
            """,
            (actor_user_id, workstream_id),
        )

    def create_assignment(
        self,
        program_id: str,
        user_id: str,
        assignment_role: str,
        actor_user_id: str | None = None,
        workstream_id: str | None = None,
        is_primary: bool = False,
    ) -> ProgramAssignment:
        return self._write_returning(
            """
            insert into campaign_ops_assignments (
                program_id, workstream_id, user_id, assignment_role, is_primary,
                created_by, updated_by
            )
            values (%s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                program_id,
                workstream_id,
                user_id,
                enum_value(AssignmentRole, assignment_role, "assignment_role"),
                is_primary,
                actor_user_id,
                actor_user_id,
            ),
            ProgramAssignment,
        )

    def list_assignments_by_program(self, program_id: str) -> list[ProgramAssignment]:
        return self._fetch_all(
            """
            select * from campaign_ops_assignments
            where program_id = %s and is_active = true
            order by is_primary desc, assignment_role asc
            """,
            (program_id,),
            ProgramAssignment,
        )

    def list_assignments_by_user(self, user_id: str) -> list[ProgramAssignment]:
        return self._fetch_all(
            """
            select * from campaign_ops_assignments
            where user_id = %s and is_active = true
            order by updated_at desc
            """,
            (user_id,),
            ProgramAssignment,
        )

    def deactivate_assignment(self, assignment_id: str, actor_user_id: str | None = None) -> None:
        self._execute(
            """
            update campaign_ops_assignments
            set is_active = false, updated_by = %s
            where id = %s and is_active = true
            """,
            (actor_user_id, assignment_id),
        )

    def create_task(
        self,
        program_id: str,
        title: str,
        actor_user_id: str | None = None,
        workstream_id: str | None = None,
        description: str | None = None,
        assigned_user_id: str | None = None,
        responsible_party: str | None = None,
        status: str = TaskStatus.NOT_STARTED.value,
        risk_level: str = RiskLevel.UNRATED.value,
        waiting_on: str = WaitingOn.NONE.value,
        due_date: Any | None = None,
        start_date: Any | None = None,
        hard_deadline: bool = False,
        priority: str | None = None,
        sort_order: int = 0,
        metadata_json: dict[str, Any] | None = None,
    ) -> Task:
        return self._write_returning(
            """
            insert into campaign_ops_tasks (
                program_id, workstream_id, title, description, assigned_user_id,
                responsible_party, status, risk_level, waiting_on, due_date, start_date,
                hard_deadline, priority, sort_order, metadata_json, created_by, updated_by
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                program_id,
                workstream_id,
                require_text(title, "title"),
                description,
                assigned_user_id,
                responsible_party,
                enum_value(TaskStatus, status, "status"),
                enum_value(RiskLevel, risk_level, "risk_level"),
                enum_value(WaitingOn, waiting_on, "waiting_on"),
                due_date,
                start_date,
                hard_deadline,
                priority,
                sort_order,
                jsonb_value(metadata_json),
                actor_user_id,
                actor_user_id,
            ),
            Task,
        )

    def list_tasks_by_program(self, program_id: str) -> list[Task]:
        return self._fetch_all(
            """
            select * from campaign_ops_tasks
            where program_id = %s and is_active = true
            order by sort_order asc, due_date asc nulls last, created_at asc
            """,
            (program_id,),
            Task,
        )

    def list_tasks_by_workstream(self, workstream_id: str) -> list[Task]:
        return self._fetch_all(
            """
            select * from campaign_ops_tasks
            where workstream_id = %s and is_active = true
            order by sort_order asc, due_date asc nulls last, created_at asc
            """,
            (workstream_id,),
            Task,
        )

    def list_tasks_by_assigned_user(self, user_id: str) -> list[Task]:
        return self._fetch_all(
            """
            select * from campaign_ops_tasks
            where assigned_user_id = %s and is_active = true
            order by due_date asc nulls last, created_at asc
            """,
            (user_id,),
            Task,
        )

    def update_task(
        self,
        task_id: str,
        actor_user_id: str | None = None,
        title: str | None = None,
        status: str | None = None,
        risk_level: str | None = None,
        waiting_on: str | None = None,
        assigned_user_id: str | None = None,
        due_date: Any | None = None,
        description: str | None = None,
    ) -> Task:
        return self._write_returning(
            """
            update campaign_ops_tasks
            set
                title = coalesce(%s, title),
                status = coalesce(%s, status),
                risk_level = coalesce(%s, risk_level),
                waiting_on = coalesce(%s, waiting_on),
                assigned_user_id = coalesce(%s, assigned_user_id),
                due_date = coalesce(%s, due_date),
                description = coalesce(%s, description),
                updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (
                require_text(title, "title") if title is not None else None,
                enum_value(TaskStatus, status, "status") if status is not None else None,
                enum_value(RiskLevel, risk_level, "risk_level") if risk_level is not None else None,
                enum_value(WaitingOn, waiting_on, "waiting_on") if waiting_on is not None else None,
                assigned_user_id,
                due_date,
                description,
                actor_user_id,
                task_id,
            ),
            Task,
        )

    def complete_task(self, task_id: str, actor_user_id: str | None = None) -> Task:
        return self._write_returning(
            """
            update campaign_ops_tasks
            set status = %s, completed_at = now(), updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (TaskStatus.COMPLETED.value, actor_user_id, task_id),
            Task,
        )

    def deactivate_task(self, task_id: str, actor_user_id: str | None = None) -> None:
        self._execute(
            """
            update campaign_ops_tasks
            set is_active = false, updated_by = %s
            where id = %s and is_active = true
            """,
            (actor_user_id, task_id),
        )

    def create_resource(
        self,
        program_id: str,
        resource_type: str,
        title: str,
        actor_user_id: str | None = None,
        workstream_id: str | None = None,
        url: str | None = None,
        notes: str | None = None,
        is_required: bool = False,
    ) -> Resource:
        return self._write_returning(
            """
            insert into campaign_ops_resources (
                program_id, workstream_id, resource_type, title, url, notes,
                is_required, created_by, updated_by
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                program_id,
                workstream_id,
                require_text(resource_type, "resource_type"),
                require_text(title, "title"),
                url,
                notes,
                is_required,
                actor_user_id,
                actor_user_id,
            ),
            Resource,
        )

    def list_resources_by_program(self, program_id: str) -> list[Resource]:
        return self._fetch_all(
            """
            select * from campaign_ops_resources
            where program_id = %s
            order by created_at asc
            """,
            (program_id,),
            Resource,
        )

    def update_resource(
        self,
        resource_id: str,
        actor_user_id: str | None = None,
        title: str | None = None,
        url: str | None = None,
        notes: str | None = None,
        is_required: bool | None = None,
    ) -> Resource:
        return self._write_returning(
            """
            update campaign_ops_resources
            set
                title = coalesce(%s, title),
                url = coalesce(%s, url),
                notes = coalesce(%s, notes),
                is_required = coalesce(%s, is_required),
                updated_by = %s
            where id = %s
            returning *
            """,
            (
                require_text(title, "title") if title is not None else None,
                url,
                notes,
                is_required,
                actor_user_id,
                resource_id,
            ),
            Resource,
        )

    def append_note(
        self,
        program_id: str,
        note_text: str,
        author_user_id: str | None = None,
        workstream_id: str | None = None,
        task_id: str | None = None,
        note_type: str | None = None,
        is_internal: bool = True,
    ) -> ProgramNote:
        return self._write_returning(
            """
            insert into campaign_ops_notes (
                program_id, workstream_id, task_id, author_user_id, note_text,
                note_type, is_internal
            )
            values (%s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                program_id,
                workstream_id,
                task_id,
                author_user_id,
                require_text(note_text, "note_text"),
                note_type,
                is_internal,
            ),
            ProgramNote,
        )

    def list_notes_chronologically(self, program_id: str) -> list[ProgramNote]:
        return self._fetch_all(
            """
            select * from campaign_ops_notes
            where program_id = %s
            order by created_at asc
            """,
            (program_id,),
            ProgramNote,
        )

    def append_event(
        self,
        event_type: str,
        entity_type: str,
        actor_user_id: str | None = None,
        entity_id: str | None = None,
        program_id: str | None = None,
        workstream_id: str | None = None,
        task_id: str | None = None,
        old_value_json: dict[str, Any] | None = None,
        new_value_json: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> ActivityEvent:
        return self._write_returning(
            """
            insert into campaign_ops_activity (
                program_id, workstream_id, task_id, actor_user_id, event_type,
                entity_type, entity_id, old_value_json, new_value_json, message
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                program_id,
                workstream_id,
                task_id,
                actor_user_id,
                require_text(event_type, "event_type"),
                require_text(entity_type, "entity_type"),
                entity_id,
                jsonb_value(old_value_json) if old_value_json is not None else None,
                jsonb_value(new_value_json) if new_value_json is not None else None,
                message,
            ),
            ActivityEvent,
        )

    def list_program_activity(self, program_id: str) -> list[ActivityEvent]:
        return self._fetch_all(
            """
            select * from campaign_ops_activity
            where program_id = %s
            order by created_at asc
            """,
            (program_id,),
            ActivityEvent,
        )
