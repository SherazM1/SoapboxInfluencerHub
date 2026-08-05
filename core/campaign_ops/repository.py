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
    ContentDeliverableRecord,
    ContentInvoiceCheckpointRecord,
    ContentMonitoringUpdateRecord,
    ContentPortfolioRow,
    ContentProgramRecord,
    ContentSkuGroupRecord,
    ContentSkuRecord,
    ContentSubmissionRecord,
    InfluencerApprovalRoundRecord,
    InfluencerCampaignRecord,
    InfluencerContentRoundRecord,
    InfluencerCreatorSummaryRecord,
    InfluencerCreatorWaveRecord,
    InfluencerLiveCheckpointRecord,
    InfluencerLiveCreatorRecord,
    InfluencerLiveExceptionRecord,
    InfluencerLivePortfolioRow,
    InfluencerPlanningPortfolioRow,
    InfluencerPlanningStepRecord,
    InfluencerRecapCheckpointRecord,
    InfluencerRecapLaunchItemRecord,
    InfluencerRecapPortfolioRow,
    InfluencerRecapRecord,
    InfluencerRecapRequirementRecord,
    InsightsObjectiveRecord,
    InsightsPortfolioRow,
    InsightsProjectRecord,
    Milestone,
    MilestoneListRow,
    NoteListRow,
    Program,
    ProgramAssignment,
    ProgramPortfolioRow,
    ProgramNote,
    ReportingRequestListRow,
    ReportingRequestRecord,
    RetailMediaActivationRecord,
    RetailMediaCampaignRecord,
    RetailMediaChannelRecord,
    RetailMediaCreativeRecord,
    RetailMediaOptimizationRecord,
    RetailMediaPortfolioRow,
    Resource,
    ResourceListRow,
    Task,
    TaskListRow,
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
            latest_update=normalized.get("latest_update"),
            start_date=normalized.get("start_date"),
            target_end_date=normalized.get("target_end_date"),
            updated_at=normalized.get("updated_at"),
            is_active=bool(normalized.get("is_active", True)),
            assignment_role=normalized.get("assignment_role"),
            assigned_workstream_type=normalized.get("assigned_workstream_type"),
            open_task_count=int(normalized.get("open_task_count") or 0),
            overdue_task_count=int(normalized.get("overdue_task_count") or 0),
            nearest_task_due_date=normalized.get("nearest_task_due_date"),
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
            ),
            task_agg as (
                select
                    program_id,
                    count(*) filter (where is_active = true and status <> %s) as open_task_count,
                    count(*) filter (
                        where is_active = true and status <> %s and due_date < current_date
                    ) as overdue_task_count,
                    min(due_date) filter (where is_active = true and status <> %s) as nearest_task_due_date
                from campaign_ops_tasks
                group by program_id
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
                p.latest_update,
                p.start_date,
                p.target_end_date,
                p.updated_at,
                p.is_active,
                null::text as assignment_role,
                null::text as assigned_workstream_type,
                coalesce(ta.open_task_count, 0) as open_task_count,
                coalesce(ta.overdue_task_count, 0) as overdue_task_count,
                ta.nearest_task_due_date
            from campaign_ops_programs p
            left join campaign_ops_clients c on c.id = p.client_id
            left join workstream_agg wa on wa.program_id = p.id
            left join assignment_agg aa on aa.program_id = p.id
            left join primary_owner po on po.program_id = p.id
            left join task_agg ta on ta.program_id = p.id
            {where_clause}
            order by {order_by}
        """
        rows = self._fetch_raw_all(
            query,
            (
                AssignmentRole.PROGRAM_OWNER.value,
                TaskStatus.COMPLETED.value,
                TaskStatus.COMPLETED.value,
                TaskStatus.COMPLETED.value,
                *params,
            ),
        )
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
        task_rows = self._fetch_raw_all(
            """
            select
                program_id,
                count(*) filter (where is_active = true and status <> %s) as open_task_count,
                count(*) filter (
                    where is_active = true and status <> %s and due_date < current_date
                ) as overdue_task_count,
                min(due_date) filter (where is_active = true and status <> %s) as nearest_task_due_date
            from campaign_ops_tasks
            where assigned_user_id = %s
            group by program_id
            """,
            (
                TaskStatus.COMPLETED.value,
                TaskStatus.COMPLETED.value,
                TaskStatus.COMPLETED.value,
                user_id,
            ),
        )
        task_counts = {str(row["program_id"]): row for row in task_rows}
        for row in rows:
            assignment = by_program.get(row.id)
            if assignment:
                row.assignment_role = assignment.get("assignment_role")
                row.assigned_workstream_type = assignment.get("assigned_workstream_type")
            counts = task_counts.get(row.id)
            if counts:
                row.open_task_count = int(counts.get("open_task_count") or 0)
                row.overdue_task_count = int(counts.get("overdue_task_count") or 0)
                row.nearest_task_due_date = counts.get("nearest_task_due_date")
            else:
                row.open_task_count = 0
                row.overdue_task_count = 0
                row.nearest_task_due_date = None
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
        client_id: str | None = None,
        primary_workstream_type: str | None = None,
        program_name: str | None = None,
        status: str | None = None,
        cross_stage: str | None = None,
        risk_level: str | None = None,
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
            update campaign_ops_programs
            set
                client_id = coalesce(%s, client_id),
                primary_workstream_type = coalesce(%s, primary_workstream_type),
                program_name = coalesce(%s, program_name),
                status = coalesce(%s, status),
                cross_stage = coalesce(%s, cross_stage),
                risk_level = coalesce(%s, risk_level),
                priority = coalesce(%s, priority),
                description = coalesce(%s, description),
                latest_update = coalesce(%s, latest_update),
                start_date = coalesce(%s, start_date),
                target_end_date = coalesce(%s, target_end_date),
                updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (
                client_id,
                primary_workstream_type,
                require_text(program_name, "program_name") if program_name is not None else None,
                enum_value(ProgramStatus, status, "status") if status is not None else None,
                enum_value(CrossStage, cross_stage, "cross_stage") if cross_stage is not None else None,
                enum_value(RiskLevel, risk_level, "risk_level") if risk_level is not None else None,
                priority,
                description,
                latest_update,
                start_date,
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

    def reactivate_program(self, program_id: str, actor_user_id: str | None = None) -> Program:
        return self._write_returning(
            """
            update campaign_ops_programs
            set
                is_active = true,
                archived_at = null,
                status = case when status = %s then %s else status end,
                updated_by = %s
            where id = %s and is_active = false
            returning *
            """,
            (ProgramStatus.ARCHIVED.value, ProgramStatus.ACTIVE.value, actor_user_id, program_id),
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

    def list_all_workstreams_by_program(self, program_id: str) -> list[Workstream]:
        return self._fetch_all(
            """
            select * from campaign_ops_workstreams
            where program_id = %s
            order by is_active desc, workstream_type asc
            """,
            (program_id,),
            Workstream,
        )

    def get_workstream(self, workstream_id: str) -> Workstream | None:
        return self._fetch_one(
            "select * from campaign_ops_workstreams where id = %s",
            (workstream_id,),
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

    def reactivate_workstream(self, workstream_id: str, actor_user_id: str | None = None) -> Workstream:
        return self._write_returning(
            """
            update campaign_ops_workstreams
            set is_active = true, updated_by = %s
            where id = %s and is_active = false
            returning *
            """,
            (actor_user_id, workstream_id),
            Workstream,
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

    def list_all_assignments_by_program(self, program_id: str) -> list[ProgramAssignment]:
        return self._fetch_all(
            """
            select * from campaign_ops_assignments
            where program_id = %s
            order by is_active desc, is_primary desc, assignment_role asc
            """,
            (program_id,),
            ProgramAssignment,
        )

    def get_assignment(self, assignment_id: str) -> ProgramAssignment | None:
        return self._fetch_one(
            "select * from campaign_ops_assignments where id = %s",
            (assignment_id,),
            ProgramAssignment,
        )

    def update_assignment(
        self,
        assignment_id: str,
        actor_user_id: str | None = None,
        program_id: str | None = None,
        workstream_id: str | None = None,
        user_id: str | None = None,
        assignment_role: str | None = None,
        is_primary: bool | None = None,
    ) -> ProgramAssignment:
        return self._write_returning(
            """
            update campaign_ops_assignments
            set
                program_id = coalesce(%s, program_id),
                workstream_id = %s,
                user_id = coalesce(%s, user_id),
                assignment_role = coalesce(%s, assignment_role),
                is_primary = coalesce(%s, is_primary),
                updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (
                program_id,
                workstream_id,
                user_id,
                enum_value(AssignmentRole, assignment_role, "assignment_role") if assignment_role is not None else None,
                is_primary,
                actor_user_id,
                assignment_id,
            ),
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

    def reactivate_assignment(self, assignment_id: str, actor_user_id: str | None = None) -> ProgramAssignment:
        return self._write_returning(
            """
            update campaign_ops_assignments
            set is_active = true, updated_by = %s
            where id = %s and is_active = false
            returning *
            """,
            (actor_user_id, assignment_id),
            ProgramAssignment,
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

    def get_task(self, task_id: str) -> Task | None:
        return self._fetch_one(
            "select * from campaign_ops_tasks where id = %s",
            (task_id,),
            Task,
        )

    def _task_list_row_from_db(self, row: dict[str, Any]) -> TaskListRow:
        normalized = normalize_row(row)
        return TaskListRow(
            id=str(normalized["id"]),
            program_id=str(normalized["program_id"]),
            program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"),
            title=str(normalized["title"]),
            description=normalized.get("description"),
            workstream_id=normalize_id(normalized.get("workstream_id")),
            workstream_type=normalized.get("workstream_type"),
            assigned_user_id=normalize_id(normalized.get("assigned_user_id")),
            assigned_user_name=normalized.get("assigned_user_name"),
            responsible_party=normalized.get("responsible_party"),
            status=str(normalized["status"]),
            risk_level=str(normalized["risk_level"]),
            waiting_on=str(normalized["waiting_on"]),
            due_date=normalized.get("due_date"),
            start_date=normalized.get("start_date"),
            completed_at=normalized.get("completed_at"),
            hard_deadline=bool(normalized.get("hard_deadline", False)),
            priority=normalized.get("priority"),
            sort_order=int(normalized.get("sort_order") or 0),
            is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"),
            updated_at=normalized.get("updated_at"),
        )

    def list_task_rows_by_program(
        self,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[TaskListRow]:
        clauses = ["t.program_id = %s"]
        params: list[Any] = [program_id]
        if not include_inactive:
            clauses.append("t.is_active = true")
        query = f"""
            select
                t.*,
                p.program_name,
                c.name as client_name,
                w.workstream_type,
                u.display_name as assigned_user_name
            from campaign_ops_tasks t
            join campaign_ops_programs p on p.id = t.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_workstreams w on w.id = t.workstream_id
            left join campaign_ops_users u on u.id = t.assigned_user_id
            where {' and '.join(clauses)}
            order by t.sort_order asc, t.due_date asc nulls last, t.updated_at desc
        """
        return [
            self._task_list_row_from_db(row)
            for row in self._fetch_raw_all(query, tuple(params))
        ]

    def list_task_rows_by_assigned_user(
        self,
        user_id: str,
        include_inactive: bool = False,
    ) -> list[TaskListRow]:
        clauses = ["t.assigned_user_id = %s"]
        params: list[Any] = [user_id]
        if not include_inactive:
            clauses.append("t.is_active = true")
        query = f"""
            select
                t.*,
                p.program_name,
                c.name as client_name,
                w.workstream_type,
                u.display_name as assigned_user_name
            from campaign_ops_tasks t
            join campaign_ops_programs p on p.id = t.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_workstreams w on w.id = t.workstream_id
            left join campaign_ops_users u on u.id = t.assigned_user_id
            where {' and '.join(clauses)}
            order by t.due_date asc nulls last, t.updated_at desc
        """
        return [
            self._task_list_row_from_db(row)
            for row in self._fetch_raw_all(query, tuple(params))
        ]

    def list_dashboard_task_rows(
        self,
        include_inactive: bool = False,
        permitted_user_id: str | None = None,
    ) -> list[TaskListRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_inactive:
            clauses.append("t.is_active = true")
            clauses.append("p.is_active = true")
        if permitted_user_id:
            clauses.append(
                """
                exists (
                    select 1 from campaign_ops_assignments a
                    where a.program_id = p.id
                      and a.user_id = %s
                      and a.is_active = true
                )
                """
            )
            params.append(permitted_user_id)
        where_clause = "where " + " and ".join(clauses) if clauses else ""
        query = f"""
            select
                t.*,
                p.program_name,
                c.name as client_name,
                w.workstream_type,
                u.display_name as assigned_user_name
            from campaign_ops_tasks t
            join campaign_ops_programs p on p.id = t.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_workstreams w on w.id = t.workstream_id
            left join campaign_ops_users u on u.id = t.assigned_user_id
            {where_clause}
            order by t.due_date asc nulls last, t.hard_deadline desc, t.updated_at desc
        """
        return [
            self._task_list_row_from_db(row)
            for row in self._fetch_raw_all(query, tuple(params))
        ]

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

    def update_task_details(
        self,
        task_id: str,
        actor_user_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        workstream_id: str | None = None,
        assigned_user_id: str | None = None,
        responsible_party: str | None = None,
        status: str | None = None,
        risk_level: str | None = None,
        waiting_on: str | None = None,
        due_date: Any | None = None,
        start_date: Any | None = None,
        completed_at: Any | None = None,
        hard_deadline: bool | None = None,
        priority: str | None = None,
        sort_order: int | None = None,
    ) -> Task:
        return self._write_returning(
            """
            update campaign_ops_tasks
            set
                title = coalesce(%s, title),
                description = %s,
                workstream_id = %s,
                assigned_user_id = %s,
                responsible_party = %s,
                status = coalesce(%s, status),
                risk_level = coalesce(%s, risk_level),
                waiting_on = coalesce(%s, waiting_on),
                due_date = %s,
                start_date = %s,
                completed_at = %s,
                hard_deadline = coalesce(%s, hard_deadline),
                priority = %s,
                sort_order = coalesce(%s, sort_order),
                updated_by = %s
            where id = %s and is_active = true
            returning *
            """,
            (
                require_text(title, "title") if title is not None else None,
                description,
                workstream_id,
                assigned_user_id,
                responsible_party,
                enum_value(TaskStatus, status, "status") if status is not None else None,
                enum_value(RiskLevel, risk_level, "risk_level") if risk_level is not None else None,
                enum_value(WaitingOn, waiting_on, "waiting_on") if waiting_on is not None else None,
                due_date,
                start_date,
                completed_at,
                hard_deadline,
                priority,
                sort_order,
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

    def reactivate_task(self, task_id: str, actor_user_id: str | None = None) -> Task:
        return self._write_returning(
            """
            update campaign_ops_tasks
            set is_active = true, updated_by = %s
            where id = %s and is_active = false
            returning *
            """,
            (actor_user_id, task_id),
            Task,
        )

    def create_milestone(
        self,
        program_id: str,
        title: str,
        actor_user_id: str | None = None,
        workstream_id: str | None = None,
        milestone_type: str | None = None,
        target_date: Any | None = None,
        start_date: Any | None = None,
        end_date: Any | None = None,
        status: str = TaskStatus.NOT_STARTED.value,
        owner_user_id: str | None = None,
        hard_deadline: bool = False,
        completed_at: Any | None = None,
        is_highlighted: bool = False,
    ) -> Milestone:
        return self._write_returning(
            """
            insert into campaign_ops_milestones (
                program_id, workstream_id, title, milestone_type, target_date,
                start_date, end_date, status, owner_user_id, hard_deadline,
                completed_at, is_highlighted, created_by, updated_by
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                program_id,
                workstream_id,
                require_text(title, "title"),
                milestone_type,
                target_date,
                start_date,
                end_date,
                enum_value(TaskStatus, status, "status"),
                owner_user_id,
                hard_deadline,
                completed_at,
                is_highlighted,
                actor_user_id,
                actor_user_id,
            ),
            Milestone,
        )

    def get_milestone(self, milestone_id: str) -> Milestone | None:
        return self._fetch_one(
            "select * from campaign_ops_milestones where id = %s",
            (milestone_id,),
            Milestone,
        )

    def update_milestone(
        self,
        milestone_id: str,
        actor_user_id: str | None = None,
        title: str | None = None,
        workstream_id: str | None = None,
        milestone_type: str | None = None,
        target_date: Any | None = None,
        start_date: Any | None = None,
        end_date: Any | None = None,
        status: str | None = None,
        owner_user_id: str | None = None,
        hard_deadline: bool | None = None,
        completed_at: Any | None = None,
        is_highlighted: bool | None = None,
    ) -> Milestone:
        return self._write_returning(
            """
            update campaign_ops_milestones
            set
                title = coalesce(%s, title),
                workstream_id = %s,
                milestone_type = %s,
                target_date = %s,
                start_date = %s,
                end_date = %s,
                status = coalesce(%s, status),
                owner_user_id = %s,
                hard_deadline = coalesce(%s, hard_deadline),
                completed_at = %s,
                is_highlighted = coalesce(%s, is_highlighted),
                updated_by = %s
            where id = %s
            returning *
            """,
            (
                require_text(title, "title") if title is not None else None,
                workstream_id,
                milestone_type,
                target_date,
                start_date,
                end_date,
                enum_value(TaskStatus, status, "status") if status is not None else None,
                owner_user_id,
                hard_deadline,
                completed_at,
                is_highlighted,
                actor_user_id,
                milestone_id,
            ),
            Milestone,
        )

    def deactivate_milestone(self, milestone_id: str, actor_user_id: str | None = None) -> None:
        self._execute(
            """
            update campaign_ops_milestones
            set is_active = false, updated_by = %s
            where id = %s and is_active = true
            """,
            (actor_user_id, milestone_id),
        )

    def reactivate_milestone(self, milestone_id: str, actor_user_id: str | None = None) -> Milestone:
        return self._write_returning(
            """
            update campaign_ops_milestones
            set is_active = true, updated_by = %s
            where id = %s and is_active = false
            returning *
            """,
            (actor_user_id, milestone_id),
            Milestone,
        )

    def _milestone_list_row_from_db(self, row: dict[str, Any]) -> MilestoneListRow:
        normalized = normalize_row(row)
        return MilestoneListRow(
            id=str(normalized["id"]),
            program_id=str(normalized["program_id"]),
            title=str(normalized["title"]),
            status=str(normalized["status"]),
            workstream_id=normalize_id(normalized.get("workstream_id")),
            workstream_type=normalized.get("workstream_type"),
            milestone_type=normalized.get("milestone_type"),
            target_date=normalized.get("target_date"),
            start_date=normalized.get("start_date"),
            end_date=normalized.get("end_date"),
            owner_user_id=normalize_id(normalized.get("owner_user_id")),
            owner_user_name=normalized.get("owner_user_name"),
            hard_deadline=bool(normalized.get("hard_deadline", False)),
            completed_at=normalized.get("completed_at"),
            is_highlighted=bool(normalized.get("is_highlighted", False)),
            is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"),
            updated_at=normalized.get("updated_at"),
        )

    def list_milestone_rows_by_program(
        self,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[MilestoneListRow]:
        clauses = ["m.program_id = %s"]
        params: list[Any] = [program_id]
        if not include_inactive:
            clauses.append("m.is_active = true")
        query = f"""
            select
                m.*,
                w.workstream_type,
                u.display_name as owner_user_name
            from campaign_ops_milestones m
            left join campaign_ops_workstreams w on w.id = m.workstream_id
            left join campaign_ops_users u on u.id = m.owner_user_id
            where {' and '.join(clauses)}
            order by coalesce(m.target_date, m.start_date, m.end_date) asc nulls last,
                     m.created_at asc
        """
        return [
            self._milestone_list_row_from_db(row)
            for row in self._fetch_raw_all(query, tuple(params))
        ]

    def list_dashboard_milestone_rows(
        self,
        include_inactive: bool = False,
        permitted_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_inactive:
            clauses.append("m.is_active = true")
            clauses.append("p.is_active = true")
        if permitted_user_id:
            clauses.append(
                """
                exists (
                    select 1 from campaign_ops_assignments a
                    where a.program_id = p.id
                      and a.user_id = %s
                      and a.is_active = true
                )
                """
            )
            params.append(permitted_user_id)
        where_clause = "where " + " and ".join(clauses) if clauses else ""
        return self._fetch_raw_all(
            f"""
            select
                m.*,
                p.program_name,
                c.name as client_name,
                w.workstream_type,
                u.display_name as owner_user_name
            from campaign_ops_milestones m
            join campaign_ops_programs p on p.id = m.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_workstreams w on w.id = m.workstream_id
            left join campaign_ops_users u on u.id = m.owner_user_id
            {where_clause}
            order by coalesce(m.target_date, m.start_date, m.end_date) asc nulls last,
                     m.hard_deadline desc,
                     m.created_at asc
            """,
            tuple(params),
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
            where program_id = %s and is_active = true
            order by created_at asc
            """,
            (program_id,),
            Resource,
        )

    def get_resource(self, resource_id: str) -> Resource | None:
        return self._fetch_one(
            "select * from campaign_ops_resources where id = %s",
            (resource_id,),
            Resource,
        )

    def list_all_resources_by_program(self, program_id: str) -> list[Resource]:
        return self._fetch_all(
            """
            select * from campaign_ops_resources
            where program_id = %s
            order by is_active desc, created_at asc
            """,
            (program_id,),
            Resource,
        )

    def list_dashboard_resource_rows(
        self,
        include_inactive: bool = False,
        permitted_user_id: str | None = None,
    ) -> list[ResourceListRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_inactive:
            clauses.append("r.is_active = true")
            clauses.append("p.is_active = true")
        if permitted_user_id:
            clauses.append(
                """
                exists (
                    select 1 from campaign_ops_assignments a
                    where a.program_id = p.id
                      and a.user_id = %s
                      and a.is_active = true
                )
                """
            )
            params.append(permitted_user_id)
        where_clause = "where " + " and ".join(clauses) if clauses else ""
        return self._fetch_all(
            f"""
            select
                r.id,
                r.program_id,
                r.title,
                r.resource_type,
                r.workstream_id,
                r.url,
                r.notes,
                r.is_required,
                r.is_active,
                r.created_at,
                r.updated_at,
                w.workstream_type
            from campaign_ops_resources r
            join campaign_ops_programs p on p.id = r.program_id
            left join campaign_ops_workstreams w on w.id = r.workstream_id
            {where_clause}
            order by r.created_at asc
            """,
            tuple(params),
            ResourceListRow,
        )

    def update_resource(
        self,
        resource_id: str,
        actor_user_id: str | None = None,
        title: str | None = None,
        resource_type: str | None = None,
        workstream_id: str | None = None,
        url: str | None = None,
        notes: str | None = None,
        is_required: bool | None = None,
    ) -> Resource:
        return self._write_returning(
            """
            update campaign_ops_resources
            set
                title = coalesce(%s, title),
                resource_type = coalesce(%s, resource_type),
                workstream_id = %s,
                url = %s,
                notes = %s,
                is_required = coalesce(%s, is_required),
                updated_by = %s
            where id = %s
            returning *
            """,
            (
                require_text(title, "title") if title is not None else None,
                require_text(resource_type, "resource_type") if resource_type is not None else None,
                workstream_id,
                url,
                notes,
                is_required,
                actor_user_id,
                resource_id,
            ),
            Resource,
        )

    def deactivate_resource(self, resource_id: str, actor_user_id: str | None = None) -> None:
        self._execute(
            """
            update campaign_ops_resources
            set is_active = false, updated_by = %s
            where id = %s and is_active = true
            """,
            (actor_user_id, resource_id),
        )

    def reactivate_resource(self, resource_id: str, actor_user_id: str | None = None) -> Resource:
        return self._write_returning(
            """
            update campaign_ops_resources
            set is_active = true, updated_by = %s
            where id = %s and is_active = false
            returning *
            """,
            (actor_user_id, resource_id),
            Resource,
        )

    def _resource_list_row_from_db(self, row: dict[str, Any]) -> ResourceListRow:
        normalized = normalize_row(row)
        return ResourceListRow(
            id=str(normalized["id"]),
            program_id=str(normalized["program_id"]),
            title=str(normalized["title"]),
            resource_type=str(normalized["resource_type"]),
            workstream_id=normalize_id(normalized.get("workstream_id")),
            workstream_type=normalized.get("workstream_type"),
            url=normalized.get("url"),
            notes=normalized.get("notes"),
            is_required=bool(normalized.get("is_required", False)),
            is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"),
            updated_at=normalized.get("updated_at"),
        )

    def list_resource_rows_by_program(
        self,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[ResourceListRow]:
        clauses = ["r.program_id = %s"]
        params: list[Any] = [program_id]
        if not include_inactive:
            clauses.append("r.is_active = true")
        query = f"""
            select r.*, w.workstream_type
            from campaign_ops_resources r
            left join campaign_ops_workstreams w on w.id = r.workstream_id
            where {' and '.join(clauses)}
            order by r.updated_at desc, r.title asc
        """
        return [
            self._resource_list_row_from_db(row)
            for row in self._fetch_raw_all(query, tuple(params))
        ]

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

    def _note_list_row_from_db(self, row: dict[str, Any]) -> NoteListRow:
        normalized = normalize_row(row)
        return NoteListRow(
            id=str(normalized["id"]),
            program_id=str(normalized["program_id"]),
            workstream_id=normalize_id(normalized.get("workstream_id")),
            workstream_type=normalized.get("workstream_type"),
            task_id=normalize_id(normalized.get("task_id")),
            task_title=normalized.get("task_title"),
            author_user_id=normalize_id(normalized.get("author_user_id")),
            author_display_name=normalized.get("author_display_name"),
            note_text=str(normalized["note_text"]),
            note_type=normalized.get("note_type"),
            is_internal=bool(normalized.get("is_internal", True)),
            created_at=normalized.get("created_at"),
        )

    def list_note_rows_by_program(
        self,
        program_id: str,
        include_internal: bool = True,
        newest_first: bool = True,
    ) -> list[NoteListRow]:
        clauses = ["n.program_id = %s"]
        params: list[Any] = [program_id]
        if not include_internal:
            clauses.append("n.is_internal = false")
        order = "desc" if newest_first else "asc"
        query = f"""
            select
                n.*,
                w.workstream_type,
                t.title as task_title,
                u.display_name as author_display_name
            from campaign_ops_notes n
            left join campaign_ops_workstreams w on w.id = n.workstream_id
            left join campaign_ops_tasks t on t.id = n.task_id
            left join campaign_ops_users u on u.id = n.author_user_id
            where {' and '.join(clauses)}
            order by n.created_at {order}
        """
        return [
            self._note_list_row_from_db(row)
            for row in self._fetch_raw_all(query, tuple(params))
        ]

    def create_reporting_request(
        self,
        actor_user_id: str | None = None,
        **kwargs: Any,
    ) -> ReportingRequestRecord:
        return self._write_returning(
            """
            insert into campaign_ops_reporting_requests (
                program_id, workstream_id, request_category, request_type, am_user_id,
                assigned_user_id, due_date, recap_date_with_client, recap_date_text,
                brief_url, brief_status_text, delivered, review_required,
                review_complete, approval_required, approved, questions_requested,
                special_requests, status, risk, waiting_on, completed_at,
                created_by_user_id
            )
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            returning *
            """,
            (
                kwargs["program_id"],
                kwargs.get("workstream_id"),
                kwargs["request_category"],
                require_text(kwargs.get("request_type"), "request_type"),
                kwargs["am_user_id"],
                kwargs.get("assigned_user_id"),
                kwargs.get("due_date"),
                kwargs.get("recap_date_with_client"),
                kwargs.get("recap_date_text"),
                kwargs.get("brief_url"),
                kwargs.get("brief_status_text"),
                bool(kwargs.get("delivered", False)),
                bool(kwargs.get("review_required", False)),
                bool(kwargs.get("review_complete", False)),
                bool(kwargs.get("approval_required", False)),
                bool(kwargs.get("approved", False)),
                kwargs.get("questions_requested"),
                kwargs.get("special_requests"),
                kwargs.get("status"),
                kwargs.get("risk"),
                kwargs.get("waiting_on"),
                kwargs.get("completed_at"),
                actor_user_id,
            ),
            ReportingRequestRecord,
        )

    def get_reporting_request(self, request_id: str) -> ReportingRequestRecord | None:
        return self._fetch_one(
            "select * from campaign_ops_reporting_requests where id = %s",
            (request_id,),
            ReportingRequestRecord,
        )

    def update_reporting_request(
        self,
        request_id: str,
        actor_user_id: str | None = None,
        **kwargs: Any,
    ) -> ReportingRequestRecord:
        return self._write_returning(
            """
            update campaign_ops_reporting_requests
            set
                program_id = %s,
                workstream_id = %s,
                request_category = %s,
                request_type = %s,
                am_user_id = %s,
                assigned_user_id = %s,
                due_date = %s,
                recap_date_with_client = %s,
                recap_date_text = %s,
                brief_url = %s,
                brief_status_text = %s,
                delivered = %s,
                review_required = %s,
                review_complete = %s,
                approval_required = %s,
                approved = %s,
                questions_requested = %s,
                special_requests = %s,
                status = %s,
                risk = %s,
                waiting_on = %s,
                completed_at = %s
            where id = %s
            returning *
            """,
            (
                kwargs["program_id"],
                kwargs.get("workstream_id"),
                kwargs["request_category"],
                require_text(kwargs.get("request_type"), "request_type"),
                kwargs["am_user_id"],
                kwargs.get("assigned_user_id"),
                kwargs.get("due_date"),
                kwargs.get("recap_date_with_client"),
                kwargs.get("recap_date_text"),
                kwargs.get("brief_url"),
                kwargs.get("brief_status_text"),
                bool(kwargs.get("delivered", False)),
                bool(kwargs.get("review_required", False)),
                bool(kwargs.get("review_complete", False)),
                bool(kwargs.get("approval_required", False)),
                bool(kwargs.get("approved", False)),
                kwargs.get("questions_requested"),
                kwargs.get("special_requests"),
                kwargs["status"],
                kwargs["risk"],
                kwargs.get("waiting_on"),
                kwargs.get("completed_at"),
                request_id,
            ),
            ReportingRequestRecord,
        )

    def deactivate_reporting_request(self, request_id: str) -> None:
        self._execute(
            """
            update campaign_ops_reporting_requests
            set is_active = false
            where id = %s and is_active = true
            """,
            (request_id,),
        )

    def reactivate_reporting_request(self, request_id: str) -> ReportingRequestRecord:
        return self._write_returning(
            """
            update campaign_ops_reporting_requests
            set is_active = true
            where id = %s and is_active = false
            returning *
            """,
            (request_id,),
            ReportingRequestRecord,
        )

    def _reporting_request_row_from_db(self, row: dict[str, Any]) -> ReportingRequestListRow:
        normalized = normalize_row(row)
        return ReportingRequestListRow(
            id=str(normalized["id"]),
            program_id=str(normalized["program_id"]),
            program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"),
            primary_workstream_type=normalized.get("primary_workstream_type"),
            request_category=str(normalized["request_category"]),
            request_type=str(normalized["request_type"]),
            am_user_id=str(normalized["am_user_id"]),
            am_display_name=str(normalized["am_display_name"]),
            assigned_user_id=normalize_id(normalized.get("assigned_user_id")),
            assigned_display_name=normalized.get("assigned_display_name"),
            workstream_id=normalize_id(normalized.get("workstream_id")),
            workstream_type=normalized.get("workstream_type"),
            due_date=normalized.get("due_date"),
            recap_date_with_client=normalized.get("recap_date_with_client"),
            recap_date_text=normalized.get("recap_date_text"),
            brief_url=normalized.get("brief_url"),
            brief_status_text=normalized.get("brief_status_text"),
            delivered=bool(normalized.get("delivered", False)),
            review_required=bool(normalized.get("review_required", False)),
            review_complete=bool(normalized.get("review_complete", False)),
            approval_required=bool(normalized.get("approval_required", False)),
            approved=bool(normalized.get("approved", False)),
            questions_requested=normalized.get("questions_requested"),
            special_requests=normalized.get("special_requests"),
            status=str(normalized["status"]),
            risk=str(normalized["risk"]),
            waiting_on=normalized.get("waiting_on"),
            completed_at=normalized.get("completed_at"),
            is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"),
            updated_at=normalized.get("updated_at"),
        )

    def list_reporting_requests(
        self,
        include_inactive: bool = False,
        program_id: str | None = None,
    ) -> list[ReportingRequestListRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_inactive:
            clauses.append("rr.is_active = true")
        if program_id:
            clauses.append("rr.program_id = %s")
            params.append(program_id)
        where_clause = "where " + " and ".join(clauses) if clauses else ""
        query = f"""
            select
                rr.*,
                p.program_name,
                p.primary_workstream_type,
                c.name as client_name,
                am.display_name as am_display_name,
                assigned.display_name as assigned_display_name,
                w.workstream_type
            from campaign_ops_reporting_requests rr
            join campaign_ops_programs p on p.id = rr.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            join campaign_ops_users am on am.id = rr.am_user_id
            left join campaign_ops_users assigned on assigned.id = rr.assigned_user_id
            left join campaign_ops_workstreams w on w.id = rr.workstream_id
            {where_clause}
            order by rr.due_date asc nulls last, rr.updated_at desc
        """
        return [
            self._reporting_request_row_from_db(row)
            for row in self._fetch_raw_all(query, tuple(params))
        ]

    def get_reporting_request_detail(self, request_id: str) -> ReportingRequestListRow | None:
        rows = [
            row for row in self.list_reporting_requests(include_inactive=True)
            if row.id == request_id
        ]
        return rows[0] if rows else None

    def list_requests_by_program(
        self,
        program_id: str,
        include_inactive: bool = False,
    ) -> list[ReportingRequestListRow]:
        return self.list_reporting_requests(include_inactive=include_inactive, program_id=program_id)

    def create_insights_project(
        self,
        actor_user_id: str | None = None,
        **kwargs: Any,
    ) -> InsightsProjectRecord:
        return self._write_returning(
            """
            insert into campaign_ops_insights_projects (
                program_id, workstream_id, job_number, project_title, insights_status,
                latest_update, total_program_cost, sample_size, budget, owner_user_id,
                created_by_user_id
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                kwargs["program_id"],
                kwargs.get("workstream_id"),
                kwargs.get("job_number"),
                require_text(kwargs.get("project_title"), "project_title"),
                kwargs.get("insights_status"),
                kwargs.get("latest_update"),
                kwargs.get("total_program_cost"),
                kwargs.get("sample_size"),
                kwargs.get("budget"),
                kwargs.get("owner_user_id"),
                actor_user_id,
            ),
            InsightsProjectRecord,
        )

    def get_insights_project(self, project_id: str) -> InsightsProjectRecord | None:
        return self._fetch_one(
            "select * from campaign_ops_insights_projects where id = %s",
            (project_id,),
            InsightsProjectRecord,
        )

    def get_insights_project_by_program(self, program_id: str) -> InsightsProjectRecord | None:
        return self._fetch_one(
            "select * from campaign_ops_insights_projects where program_id = %s",
            (program_id,),
            InsightsProjectRecord,
        )

    def update_insights_project(
        self,
        project_id: str,
        **kwargs: Any,
    ) -> InsightsProjectRecord:
        return self._write_returning(
            """
            update campaign_ops_insights_projects
            set
                workstream_id = %s,
                job_number = %s,
                project_title = %s,
                insights_status = %s,
                latest_update = %s,
                total_program_cost = %s,
                sample_size = %s,
                budget = %s,
                owner_user_id = %s
            where id = %s
            returning *
            """,
            (
                kwargs.get("workstream_id"),
                kwargs.get("job_number"),
                require_text(kwargs.get("project_title"), "project_title"),
                kwargs.get("insights_status"),
                kwargs.get("latest_update"),
                kwargs.get("total_program_cost"),
                kwargs.get("sample_size"),
                kwargs.get("budget"),
                kwargs.get("owner_user_id"),
                project_id,
            ),
            InsightsProjectRecord,
        )

    def deactivate_insights_project(self, project_id: str) -> None:
        self._execute(
            """
            update campaign_ops_insights_projects
            set is_active = false
            where id = %s and is_active = true
            """,
            (project_id,),
        )

    def reactivate_insights_project(self, project_id: str) -> InsightsProjectRecord:
        return self._write_returning(
            """
            update campaign_ops_insights_projects
            set is_active = true
            where id = %s and is_active = false
            returning *
            """,
            (project_id,),
            InsightsProjectRecord,
        )

    def _insights_portfolio_row_from_db(self, row: dict[str, Any]) -> InsightsPortfolioRow:
        normalized = normalize_row(row)
        return InsightsPortfolioRow(
            id=str(normalized["id"]),
            program_id=str(normalized["program_id"]),
            program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"),
            workstream_id=normalize_id(normalized.get("workstream_id")),
            project_title=str(normalized["project_title"]),
            job_number=normalized.get("job_number"),
            insights_status=normalized.get("insights_status"),
            latest_update=normalized.get("latest_update"),
            owner_user_id=normalize_id(normalized.get("owner_user_id")),
            owner_display_name=normalized.get("owner_display_name"),
            total_program_cost=normalized.get("total_program_cost"),
            sample_size=normalized.get("sample_size"),
            budget=normalized.get("budget"),
            program_status=str(normalized["program_status"]),
            program_risk=str(normalized["program_risk"]),
            next_milestone=normalized.get("next_milestone"),
            next_milestone_date=normalized.get("next_milestone_date"),
            tracksheet_url=normalized.get("tracksheet_url"),
            results_deck_url=normalized.get("results_deck_url"),
            raw_data_url=normalized.get("raw_data_url"),
            is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"),
            updated_at=normalized.get("updated_at"),
        )

    def list_insights_projects(self, include_inactive: bool = False) -> list[InsightsPortfolioRow]:
        clauses = [] if include_inactive else ["ip.is_active = true"]
        where_clause = "where " + " and ".join(clauses) if clauses else ""
        query = f"""
            with next_milestone as (
                select distinct on (m.program_id)
                    m.program_id,
                    m.title,
                    coalesce(m.target_date, m.start_date, m.end_date) as milestone_date
                from campaign_ops_milestones m
                where m.is_active = true
                  and m.status <> %s
                order by m.program_id, coalesce(m.target_date, m.start_date, m.end_date) asc nulls last, m.created_at asc
            ),
            resource_agg as (
                select
                    program_id,
                    max(url) filter (where resource_type = 'Tracksheet' and is_active = true) as tracksheet_url,
                    max(url) filter (where resource_type = 'Results Deck' and is_active = true) as results_deck_url,
                    max(url) filter (where resource_type in ('Raw Data', 'Raw Data Key') and is_active = true) as raw_data_url
                from campaign_ops_resources
                group by program_id
            )
            select
                ip.*,
                p.program_name,
                p.status as program_status,
                p.risk_level as program_risk,
                c.name as client_name,
                u.display_name as owner_display_name,
                nm.title as next_milestone,
                nm.milestone_date as next_milestone_date,
                ra.tracksheet_url,
                ra.results_deck_url,
                ra.raw_data_url
            from campaign_ops_insights_projects ip
            join campaign_ops_programs p on p.id = ip.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_users u on u.id = ip.owner_user_id
            left join next_milestone nm on nm.program_id = ip.program_id
            left join resource_agg ra on ra.program_id = ip.program_id
            {where_clause}
            order by ip.updated_at desc, ip.project_title asc
        """
        return [
            self._insights_portfolio_row_from_db(row)
            for row in self._fetch_raw_all(query, (TaskStatus.COMPLETED.value,))
        ]

    def get_insights_project_detail(self, project_id: str) -> InsightsPortfolioRow | None:
        return next((row for row in self.list_insights_projects(include_inactive=True) if row.id == project_id), None)

    def create_insights_objective(
        self,
        insights_project_id: str,
        objective_text: str,
        actor_user_id: str | None = None,
        sort_order: int = 0,
    ) -> InsightsObjectiveRecord:
        return self._write_returning(
            """
            insert into campaign_ops_insights_objectives (
                insights_project_id, objective_text, sort_order, created_by_user_id
            )
            values (%s, %s, %s, %s)
            returning *
            """,
            (insights_project_id, require_text(objective_text, "objective_text"), sort_order, actor_user_id),
            InsightsObjectiveRecord,
        )

    def list_insights_objectives(
        self,
        insights_project_id: str,
        include_inactive: bool = False,
    ) -> list[InsightsObjectiveRecord]:
        clauses = ["insights_project_id = %s"]
        params: list[Any] = [insights_project_id]
        if not include_inactive:
            clauses.append("is_active = true")
        return self._fetch_all(
            f"""
            select * from campaign_ops_insights_objectives
            where {' and '.join(clauses)}
            order by sort_order asc, created_at asc
            """,
            tuple(params),
            InsightsObjectiveRecord,
        )

    def update_insights_objective(
        self,
        objective_id: str,
        objective_text: str,
        sort_order: int,
    ) -> InsightsObjectiveRecord:
        return self._write_returning(
            """
            update campaign_ops_insights_objectives
            set objective_text = %s, sort_order = %s
            where id = %s
            returning *
            """,
            (require_text(objective_text, "objective_text"), sort_order, objective_id),
            InsightsObjectiveRecord,
        )

    def deactivate_insights_objective(self, objective_id: str) -> None:
        self._execute(
            """
            update campaign_ops_insights_objectives
            set is_active = false
            where id = %s and is_active = true
            """,
            (objective_id,),
        )

    def reactivate_insights_objective(self, objective_id: str) -> InsightsObjectiveRecord:
        return self._write_returning(
            """
            update campaign_ops_insights_objectives
            set is_active = true
            where id = %s and is_active = false
            returning *
            """,
            (objective_id,),
            InsightsObjectiveRecord,
        )

    def create_retail_media_campaign(self, actor_user_id: str | None = None, **kwargs: Any) -> RetailMediaCampaignRecord:
        return self._write_returning(
            """
            insert into campaign_ops_retail_media_campaigns (
                program_id, workstream_id, campaign_title, retail_media_status,
                latest_update, waiting_on, owner_user_id, launch_date, wrap_date,
                reporting_cadence, overall_budget, total_spend, is_paused,
                pause_reason, created_by_user_id
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                kwargs["program_id"],
                kwargs.get("workstream_id"),
                require_text(kwargs.get("campaign_title"), "campaign_title"),
                kwargs.get("retail_media_status"),
                kwargs.get("latest_update"),
                kwargs.get("waiting_on"),
                kwargs.get("owner_user_id"),
                kwargs.get("launch_date"),
                kwargs.get("wrap_date"),
                kwargs.get("reporting_cadence"),
                kwargs.get("overall_budget"),
                kwargs.get("total_spend"),
                bool(kwargs.get("is_paused", False)),
                kwargs.get("pause_reason"),
                actor_user_id,
            ),
            RetailMediaCampaignRecord,
        )

    def get_retail_media_campaign(self, campaign_id: str) -> RetailMediaCampaignRecord | None:
        return self._fetch_one(
            "select * from campaign_ops_retail_media_campaigns where id = %s",
            (campaign_id,),
            RetailMediaCampaignRecord,
        )

    def get_active_retail_media_campaign_by_title(
        self,
        program_id: str,
        campaign_title: str,
    ) -> RetailMediaCampaignRecord | None:
        return self._fetch_one(
            """
            select * from campaign_ops_retail_media_campaigns
            where program_id = %s and lower(campaign_title) = lower(%s) and is_active = true
            """,
            (program_id, campaign_title),
            RetailMediaCampaignRecord,
        )

    def update_retail_media_campaign(self, campaign_id: str, **kwargs: Any) -> RetailMediaCampaignRecord:
        return self._write_returning(
            """
            update campaign_ops_retail_media_campaigns
            set
                workstream_id = %s,
                campaign_title = %s,
                retail_media_status = %s,
                latest_update = %s,
                waiting_on = %s,
                owner_user_id = %s,
                launch_date = %s,
                wrap_date = %s,
                reporting_cadence = %s,
                overall_budget = %s,
                total_spend = %s,
                is_paused = %s,
                pause_reason = %s
            where id = %s
            returning *
            """,
            (
                kwargs.get("workstream_id"),
                require_text(kwargs.get("campaign_title"), "campaign_title"),
                kwargs.get("retail_media_status"),
                kwargs.get("latest_update"),
                kwargs.get("waiting_on"),
                kwargs.get("owner_user_id"),
                kwargs.get("launch_date"),
                kwargs.get("wrap_date"),
                kwargs.get("reporting_cadence"),
                kwargs.get("overall_budget"),
                kwargs.get("total_spend"),
                bool(kwargs.get("is_paused", False)),
                kwargs.get("pause_reason"),
                campaign_id,
            ),
            RetailMediaCampaignRecord,
        )

    def deactivate_retail_media_campaign(self, campaign_id: str) -> None:
        self._execute(
            "update campaign_ops_retail_media_campaigns set is_active = false where id = %s and is_active = true",
            (campaign_id,),
        )

    def reactivate_retail_media_campaign(self, campaign_id: str) -> RetailMediaCampaignRecord:
        return self._write_returning(
            "update campaign_ops_retail_media_campaigns set is_active = true where id = %s and is_active = false returning *",
            (campaign_id,),
            RetailMediaCampaignRecord,
        )

    def _retail_media_portfolio_row_from_db(self, row: dict[str, Any]) -> RetailMediaPortfolioRow:
        normalized = normalize_row(row)
        return RetailMediaPortfolioRow(
            id=str(normalized["id"]),
            program_id=str(normalized["program_id"]),
            program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"),
            workstream_id=normalize_id(normalized.get("workstream_id")),
            campaign_title=str(normalized["campaign_title"]),
            retail_media_status=normalized.get("retail_media_status"),
            latest_update=normalized.get("latest_update"),
            waiting_on=normalized.get("waiting_on"),
            owner_user_id=normalize_id(normalized.get("owner_user_id")),
            owner_display_name=normalized.get("owner_display_name"),
            launch_date=normalized.get("launch_date"),
            wrap_date=normalized.get("wrap_date"),
            reporting_cadence=normalized.get("reporting_cadence"),
            overall_budget=normalized.get("overall_budget"),
            total_spend=normalized.get("total_spend"),
            channel_budget_total=normalized.get("channel_budget_total"),
            channel_spend_total=normalized.get("channel_spend_total"),
            channel_mix=normalize_optional_list(normalized.get("channel_mix")),
            program_status=str(normalized["program_status"]),
            program_risk=str(normalized["program_risk"]),
            next_milestone=normalized.get("next_milestone"),
            next_milestone_date=normalized.get("next_milestone_date"),
            tracksheet_url=normalized.get("tracksheet_url"),
            budget_tracker_url=normalized.get("budget_tracker_url"),
            optimization_log_url=normalized.get("optimization_log_url"),
            is_paused=bool(normalized.get("is_paused", False)),
            pause_reason=normalized.get("pause_reason"),
            is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"),
            updated_at=normalized.get("updated_at"),
        )

    def list_retail_media_campaigns(self, include_inactive: bool = False) -> list[RetailMediaPortfolioRow]:
        clauses = [] if include_inactive else ["rm.is_active = true"]
        where_clause = "where " + " and ".join(clauses) if clauses else ""
        query = f"""
            with channel_agg as (
                select
                    retail_media_campaign_id,
                    array_agg(channel_type order by channel_type) filter (where is_active = true) as channel_mix,
                    sum(budget) filter (where is_active = true) as channel_budget_total,
                    sum(spend_to_date) filter (where is_active = true) as channel_spend_total
                from campaign_ops_retail_media_channels
                group by retail_media_campaign_id
            ),
            next_milestone as (
                select distinct on (m.program_id)
                    m.program_id,
                    m.title,
                    coalesce(m.target_date, m.start_date, m.end_date) as milestone_date
                from campaign_ops_milestones m
                where m.is_active = true and m.status <> %s
                order by m.program_id, coalesce(m.target_date, m.start_date, m.end_date) asc nulls last, m.created_at asc
            ),
            resource_agg as (
                select
                    program_id,
                    max(url) filter (where resource_type in ('Tracksheet', 'Program Tracksheet') and is_active = true) as tracksheet_url,
                    max(url) filter (where resource_type = 'Budget Tracker' and is_active = true) as budget_tracker_url,
                    max(url) filter (where resource_type = 'Optimization Log' and is_active = true) as optimization_log_url
                from campaign_ops_resources
                group by program_id
            )
            select
                rm.*,
                p.program_name,
                p.status as program_status,
                p.risk_level as program_risk,
                c.name as client_name,
                u.display_name as owner_display_name,
                ca.channel_mix,
                ca.channel_budget_total,
                ca.channel_spend_total,
                nm.title as next_milestone,
                nm.milestone_date as next_milestone_date,
                ra.tracksheet_url,
                ra.budget_tracker_url,
                ra.optimization_log_url
            from campaign_ops_retail_media_campaigns rm
            join campaign_ops_programs p on p.id = rm.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_users u on u.id = rm.owner_user_id
            left join channel_agg ca on ca.retail_media_campaign_id = rm.id
            left join next_milestone nm on nm.program_id = rm.program_id
            left join resource_agg ra on ra.program_id = rm.program_id
            {where_clause}
            order by rm.updated_at desc, rm.campaign_title asc
        """
        return [
            self._retail_media_portfolio_row_from_db(row)
            for row in self._fetch_raw_all(query, (TaskStatus.COMPLETED.value,))
        ]

    def get_retail_media_campaign_detail(self, campaign_id: str) -> RetailMediaPortfolioRow | None:
        return next((row for row in self.list_retail_media_campaigns(include_inactive=True) if row.id == campaign_id), None)

    def create_retail_media_channel(self, retail_media_campaign_id: str, channel_type: str, **kwargs: Any) -> RetailMediaChannelRecord:
        return self._write_returning(
            """
            insert into campaign_ops_retail_media_channels (
                retail_media_campaign_id, channel_type, platform_name, status,
                budget, spend_to_date, launch_date, end_date, reporting_requirement
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                retail_media_campaign_id,
                require_text(channel_type, "channel_type"),
                kwargs.get("platform_name"),
                kwargs.get("status"),
                kwargs.get("budget"),
                kwargs.get("spend_to_date"),
                kwargs.get("launch_date"),
                kwargs.get("end_date"),
                kwargs.get("reporting_requirement"),
            ),
            RetailMediaChannelRecord,
        )

    def list_retail_media_channels(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaChannelRecord]:
        clauses = ["retail_media_campaign_id = %s"]
        params: list[Any] = [retail_media_campaign_id]
        if not include_inactive:
            clauses.append("is_active = true")
        return self._fetch_all(
            f"select * from campaign_ops_retail_media_channels where {' and '.join(clauses)} order by channel_type asc, created_at asc",
            tuple(params),
            RetailMediaChannelRecord,
        )

    def update_retail_media_channel(self, channel_id: str, **kwargs: Any) -> RetailMediaChannelRecord:
        return self._write_returning(
            """
            update campaign_ops_retail_media_channels
            set channel_type = %s, platform_name = %s, status = %s, budget = %s,
                spend_to_date = %s, launch_date = %s, end_date = %s, reporting_requirement = %s
            where id = %s
            returning *
            """,
            (
                require_text(kwargs.get("channel_type"), "channel_type"),
                kwargs.get("platform_name"),
                kwargs.get("status"),
                kwargs.get("budget"),
                kwargs.get("spend_to_date"),
                kwargs.get("launch_date"),
                kwargs.get("end_date"),
                kwargs.get("reporting_requirement"),
                channel_id,
            ),
            RetailMediaChannelRecord,
        )

    def deactivate_retail_media_channel(self, channel_id: str) -> None:
        self._execute("update campaign_ops_retail_media_channels set is_active = false where id = %s and is_active = true", (channel_id,))

    def reactivate_retail_media_channel(self, channel_id: str) -> RetailMediaChannelRecord:
        return self._write_returning("update campaign_ops_retail_media_channels set is_active = true where id = %s and is_active = false returning *", (channel_id,), RetailMediaChannelRecord)

    def create_retail_media_activation(self, retail_media_campaign_id: str, activation_name: str, **kwargs: Any) -> RetailMediaActivationRecord:
        return self._write_returning(
            """
            insert into campaign_ops_retail_media_activations (
                retail_media_campaign_id, channel_id, activation_name, activation_type,
                status, start_date, end_date, hard_deadline, waiting_on, latest_update, completed_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                retail_media_campaign_id,
                kwargs.get("channel_id"),
                require_text(activation_name, "activation_name"),
                kwargs.get("activation_type"),
                kwargs.get("status"),
                kwargs.get("start_date"),
                kwargs.get("end_date"),
                bool(kwargs.get("hard_deadline", False)),
                kwargs.get("waiting_on"),
                kwargs.get("latest_update"),
                kwargs.get("completed_at"),
            ),
            RetailMediaActivationRecord,
        )

    def list_retail_media_activations(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaActivationRecord]:
        clauses = ["retail_media_campaign_id = %s"]
        params: list[Any] = [retail_media_campaign_id]
        if not include_inactive:
            clauses.append("is_active = true")
        return self._fetch_all(
            f"select * from campaign_ops_retail_media_activations where {' and '.join(clauses)} order by coalesce(start_date, end_date) asc nulls last, created_at asc",
            tuple(params),
            RetailMediaActivationRecord,
        )

    def update_retail_media_activation(self, activation_id: str, **kwargs: Any) -> RetailMediaActivationRecord:
        return self._write_returning(
            """
            update campaign_ops_retail_media_activations
            set channel_id = %s, activation_name = %s, activation_type = %s, status = %s,
                start_date = %s, end_date = %s, hard_deadline = %s, waiting_on = %s,
                latest_update = %s, completed_at = %s
            where id = %s
            returning *
            """,
            (
                kwargs.get("channel_id"),
                require_text(kwargs.get("activation_name"), "activation_name"),
                kwargs.get("activation_type"),
                kwargs.get("status"),
                kwargs.get("start_date"),
                kwargs.get("end_date"),
                bool(kwargs.get("hard_deadline", False)),
                kwargs.get("waiting_on"),
                kwargs.get("latest_update"),
                kwargs.get("completed_at"),
                activation_id,
            ),
            RetailMediaActivationRecord,
        )

    def deactivate_retail_media_activation(self, activation_id: str) -> None:
        self._execute("update campaign_ops_retail_media_activations set is_active = false where id = %s and is_active = true", (activation_id,))

    def reactivate_retail_media_activation(self, activation_id: str) -> RetailMediaActivationRecord:
        return self._write_returning("update campaign_ops_retail_media_activations set is_active = true where id = %s and is_active = false returning *", (activation_id,), RetailMediaActivationRecord)

    def create_retail_media_creative(self, retail_media_campaign_id: str, creative_name: str, **kwargs: Any) -> RetailMediaCreativeRecord:
        return self._write_returning(
            """
            insert into campaign_ops_retail_media_creative_items (
                retail_media_campaign_id, channel_id, creative_name, creative_type,
                approval_status, submission_status, platform_status, due_date,
                submitted_date, approved_date, notes
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                retail_media_campaign_id,
                kwargs.get("channel_id"),
                require_text(creative_name, "creative_name"),
                kwargs.get("creative_type"),
                kwargs.get("approval_status"),
                kwargs.get("submission_status"),
                kwargs.get("platform_status"),
                kwargs.get("due_date"),
                kwargs.get("submitted_date"),
                kwargs.get("approved_date"),
                kwargs.get("notes"),
            ),
            RetailMediaCreativeRecord,
        )

    def list_retail_media_creative(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaCreativeRecord]:
        clauses = ["retail_media_campaign_id = %s"]
        params: list[Any] = [retail_media_campaign_id]
        if not include_inactive:
            clauses.append("is_active = true")
        return self._fetch_all(
            f"select * from campaign_ops_retail_media_creative_items where {' and '.join(clauses)} order by due_date asc nulls last, created_at asc",
            tuple(params),
            RetailMediaCreativeRecord,
        )

    def update_retail_media_creative(self, creative_id: str, **kwargs: Any) -> RetailMediaCreativeRecord:
        return self._write_returning(
            """
            update campaign_ops_retail_media_creative_items
            set channel_id = %s, creative_name = %s, creative_type = %s,
                approval_status = %s, submission_status = %s, platform_status = %s,
                due_date = %s, submitted_date = %s, approved_date = %s, notes = %s
            where id = %s
            returning *
            """,
            (
                kwargs.get("channel_id"),
                require_text(kwargs.get("creative_name"), "creative_name"),
                kwargs.get("creative_type"),
                kwargs.get("approval_status"),
                kwargs.get("submission_status"),
                kwargs.get("platform_status"),
                kwargs.get("due_date"),
                kwargs.get("submitted_date"),
                kwargs.get("approved_date"),
                kwargs.get("notes"),
                creative_id,
            ),
            RetailMediaCreativeRecord,
        )

    def deactivate_retail_media_creative(self, creative_id: str) -> None:
        self._execute("update campaign_ops_retail_media_creative_items set is_active = false where id = %s and is_active = true", (creative_id,))

    def reactivate_retail_media_creative(self, creative_id: str) -> RetailMediaCreativeRecord:
        return self._write_returning("update campaign_ops_retail_media_creative_items set is_active = true where id = %s and is_active = false returning *", (creative_id,), RetailMediaCreativeRecord)

    def create_retail_media_optimization(self, retail_media_campaign_id: str, update_date: Any, update_text: str, actor_user_id: str | None = None, **kwargs: Any) -> RetailMediaOptimizationRecord:
        return self._write_returning(
            """
            insert into campaign_ops_retail_media_optimization_updates (
                retail_media_campaign_id, channel_id, update_date, update_text,
                optimization_type, created_by_user_id
            )
            values (%s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                retail_media_campaign_id,
                kwargs.get("channel_id"),
                update_date,
                require_text(update_text, "update_text"),
                kwargs.get("optimization_type"),
                actor_user_id,
            ),
            RetailMediaOptimizationRecord,
        )

    def list_retail_media_optimizations(self, retail_media_campaign_id: str, include_inactive: bool = False) -> list[RetailMediaOptimizationRecord]:
        clauses = ["retail_media_campaign_id = %s"]
        params: list[Any] = [retail_media_campaign_id]
        if not include_inactive:
            clauses.append("is_active = true")
        return self._fetch_all(
            f"select * from campaign_ops_retail_media_optimization_updates where {' and '.join(clauses)} order by update_date desc, created_at desc",
            tuple(params),
            RetailMediaOptimizationRecord,
        )

    def update_retail_media_optimization(self, optimization_id: str, **kwargs: Any) -> RetailMediaOptimizationRecord:
        return self._write_returning(
            """
            update campaign_ops_retail_media_optimization_updates
            set channel_id = %s, update_date = %s, update_text = %s, optimization_type = %s
            where id = %s
            returning *
            """,
            (
                kwargs.get("channel_id"),
                kwargs.get("update_date"),
                require_text(kwargs.get("update_text"), "update_text"),
                kwargs.get("optimization_type"),
                optimization_id,
            ),
            RetailMediaOptimizationRecord,
        )

    def deactivate_retail_media_optimization(self, optimization_id: str) -> None:
        self._execute("update campaign_ops_retail_media_optimization_updates set is_active = false where id = %s and is_active = true", (optimization_id,))

    def reactivate_retail_media_optimization(self, optimization_id: str) -> RetailMediaOptimizationRecord:
        return self._write_returning("update campaign_ops_retail_media_optimization_updates set is_active = true where id = %s and is_active = false returning *", (optimization_id,), RetailMediaOptimizationRecord)

    def create_content_program(self, actor_user_id: str | None = None, **kwargs: Any) -> ContentProgramRecord:
        return self._write_returning(
            """
            insert into campaign_ops_content_programs (
                program_id, workstream_id, content_program_title, content_status,
                latest_update, waiting_on, owner_user_id, total_sku_count,
                default_graphics_per_sku, monitoring_start_date, maintenance_end_date,
                reporting_cadence, is_invoiced, invoice_status, created_by_user_id
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                kwargs["program_id"], kwargs.get("workstream_id"), require_text(kwargs.get("content_program_title"), "content_program_title"),
                kwargs.get("content_status"), kwargs.get("latest_update"), kwargs.get("waiting_on"), kwargs.get("owner_user_id"),
                kwargs.get("total_sku_count"), kwargs.get("default_graphics_per_sku"), kwargs.get("monitoring_start_date"),
                kwargs.get("maintenance_end_date"), kwargs.get("reporting_cadence"), bool(kwargs.get("is_invoiced", False)),
                kwargs.get("invoice_status"), actor_user_id,
            ),
            ContentProgramRecord,
        )

    def get_content_program(self, content_program_id: str) -> ContentProgramRecord | None:
        return self._fetch_one("select * from campaign_ops_content_programs where id = %s", (content_program_id,), ContentProgramRecord)

    def get_active_content_program_by_title(self, program_id: str, title: str) -> ContentProgramRecord | None:
        return self._fetch_one(
            "select * from campaign_ops_content_programs where program_id = %s and lower(content_program_title) = lower(%s) and is_active = true",
            (program_id, title),
            ContentProgramRecord,
        )

    def update_content_program(self, content_program_id: str, **kwargs: Any) -> ContentProgramRecord:
        return self._write_returning(
            """
            update campaign_ops_content_programs
            set workstream_id=%s, content_program_title=%s, content_status=%s,
                latest_update=%s, waiting_on=%s, owner_user_id=%s,
                total_sku_count=%s, default_graphics_per_sku=%s,
                monitoring_start_date=%s, maintenance_end_date=%s,
                reporting_cadence=%s, is_invoiced=%s, invoice_status=%s
            where id = %s
            returning *
            """,
            (
                kwargs.get("workstream_id"), require_text(kwargs.get("content_program_title"), "content_program_title"),
                kwargs.get("content_status"), kwargs.get("latest_update"), kwargs.get("waiting_on"), kwargs.get("owner_user_id"),
                kwargs.get("total_sku_count"), kwargs.get("default_graphics_per_sku"), kwargs.get("monitoring_start_date"),
                kwargs.get("maintenance_end_date"), kwargs.get("reporting_cadence"), bool(kwargs.get("is_invoiced", False)),
                kwargs.get("invoice_status"), content_program_id,
            ),
            ContentProgramRecord,
        )

    def deactivate_content_program(self, content_program_id: str) -> None:
        self._execute("update campaign_ops_content_programs set is_active = false where id = %s and is_active = true", (content_program_id,))

    def reactivate_content_program(self, content_program_id: str) -> ContentProgramRecord:
        return self._write_returning("update campaign_ops_content_programs set is_active = true where id = %s and is_active = false returning *", (content_program_id,), ContentProgramRecord)

    def _content_portfolio_row_from_db(self, row: dict[str, Any]) -> ContentPortfolioRow:
        normalized = normalize_row(row)
        return ContentPortfolioRow(
            id=str(normalized["id"]), program_id=str(normalized["program_id"]), program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"), workstream_id=normalize_id(normalized.get("workstream_id")),
            content_program_title=str(normalized["content_program_title"]), content_status=normalized.get("content_status"),
            latest_update=normalized.get("latest_update"), waiting_on=normalized.get("waiting_on"),
            owner_user_id=normalize_id(normalized.get("owner_user_id")), owner_display_name=normalized.get("owner_display_name"),
            total_sku_count=normalized.get("total_sku_count"), default_graphics_per_sku=normalized.get("default_graphics_per_sku"),
            monitoring_start_date=normalized.get("monitoring_start_date"), maintenance_end_date=normalized.get("maintenance_end_date"),
            reporting_cadence=normalized.get("reporting_cadence"), is_invoiced=bool(normalized.get("is_invoiced", False)),
            invoice_status=normalized.get("invoice_status"), group_names=normalize_optional_list(normalized.get("group_names")),
            group_expected_sku_total=normalized.get("group_expected_sku_total"), active_sku_count=int(normalized.get("active_sku_count") or 0),
            delivered_count=int(normalized.get("delivered_count") or 0), live_count=int(normalized.get("live_count") or 0),
            issue_count=int(normalized.get("issue_count") or 0), program_status=str(normalized["program_status"]),
            program_risk=str(normalized["program_risk"]), next_milestone=normalized.get("next_milestone"),
            next_milestone_date=normalized.get("next_milestone_date"), sku_list_url=normalized.get("sku_list_url"),
            tracksheet_url=normalized.get("tracksheet_url"), creative_request_deck_url=normalized.get("creative_request_deck_url"),
            pdp_request_deck_url=normalized.get("pdp_request_deck_url"), keyword_insights_url=normalized.get("keyword_insights_url"),
            photography_url=normalized.get("photography_url"), is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"), updated_at=normalized.get("updated_at"),
        )

    def list_content_programs(self, include_inactive: bool = False) -> list[ContentPortfolioRow]:
        where_clause = "" if include_inactive else "where cp.is_active = true"
        query = f"""
            with group_agg as (
                select content_program_id, array_agg(group_name order by sort_order, group_name) filter (where is_active = true) as group_names,
                       sum(expected_sku_count) filter (where is_active = true) as group_expected_sku_total
                from campaign_ops_content_sku_groups group by content_program_id
            ), sku_agg as (
                select content_program_id,
                       count(*) filter (where is_active = true) as active_sku_count,
                       count(*) filter (where is_active = true and publication_status = 'live') as live_count,
                       count(*) filter (where is_active = true and issue_status is not null and issue_status <> '') as issue_count
                from campaign_ops_content_skus group by content_program_id
            ), deliverable_agg as (
                select content_program_id, count(*) filter (where is_active = true and status in ('delivered','approved','complete')) as delivered_count
                from campaign_ops_content_deliverables group by content_program_id
            ), next_milestone as (
                select distinct on (m.program_id) m.program_id, m.title, coalesce(m.target_date, m.start_date, m.end_date) as milestone_date
                from campaign_ops_milestones m where m.is_active = true and m.status <> %s
                order by m.program_id, coalesce(m.target_date, m.start_date, m.end_date) asc nulls last, m.created_at asc
            ), resource_agg as (
                select program_id,
                    max(url) filter (where resource_type = 'SKU List' and is_active = true) as sku_list_url,
                    max(url) filter (where resource_type = 'Tracksheet' and is_active = true) as tracksheet_url,
                    max(url) filter (where resource_type = 'Creative Request Deck' and is_active = true) as creative_request_deck_url,
                    max(url) filter (where resource_type = 'PDP Request Deck' and is_active = true) as pdp_request_deck_url,
                    max(url) filter (where resource_type = 'Keyword Insights' and is_active = true) as keyword_insights_url,
                    max(url) filter (where resource_type = 'Photography Folder' and is_active = true) as photography_url
                from campaign_ops_resources group by program_id
            )
            select cp.*, p.program_name, p.status as program_status, p.risk_level as program_risk, c.name as client_name,
                   u.display_name as owner_display_name, ga.group_names, ga.group_expected_sku_total,
                   coalesce(sa.active_sku_count, 0) as active_sku_count, coalesce(sa.live_count, 0) as live_count,
                   coalesce(sa.issue_count, 0) as issue_count, coalesce(da.delivered_count, 0) as delivered_count,
                   nm.title as next_milestone, nm.milestone_date as next_milestone_date,
                   ra.sku_list_url, ra.tracksheet_url, ra.creative_request_deck_url, ra.pdp_request_deck_url,
                   ra.keyword_insights_url, ra.photography_url
            from campaign_ops_content_programs cp
            join campaign_ops_programs p on p.id = cp.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_users u on u.id = cp.owner_user_id
            left join group_agg ga on ga.content_program_id = cp.id
            left join sku_agg sa on sa.content_program_id = cp.id
            left join deliverable_agg da on da.content_program_id = cp.id
            left join next_milestone nm on nm.program_id = cp.program_id
            left join resource_agg ra on ra.program_id = cp.program_id
            {where_clause}
            order by cp.updated_at desc, cp.content_program_title asc
        """
        return [self._content_portfolio_row_from_db(row) for row in self._fetch_raw_all(query, (TaskStatus.COMPLETED.value,))]

    def get_content_program_detail(self, content_program_id: str) -> ContentPortfolioRow | None:
        return next((row for row in self.list_content_programs(include_inactive=True) if row.id == content_program_id), None)

    def _create_content_child(self, table: str, model: type, fields: list[str], values: tuple[Any, ...]) -> Any:
        columns = ", ".join(fields)
        placeholders = ", ".join(["%s"] * len(fields))
        return self._write_returning(f"insert into {table} ({columns}) values ({placeholders}) returning *", values, model)

    def _update_content_child(self, table: str, model: type, record_id: str, fields: list[str], values: tuple[Any, ...]) -> Any:
        assignments = ", ".join(f"{field} = %s" for field in fields)
        return self._write_returning(f"update {table} set {assignments} where id = %s returning *", (*values, record_id), model)

    def create_content_sku_group(self, content_program_id: str, group_name: str, **kwargs: Any) -> ContentSkuGroupRecord:
        fields = ["content_program_id", "group_name", "brand_name", "expected_sku_count", "graphics_per_sku", "status", "latest_update", "waiting_on", "sort_order"]
        return self._create_content_child("campaign_ops_content_sku_groups", ContentSkuGroupRecord, fields, (content_program_id, require_text(group_name, "group_name"), kwargs.get("brand_name"), kwargs.get("expected_sku_count"), kwargs.get("graphics_per_sku"), kwargs.get("status"), kwargs.get("latest_update"), kwargs.get("waiting_on"), kwargs.get("sort_order", 0)))

    def list_content_sku_groups(self, content_program_id: str, include_inactive: bool = False) -> list[ContentSkuGroupRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_content_sku_groups where content_program_id = %s {clause} order by sort_order asc, group_name asc", (content_program_id,), ContentSkuGroupRecord)

    def update_content_sku_group(self, group_id: str, **kwargs: Any) -> ContentSkuGroupRecord:
        fields = ["group_name", "brand_name", "expected_sku_count", "graphics_per_sku", "status", "latest_update", "waiting_on", "sort_order"]
        return self._update_content_child("campaign_ops_content_sku_groups", ContentSkuGroupRecord, group_id, fields, tuple(kwargs.get(f) for f in fields))

    def deactivate_content_sku_group(self, group_id: str) -> None:
        self._execute("update campaign_ops_content_sku_groups set is_active = false where id = %s and is_active = true", (group_id,))

    def reactivate_content_sku_group(self, group_id: str) -> ContentSkuGroupRecord:
        return self._write_returning("update campaign_ops_content_sku_groups set is_active = true where id = %s and is_active = false returning *", (group_id,), ContentSkuGroupRecord)

    def create_content_sku(self, content_program_id: str, product_name: str, **kwargs: Any) -> ContentSkuRecord:
        fields = ["content_program_id", "sku_group_id", "sku_code", "product_name", "retailer_sku", "upc", "variant", "content_status", "copy_status", "attribute_status", "graphics_status", "submission_status", "publication_status", "live_url", "last_checked_at", "issue_status", "waiting_on", "maintenance_required"]
        return self._create_content_child("campaign_ops_content_skus", ContentSkuRecord, fields, (content_program_id, kwargs.get("sku_group_id"), kwargs.get("sku_code"), require_text(product_name, "product_name"), kwargs.get("retailer_sku"), kwargs.get("upc"), kwargs.get("variant"), kwargs.get("content_status"), kwargs.get("copy_status"), kwargs.get("attribute_status"), kwargs.get("graphics_status"), kwargs.get("submission_status"), kwargs.get("publication_status"), kwargs.get("live_url"), kwargs.get("last_checked_at"), kwargs.get("issue_status"), kwargs.get("waiting_on"), bool(kwargs.get("maintenance_required", False))))

    def get_content_sku(self, sku_id: str) -> ContentSkuRecord | None:
        return self._fetch_one("select * from campaign_ops_content_skus where id = %s", (sku_id,), ContentSkuRecord)

    def list_content_skus(self, content_program_id: str, include_inactive: bool = False) -> list[ContentSkuRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_content_skus where content_program_id = %s {clause} order by product_name asc", (content_program_id,), ContentSkuRecord)

    def update_content_sku(self, sku_id: str, **kwargs: Any) -> ContentSkuRecord:
        fields = ["sku_group_id", "sku_code", "product_name", "retailer_sku", "upc", "variant", "content_status", "copy_status", "attribute_status", "graphics_status", "submission_status", "publication_status", "live_url", "last_checked_at", "issue_status", "waiting_on", "maintenance_required"]
        return self._update_content_child("campaign_ops_content_skus", ContentSkuRecord, sku_id, fields, tuple(kwargs.get(f) for f in fields))

    def deactivate_content_sku(self, sku_id: str) -> None:
        self._execute("update campaign_ops_content_skus set is_active = false where id = %s and is_active = true", (sku_id,))

    def reactivate_content_sku(self, sku_id: str) -> ContentSkuRecord:
        return self._write_returning("update campaign_ops_content_skus set is_active = true where id = %s and is_active = false returning *", (sku_id,), ContentSkuRecord)

    def create_content_deliverable(self, content_program_id: str, deliverable_name: str, **kwargs: Any) -> ContentDeliverableRecord:
        fields = ["content_program_id", "sku_group_id", "sku_id", "deliverable_name", "deliverable_type", "status", "approval_status", "due_date", "delivered_date", "approved_date", "required_quantity", "completed_quantity", "waiting_on", "notes"]
        return self._create_content_child("campaign_ops_content_deliverables", ContentDeliverableRecord, fields, (content_program_id, kwargs.get("sku_group_id"), kwargs.get("sku_id"), require_text(deliverable_name, "deliverable_name"), kwargs.get("deliverable_type"), kwargs.get("status"), kwargs.get("approval_status"), kwargs.get("due_date"), kwargs.get("delivered_date"), kwargs.get("approved_date"), kwargs.get("required_quantity"), kwargs.get("completed_quantity"), kwargs.get("waiting_on"), kwargs.get("notes")))

    def list_content_deliverables(self, content_program_id: str, include_inactive: bool = False) -> list[ContentDeliverableRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_content_deliverables where content_program_id = %s {clause} order by due_date asc nulls last, created_at asc", (content_program_id,), ContentDeliverableRecord)

    def update_content_deliverable(self, deliverable_id: str, **kwargs: Any) -> ContentDeliverableRecord:
        fields = ["sku_group_id", "sku_id", "deliverable_name", "deliverable_type", "status", "approval_status", "due_date", "delivered_date", "approved_date", "required_quantity", "completed_quantity", "waiting_on", "notes"]
        return self._update_content_child("campaign_ops_content_deliverables", ContentDeliverableRecord, deliverable_id, fields, tuple(kwargs.get(f) for f in fields))

    def deactivate_content_deliverable(self, deliverable_id: str) -> None:
        self._execute("update campaign_ops_content_deliverables set is_active = false where id = %s and is_active = true", (deliverable_id,))

    def reactivate_content_deliverable(self, deliverable_id: str) -> ContentDeliverableRecord:
        return self._write_returning("update campaign_ops_content_deliverables set is_active = true where id = %s and is_active = false returning *", (deliverable_id,), ContentDeliverableRecord)

    def create_content_submission(self, content_program_id: str, **kwargs: Any) -> ContentSubmissionRecord:
        fields = ["content_program_id", "sku_group_id", "sku_id", "retailer_or_platform", "submission_type", "status", "submitted_date", "approved_date", "published_date", "expected_live_date", "live_url", "issue_text", "waiting_on"]
        return self._create_content_child("campaign_ops_content_submissions", ContentSubmissionRecord, fields, (content_program_id, kwargs.get("sku_group_id"), kwargs.get("sku_id"), kwargs.get("retailer_or_platform"), kwargs.get("submission_type"), kwargs.get("status"), kwargs.get("submitted_date"), kwargs.get("approved_date"), kwargs.get("published_date"), kwargs.get("expected_live_date"), kwargs.get("live_url"), kwargs.get("issue_text"), kwargs.get("waiting_on")))

    def list_content_submissions(self, content_program_id: str, include_inactive: bool = False) -> list[ContentSubmissionRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_content_submissions where content_program_id = %s {clause} order by expected_live_date asc nulls last, created_at asc", (content_program_id,), ContentSubmissionRecord)

    def update_content_submission(self, submission_id: str, **kwargs: Any) -> ContentSubmissionRecord:
        fields = ["sku_group_id", "sku_id", "retailer_or_platform", "submission_type", "status", "submitted_date", "approved_date", "published_date", "expected_live_date", "live_url", "issue_text", "waiting_on"]
        return self._update_content_child("campaign_ops_content_submissions", ContentSubmissionRecord, submission_id, fields, tuple(kwargs.get(f) for f in fields))

    def deactivate_content_submission(self, submission_id: str) -> None:
        self._execute("update campaign_ops_content_submissions set is_active = false where id = %s and is_active = true", (submission_id,))

    def reactivate_content_submission(self, submission_id: str) -> ContentSubmissionRecord:
        return self._write_returning("update campaign_ops_content_submissions set is_active = true where id = %s and is_active = false returning *", (submission_id,), ContentSubmissionRecord)

    def create_content_monitoring_update(self, content_program_id: str, update_date: Any, update_text: str, actor_user_id: str | None = None, **kwargs: Any) -> ContentMonitoringUpdateRecord:
        fields = ["content_program_id", "sku_group_id", "sku_id", "update_date", "update_type", "update_text", "live_review_count", "publication_state", "created_by_user_id"]
        return self._create_content_child("campaign_ops_content_monitoring_updates", ContentMonitoringUpdateRecord, fields, (content_program_id, kwargs.get("sku_group_id"), kwargs.get("sku_id"), update_date, kwargs.get("update_type"), require_text(update_text, "update_text"), kwargs.get("live_review_count"), kwargs.get("publication_state"), actor_user_id))

    def list_content_monitoring_updates(self, content_program_id: str, include_inactive: bool = False) -> list[ContentMonitoringUpdateRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_content_monitoring_updates where content_program_id = %s {clause} order by update_date desc, created_at desc", (content_program_id,), ContentMonitoringUpdateRecord)

    def update_content_monitoring_update(self, update_id: str, **kwargs: Any) -> ContentMonitoringUpdateRecord:
        fields = ["sku_group_id", "sku_id", "update_date", "update_type", "update_text", "live_review_count", "publication_state"]
        return self._update_content_child("campaign_ops_content_monitoring_updates", ContentMonitoringUpdateRecord, update_id, fields, tuple(kwargs.get(f) for f in fields))

    def deactivate_content_monitoring_update(self, update_id: str) -> None:
        self._execute("update campaign_ops_content_monitoring_updates set is_active = false where id = %s and is_active = true", (update_id,))

    def reactivate_content_monitoring_update(self, update_id: str) -> ContentMonitoringUpdateRecord:
        return self._write_returning("update campaign_ops_content_monitoring_updates set is_active = true where id = %s and is_active = false returning *", (update_id,), ContentMonitoringUpdateRecord)

    def create_content_invoice_checkpoint(self, content_program_id: str, checkpoint_name: str, **kwargs: Any) -> ContentInvoiceCheckpointRecord:
        fields = ["content_program_id", "checkpoint_name", "invoice_date", "due_date", "status", "amount", "notes"]
        return self._create_content_child("campaign_ops_content_invoice_checkpoints", ContentInvoiceCheckpointRecord, fields, (content_program_id, require_text(checkpoint_name, "checkpoint_name"), kwargs.get("invoice_date"), kwargs.get("due_date"), kwargs.get("status"), kwargs.get("amount"), kwargs.get("notes")))

    def list_content_invoice_checkpoints(self, content_program_id: str, include_inactive: bool = False) -> list[ContentInvoiceCheckpointRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_content_invoice_checkpoints where content_program_id = %s {clause} order by coalesce(invoice_date, due_date) asc nulls last, created_at asc", (content_program_id,), ContentInvoiceCheckpointRecord)

    def update_content_invoice_checkpoint(self, checkpoint_id: str, **kwargs: Any) -> ContentInvoiceCheckpointRecord:
        fields = ["checkpoint_name", "invoice_date", "due_date", "status", "amount", "notes"]
        return self._update_content_child("campaign_ops_content_invoice_checkpoints", ContentInvoiceCheckpointRecord, checkpoint_id, fields, tuple(kwargs.get(f) for f in fields))

    def deactivate_content_invoice_checkpoint(self, checkpoint_id: str) -> None:
        self._execute("update campaign_ops_content_invoice_checkpoints set is_active = false where id = %s and is_active = true", (checkpoint_id,))

    def reactivate_content_invoice_checkpoint(self, checkpoint_id: str) -> ContentInvoiceCheckpointRecord:
        return self._write_returning("update campaign_ops_content_invoice_checkpoints set is_active = true where id = %s and is_active = false returning *", (checkpoint_id,), ContentInvoiceCheckpointRecord)

    def create_influencer_campaign(self, actor_user_id: str | None = None, **kwargs: Any) -> InfluencerCampaignRecord:
        return self._write_returning(
            """
            insert into campaign_ops_influencer_campaigns (
                program_id, workstream_id, campaign_title, manager_user_id,
                influencer_stage, planning_status, latest_update, waiting_on,
                is_on_hold, hold_reason, application_open_date, application_close_date,
                influencer_approval_due_date, scripts_due_date, first_content_due_date,
                launch_date, wrap_date, invoice_date, invoice_status, invoice_amount,
                target_creator_count, approved_creator_count, contracted_creator_count,
                created_by_user_id
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning *
            """,
            (
                kwargs["program_id"], kwargs.get("workstream_id"), require_text(kwargs.get("campaign_title"), "campaign_title"),
                kwargs.get("manager_user_id"), kwargs.get("influencer_stage"), kwargs.get("planning_status"), kwargs.get("latest_update"),
                kwargs.get("waiting_on"), bool(kwargs.get("is_on_hold", False)), kwargs.get("hold_reason"),
                kwargs.get("application_open_date"), kwargs.get("application_close_date"), kwargs.get("influencer_approval_due_date"),
                kwargs.get("scripts_due_date"), kwargs.get("first_content_due_date"), kwargs.get("launch_date"), kwargs.get("wrap_date"),
                kwargs.get("invoice_date"), kwargs.get("invoice_status"), kwargs.get("invoice_amount"), kwargs.get("target_creator_count"),
                kwargs.get("approved_creator_count"), kwargs.get("contracted_creator_count"), actor_user_id,
            ),
            InfluencerCampaignRecord,
        )

    def get_influencer_campaign(self, campaign_id: str) -> InfluencerCampaignRecord | None:
        return self._fetch_one("select * from campaign_ops_influencer_campaigns where id = %s", (campaign_id,), InfluencerCampaignRecord)

    def get_active_influencer_campaign_by_title(self, program_id: str, campaign_title: str) -> InfluencerCampaignRecord | None:
        return self._fetch_one(
            "select * from campaign_ops_influencer_campaigns where program_id = %s and lower(campaign_title) = lower(%s) and is_active = true",
            (program_id, campaign_title),
            InfluencerCampaignRecord,
        )

    def update_influencer_campaign(self, campaign_id: str, **kwargs: Any) -> InfluencerCampaignRecord:
        fields = [
            "workstream_id", "campaign_title", "manager_user_id", "influencer_stage", "planning_status", "latest_update",
            "waiting_on", "is_on_hold", "hold_reason", "application_open_date", "application_close_date",
            "influencer_approval_due_date", "scripts_due_date", "first_content_due_date", "launch_date", "wrap_date",
            "invoice_date", "invoice_status", "invoice_amount", "target_creator_count", "approved_creator_count",
            "contracted_creator_count",
        ]
        return self._write_returning(
            f"update campaign_ops_influencer_campaigns set {', '.join(f'{field} = %s' for field in fields)} where id = %s returning *",
            (*tuple(kwargs.get(field) for field in fields), campaign_id),
            InfluencerCampaignRecord,
        )

    def deactivate_influencer_campaign(self, campaign_id: str) -> None:
        self._execute("update campaign_ops_influencer_campaigns set is_active = false where id = %s and is_active = true", (campaign_id,))

    def reactivate_influencer_campaign(self, campaign_id: str) -> InfluencerCampaignRecord:
        return self._write_returning("update campaign_ops_influencer_campaigns set is_active = true where id = %s and is_active = false returning *", (campaign_id,), InfluencerCampaignRecord)

    def _influencer_portfolio_row_from_db(self, row: dict[str, Any]) -> InfluencerPlanningPortfolioRow:
        normalized = normalize_row(row)
        return InfluencerPlanningPortfolioRow(
            id=str(normalized["id"]), program_id=str(normalized["program_id"]), program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"), workstream_id=normalize_id(normalized.get("workstream_id")),
            campaign_title=str(normalized["campaign_title"]), manager_user_id=normalize_id(normalized.get("manager_user_id")),
            manager_display_name=normalized.get("manager_display_name"), influencer_stage=str(normalized["influencer_stage"]),
            planning_status=normalized.get("planning_status"), latest_update=normalized.get("latest_update"),
            waiting_on=normalized.get("waiting_on"), is_on_hold=bool(normalized.get("is_on_hold", False)),
            hold_reason=normalized.get("hold_reason"), application_open_date=normalized.get("application_open_date"),
            application_close_date=normalized.get("application_close_date"), influencer_approval_due_date=normalized.get("influencer_approval_due_date"),
            scripts_due_date=normalized.get("scripts_due_date"), first_content_due_date=normalized.get("first_content_due_date"),
            launch_date=normalized.get("launch_date"), wrap_date=normalized.get("wrap_date"), invoice_date=normalized.get("invoice_date"),
            invoice_status=normalized.get("invoice_status"), invoice_amount=normalized.get("invoice_amount"),
            target_creator_count=normalized.get("target_creator_count"), approved_creator_count=normalized.get("approved_creator_count"),
            contracted_creator_count=normalized.get("contracted_creator_count"), applicants_count=normalized.get("applicants_count"),
            vetted_count=normalized.get("vetted_count"), submitted_for_approval_count=normalized.get("submitted_for_approval_count"),
            content_submitted_count=normalized.get("content_submitted_count"), content_approved_count=normalized.get("content_approved_count"),
            creator_summary_notes=normalized.get("creator_summary_notes"), program_status=str(normalized["program_status"]),
            program_risk=str(normalized["program_risk"]), next_planning_step=normalized.get("next_planning_step"),
            next_planning_step_due_date=normalized.get("next_planning_step_due_date"), track_sheet_url=normalized.get("track_sheet_url"),
            influencer_brief_url=normalized.get("influencer_brief_url"), bitly_link_url=normalized.get("bitly_link_url"),
            invoice_url=normalized.get("invoice_url"), eop_survey_url=normalized.get("eop_survey_url"),
            influencer_education_url=normalized.get("influencer_education_url"), campaign_brief_url=normalized.get("campaign_brief_url"),
            click2cart_link_url=normalized.get("click2cart_link_url"), content_folder_url=normalized.get("content_folder_url"),
            application_link_url=normalized.get("application_link_url"), is_active=bool(normalized.get("is_active", True)),
            created_at=normalized.get("created_at"), updated_at=normalized.get("updated_at"),
        )

    def list_influencer_campaigns(self, include_inactive: bool = False, manager_user_id: str | None = None, stage: str | None = None) -> list[InfluencerPlanningPortfolioRow]:
        clauses: list[str] = []
        params: list[Any] = []
        if not include_inactive:
            clauses.append("ic.is_active = true")
        if manager_user_id:
            clauses.append("ic.manager_user_id = %s")
            params.append(manager_user_id)
        if stage:
            clauses.append("ic.influencer_stage = %s")
            params.append(stage)
        where_clause = f"where {' and '.join(clauses)}" if clauses else ""
        query = f"""
            with next_step as (
                select distinct on (influencer_campaign_id) influencer_campaign_id, step_title, due_date
                from campaign_ops_influencer_planning_steps
                where is_active = true and coalesce(status, '') <> 'complete' and completed_date is null
                order by influencer_campaign_id, due_date asc nulls last, sequence_order asc, created_at asc
            ), resource_agg as (
                select program_id,
                    max(url) filter (where resource_type = 'Track Sheet' and is_active = true) as track_sheet_url,
                    max(url) filter (where resource_type = 'Influencer Brief' and is_active = true) as influencer_brief_url,
                    max(url) filter (where resource_type = 'Bitly Link' and is_active = true) as bitly_link_url,
                    max(url) filter (where resource_type = 'Invoice' and is_active = true) as invoice_url,
                    max(url) filter (where resource_type = 'EOP Survey' and is_active = true) as eop_survey_url,
                    max(url) filter (where resource_type = 'Influencer Education' and is_active = true) as influencer_education_url,
                    max(url) filter (where resource_type = 'Campaign Brief' and is_active = true) as campaign_brief_url,
                    max(url) filter (where resource_type = 'Click2Cart Link' and is_active = true) as click2cart_link_url,
                    max(url) filter (where resource_type = 'Content Folder' and is_active = true) as content_folder_url,
                    max(url) filter (where resource_type = 'Application Link' and is_active = true) as application_link_url
                from campaign_ops_resources group by program_id
            )
            select ic.*, p.program_name, p.status as program_status, p.risk_level as program_risk,
                   c.name as client_name, u.display_name as manager_display_name,
                   cs.applicants_count, cs.vetted_count, cs.submitted_for_approval_count,
                   cs.content_submitted_count, cs.content_approved_count, cs.notes as creator_summary_notes,
                   coalesce(cs.target_creator_count, ic.target_creator_count) as target_creator_count,
                   coalesce(cs.approved_count, ic.approved_creator_count) as approved_creator_count,
                   coalesce(cs.contracted_count, ic.contracted_creator_count) as contracted_creator_count,
                   ns.step_title as next_planning_step, ns.due_date as next_planning_step_due_date,
                   ra.track_sheet_url, ra.influencer_brief_url, ra.bitly_link_url, ra.invoice_url,
                   ra.eop_survey_url, ra.influencer_education_url, ra.campaign_brief_url,
                   ra.click2cart_link_url, ra.content_folder_url, ra.application_link_url
            from campaign_ops_influencer_campaigns ic
            join campaign_ops_programs p on p.id = ic.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_users u on u.id = ic.manager_user_id
            left join campaign_ops_influencer_creator_summary cs on cs.influencer_campaign_id = ic.id and cs.is_active = true
            left join next_step ns on ns.influencer_campaign_id = ic.id
            left join resource_agg ra on ra.program_id = ic.program_id
            {where_clause}
            order by ic.updated_at desc, ic.campaign_title asc
        """
        return [self._influencer_portfolio_row_from_db(row) for row in self._fetch_raw_all(query, tuple(params))]

    def get_influencer_campaign_detail(self, campaign_id: str) -> InfluencerPlanningPortfolioRow | None:
        return next((row for row in self.list_influencer_campaigns(include_inactive=True) if row.id == campaign_id), None)

    def create_influencer_planning_step(self, influencer_campaign_id: str, step_title: str, **kwargs: Any) -> InfluencerPlanningStepRecord:
        fields = ["influencer_campaign_id", "step_type", "step_title", "step_description", "sequence_order", "responsible_party", "assigned_user_id", "start_date", "due_date", "completed_date", "status", "hard_deadline", "waiting_on", "notes"]
        return self._create_content_child("campaign_ops_influencer_planning_steps", InfluencerPlanningStepRecord, fields, (influencer_campaign_id, kwargs.get("step_type"), require_text(step_title, "step_title"), kwargs.get("step_description"), kwargs.get("sequence_order", 0), kwargs.get("responsible_party"), kwargs.get("assigned_user_id"), kwargs.get("start_date"), kwargs.get("due_date"), kwargs.get("completed_date"), kwargs.get("status"), bool(kwargs.get("hard_deadline", False)), kwargs.get("waiting_on"), kwargs.get("notes")))

    def list_influencer_planning_steps(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerPlanningStepRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_planning_steps where influencer_campaign_id = %s {clause} order by sequence_order asc, due_date asc nulls last, created_at asc", (influencer_campaign_id,), InfluencerPlanningStepRecord)

    def update_influencer_planning_step(self, step_id: str, **kwargs: Any) -> InfluencerPlanningStepRecord:
        fields = ["step_type", "step_title", "step_description", "sequence_order", "responsible_party", "assigned_user_id", "start_date", "due_date", "completed_date", "status", "hard_deadline", "waiting_on", "notes"]
        return self._update_content_child("campaign_ops_influencer_planning_steps", InfluencerPlanningStepRecord, step_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_planning_step(self, step_id: str) -> None:
        self._execute("update campaign_ops_influencer_planning_steps set is_active = false where id = %s and is_active = true", (step_id,))

    def reactivate_influencer_planning_step(self, step_id: str) -> InfluencerPlanningStepRecord:
        return self._write_returning("update campaign_ops_influencer_planning_steps set is_active = true where id = %s and is_active = false returning *", (step_id,), InfluencerPlanningStepRecord)

    def create_influencer_approval_round(self, influencer_campaign_id: str, approval_type: str, **kwargs: Any) -> InfluencerApprovalRoundRecord:
        fields = ["influencer_campaign_id", "approval_type", "round_number", "approval_scope", "requested_date", "feedback_due_date", "feedback_received_date", "approved_date", "status", "waiting_on", "notes"]
        return self._create_content_child("campaign_ops_influencer_approval_rounds", InfluencerApprovalRoundRecord, fields, (influencer_campaign_id, require_text(approval_type, "approval_type"), kwargs.get("round_number", 1), kwargs.get("approval_scope"), kwargs.get("requested_date"), kwargs.get("feedback_due_date"), kwargs.get("feedback_received_date"), kwargs.get("approved_date"), kwargs.get("status"), kwargs.get("waiting_on"), kwargs.get("notes")))

    def list_influencer_approval_rounds(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerApprovalRoundRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_approval_rounds where influencer_campaign_id = %s {clause} order by approval_type asc, round_number asc, created_at asc", (influencer_campaign_id,), InfluencerApprovalRoundRecord)

    def update_influencer_approval_round(self, approval_id: str, **kwargs: Any) -> InfluencerApprovalRoundRecord:
        fields = ["approval_type", "round_number", "approval_scope", "requested_date", "feedback_due_date", "feedback_received_date", "approved_date", "status", "waiting_on", "notes"]
        return self._update_content_child("campaign_ops_influencer_approval_rounds", InfluencerApprovalRoundRecord, approval_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_approval_round(self, approval_id: str) -> None:
        self._execute("update campaign_ops_influencer_approval_rounds set is_active = false where id = %s and is_active = true", (approval_id,))

    def reactivate_influencer_approval_round(self, approval_id: str) -> InfluencerApprovalRoundRecord:
        return self._write_returning("update campaign_ops_influencer_approval_rounds set is_active = true where id = %s and is_active = false returning *", (approval_id,), InfluencerApprovalRoundRecord)

    def create_influencer_content_round(self, influencer_campaign_id: str, round_number: int, **kwargs: Any) -> InfluencerContentRoundRecord:
        fields = ["influencer_campaign_id", "round_number", "content_type", "internal_review_due_date", "client_review_sent_date", "client_feedback_due_date", "feedback_received_date", "resubmission_due_date", "approved_date", "status", "waiting_on", "notes"]
        return self._create_content_child("campaign_ops_influencer_content_rounds", InfluencerContentRoundRecord, fields, (influencer_campaign_id, round_number, kwargs.get("content_type"), kwargs.get("internal_review_due_date"), kwargs.get("client_review_sent_date"), kwargs.get("client_feedback_due_date"), kwargs.get("feedback_received_date"), kwargs.get("resubmission_due_date"), kwargs.get("approved_date"), kwargs.get("status"), kwargs.get("waiting_on"), kwargs.get("notes")))

    def list_influencer_content_rounds(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerContentRoundRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_content_rounds where influencer_campaign_id = %s {clause} order by round_number asc, created_at asc", (influencer_campaign_id,), InfluencerContentRoundRecord)

    def update_influencer_content_round(self, content_round_id: str, **kwargs: Any) -> InfluencerContentRoundRecord:
        fields = ["round_number", "content_type", "internal_review_due_date", "client_review_sent_date", "client_feedback_due_date", "feedback_received_date", "resubmission_due_date", "approved_date", "status", "waiting_on", "notes"]
        return self._update_content_child("campaign_ops_influencer_content_rounds", InfluencerContentRoundRecord, content_round_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_content_round(self, content_round_id: str) -> None:
        self._execute("update campaign_ops_influencer_content_rounds set is_active = false where id = %s and is_active = true", (content_round_id,))

    def reactivate_influencer_content_round(self, content_round_id: str) -> InfluencerContentRoundRecord:
        return self._write_returning("update campaign_ops_influencer_content_rounds set is_active = true where id = %s and is_active = false returning *", (content_round_id,), InfluencerContentRoundRecord)

    def get_influencer_creator_summary(self, influencer_campaign_id: str) -> InfluencerCreatorSummaryRecord | None:
        return self._fetch_one("select * from campaign_ops_influencer_creator_summary where influencer_campaign_id = %s", (influencer_campaign_id,), InfluencerCreatorSummaryRecord)

    def create_or_update_influencer_creator_summary(self, influencer_campaign_id: str, **kwargs: Any) -> InfluencerCreatorSummaryRecord:
        fields = ["target_creator_count", "applicants_count", "vetted_count", "submitted_for_approval_count", "approved_count", "contracted_count", "content_submitted_count", "content_approved_count", "notes", "is_active"]
        return self._write_returning(
            f"""
            insert into campaign_ops_influencer_creator_summary (influencer_campaign_id, {', '.join(fields)})
            values (%s, {', '.join(['%s'] * len(fields))})
            on conflict (influencer_campaign_id) do update set {', '.join(f'{field} = excluded.{field}' for field in fields)}
            returning *
            """,
            (influencer_campaign_id, *tuple(kwargs.get(field) for field in fields)),
            InfluencerCreatorSummaryRecord,
        )

    def _influencer_live_portfolio_row_from_db(self, row: dict[str, Any]) -> InfluencerLivePortfolioRow:
        normalized = normalize_row(row)
        return InfluencerLivePortfolioRow(
            id=str(normalized["id"]), program_id=str(normalized["program_id"]), program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"), workstream_id=normalize_id(normalized.get("workstream_id")),
            campaign_title=str(normalized["campaign_title"]), manager_user_id=normalize_id(normalized.get("manager_user_id")),
            manager_display_name=normalized.get("manager_display_name"), influencer_stage=str(normalized["influencer_stage"]),
            live_status=normalized.get("live_status"), planning_status=normalized.get("planning_status"),
            latest_update=normalized.get("latest_update"), waiting_on=normalized.get("waiting_on"),
            is_on_hold=bool(normalized.get("is_on_hold", False)), hold_reason=normalized.get("hold_reason"),
            planned_creator_count=normalized.get("planned_creator_count"), live_creator_count=int(normalized.get("live_creator_count") or 0),
            completed_creator_count=int(normalized.get("completed_creator_count") or 0), active_wave_count=int(normalized.get("active_wave_count") or 0),
            next_go_live_date=normalized.get("next_go_live_date"), paid_live_end_date=normalized.get("paid_live_end_date"),
            open_exception_count=int(normalized.get("open_exception_count") or 0), highlighted_exception_count=int(normalized.get("highlighted_exception_count") or 0),
            launch_date=normalized.get("launch_date"), wrap_date=normalized.get("wrap_date"), invoice_date=normalized.get("invoice_date"),
            invoice_status=normalized.get("invoice_status"), invoice_amount=normalized.get("invoice_amount"),
            program_status=str(normalized["program_status"]), program_risk=str(normalized["program_risk"]),
            next_checkpoint=normalized.get("next_checkpoint"), next_checkpoint_due_date=normalized.get("next_checkpoint_due_date"),
            track_sheet_url=normalized.get("track_sheet_url"), influencer_brief_url=normalized.get("influencer_brief_url"),
            eop_survey_url=normalized.get("eop_survey_url"), invoice_url=normalized.get("invoice_url"),
            bitly_link_url=normalized.get("bitly_link_url"), click2cart_link_url=normalized.get("click2cart_link_url"),
            client_facing_live_doc_url=normalized.get("client_facing_live_doc_url"), daily_impressions_url=normalized.get("daily_impressions_url"),
            is_active=bool(normalized.get("is_active", True)), created_at=normalized.get("created_at"), updated_at=normalized.get("updated_at"),
        )

    def list_influencer_live_campaigns(self, include_inactive: bool = False, manager_user_id: str | None = None) -> list[InfluencerLivePortfolioRow]:
        clauses = ["ic.influencer_stage = 'live'"]
        params: list[Any] = []
        if not include_inactive:
            clauses.append("ic.is_active = true")
        if manager_user_id:
            clauses.append("ic.manager_user_id = %s")
            params.append(manager_user_id)
        query = f"""
            with next_checkpoint as (
                select distinct on (influencer_campaign_id) influencer_campaign_id, checkpoint_title, due_date
                from campaign_ops_influencer_live_checkpoints
                where is_active = true and coalesce(status, '') <> 'complete' and completed_date is null
                order by influencer_campaign_id, due_date asc nulls last, sequence_order asc, created_at asc
            ), wave_agg as (
                select influencer_campaign_id,
                       count(*) filter (where is_active = true) as active_wave_count,
                       sum(planned_creator_count) filter (where is_active = true) as planned_creator_count,
                       sum(live_creator_count) filter (where is_active = true) as live_wave_creator_count,
                       sum(completed_creator_count) filter (where is_active = true) as completed_wave_creator_count
                from campaign_ops_influencer_creator_waves group by influencer_campaign_id
            ), creator_agg as (
                select influencer_campaign_id,
                       count(*) filter (where is_active = true and live_status in ('live','paid_live_complete','complete')) as live_creator_count,
                       count(*) filter (where is_active = true and live_status in ('paid_live_complete','complete')) as completed_creator_count,
                       min(coalesce(scheduled_live_date, actual_live_date)) filter (where is_active = true and live_status not in ('live','paid_live_complete','complete')) as next_go_live_date,
                       max(paid_live_end_date) filter (where is_active = true) as paid_live_end_date
                from campaign_ops_influencer_live_creators group by influencer_campaign_id
            ), exception_agg as (
                select influencer_campaign_id,
                       count(*) filter (where is_active = true and coalesce(status, 'open') not in ('resolved','cancelled')) as open_exception_count,
                       count(*) filter (where is_active = true and is_highlighted = true and coalesce(status, 'open') not in ('resolved','cancelled')) as highlighted_exception_count
                from campaign_ops_influencer_live_exceptions group by influencer_campaign_id
            ), resource_agg as (
                select program_id,
                    max(url) filter (where resource_type = 'Track Sheet' and is_active = true) as track_sheet_url,
                    max(url) filter (where resource_type = 'Influencer Brief' and is_active = true) as influencer_brief_url,
                    max(url) filter (where resource_type = 'EOP Survey' and is_active = true) as eop_survey_url,
                    max(url) filter (where resource_type = 'Invoice' and is_active = true) as invoice_url,
                    max(url) filter (where resource_type = 'Bitly Link' and is_active = true) as bitly_link_url,
                    max(url) filter (where resource_type = 'Click2Cart Link' and is_active = true) as click2cart_link_url,
                    max(url) filter (where resource_type = 'Client-Facing Live Doc' and is_active = true) as client_facing_live_doc_url,
                    max(url) filter (where resource_type = 'Daily Impressions' and is_active = true) as daily_impressions_url
                from campaign_ops_resources group by program_id
            )
            select ic.*, ic.planning_status as live_status, p.program_name, p.status as program_status, p.risk_level as program_risk,
                   c.name as client_name, u.display_name as manager_display_name,
                   coalesce(wa.planned_creator_count, ic.target_creator_count) as planned_creator_count,
                   coalesce(ca.live_creator_count, wa.live_wave_creator_count, 0) as live_creator_count,
                   coalesce(ca.completed_creator_count, wa.completed_wave_creator_count, 0) as completed_creator_count,
                   coalesce(wa.active_wave_count, 0) as active_wave_count,
                   ca.next_go_live_date, ca.paid_live_end_date,
                   coalesce(ea.open_exception_count, 0) as open_exception_count,
                   coalesce(ea.highlighted_exception_count, 0) as highlighted_exception_count,
                   nc.checkpoint_title as next_checkpoint, nc.due_date as next_checkpoint_due_date,
                   ra.track_sheet_url, ra.influencer_brief_url, ra.eop_survey_url, ra.invoice_url,
                   ra.bitly_link_url, ra.click2cart_link_url, ra.client_facing_live_doc_url, ra.daily_impressions_url
            from campaign_ops_influencer_campaigns ic
            join campaign_ops_programs p on p.id = ic.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_users u on u.id = ic.manager_user_id
            left join next_checkpoint nc on nc.influencer_campaign_id = ic.id
            left join wave_agg wa on wa.influencer_campaign_id = ic.id
            left join creator_agg ca on ca.influencer_campaign_id = ic.id
            left join exception_agg ea on ea.influencer_campaign_id = ic.id
            left join resource_agg ra on ra.program_id = ic.program_id
            where {' and '.join(clauses)}
            order by ic.updated_at desc, ic.campaign_title asc
        """
        return [self._influencer_live_portfolio_row_from_db(row) for row in self._fetch_raw_all(query, tuple(params))]

    def get_influencer_live_campaign_detail(self, campaign_id: str) -> InfluencerLivePortfolioRow | None:
        return next((row for row in self.list_influencer_live_campaigns(include_inactive=True) if row.id == campaign_id), None)

    def create_influencer_live_checkpoint(self, influencer_campaign_id: str, checkpoint_title: str, **kwargs: Any) -> InfluencerLiveCheckpointRecord:
        fields = ["influencer_campaign_id", "checkpoint_type", "checkpoint_title", "checkpoint_description", "sequence_order", "responsible_party", "assigned_user_id", "start_date", "due_date", "completed_date", "status", "hard_deadline", "waiting_on", "notes"]
        return self._create_content_child("campaign_ops_influencer_live_checkpoints", InfluencerLiveCheckpointRecord, fields, (influencer_campaign_id, kwargs.get("checkpoint_type"), require_text(checkpoint_title, "checkpoint_title"), kwargs.get("checkpoint_description"), kwargs.get("sequence_order", 0), kwargs.get("responsible_party"), kwargs.get("assigned_user_id"), kwargs.get("start_date"), kwargs.get("due_date"), kwargs.get("completed_date"), kwargs.get("status"), bool(kwargs.get("hard_deadline", False)), kwargs.get("waiting_on"), kwargs.get("notes")))

    def list_influencer_live_checkpoints(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveCheckpointRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_live_checkpoints where influencer_campaign_id = %s {clause} order by sequence_order asc, due_date asc nulls last, created_at asc", (influencer_campaign_id,), InfluencerLiveCheckpointRecord)

    def update_influencer_live_checkpoint(self, checkpoint_id: str, **kwargs: Any) -> InfluencerLiveCheckpointRecord:
        fields = ["checkpoint_type", "checkpoint_title", "checkpoint_description", "sequence_order", "responsible_party", "assigned_user_id", "start_date", "due_date", "completed_date", "status", "hard_deadline", "waiting_on", "notes"]
        return self._update_content_child("campaign_ops_influencer_live_checkpoints", InfluencerLiveCheckpointRecord, checkpoint_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_live_checkpoint(self, checkpoint_id: str) -> None:
        self._execute("update campaign_ops_influencer_live_checkpoints set is_active = false where id = %s and is_active = true", (checkpoint_id,))

    def reactivate_influencer_live_checkpoint(self, checkpoint_id: str) -> InfluencerLiveCheckpointRecord:
        return self._write_returning("update campaign_ops_influencer_live_checkpoints set is_active = true where id = %s and is_active = false returning *", (checkpoint_id,), InfluencerLiveCheckpointRecord)

    def create_influencer_creator_wave(self, influencer_campaign_id: str, wave_number: int, **kwargs: Any) -> InfluencerCreatorWaveRecord:
        fields = ["influencer_campaign_id", "wave_number", "wave_name", "planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date", "planned_creator_count", "live_creator_count", "completed_creator_count", "status", "waiting_on", "notes"]
        return self._create_content_child("campaign_ops_influencer_creator_waves", InfluencerCreatorWaveRecord, fields, (influencer_campaign_id, wave_number, kwargs.get("wave_name"), kwargs.get("planned_start_date"), kwargs.get("planned_end_date"), kwargs.get("actual_start_date"), kwargs.get("actual_end_date"), kwargs.get("planned_creator_count"), kwargs.get("live_creator_count"), kwargs.get("completed_creator_count"), kwargs.get("status"), kwargs.get("waiting_on"), kwargs.get("notes")))

    def list_influencer_creator_waves(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerCreatorWaveRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_creator_waves where influencer_campaign_id = %s {clause} order by wave_number asc, created_at asc", (influencer_campaign_id,), InfluencerCreatorWaveRecord)

    def update_influencer_creator_wave(self, wave_id: str, **kwargs: Any) -> InfluencerCreatorWaveRecord:
        fields = ["wave_number", "wave_name", "planned_start_date", "planned_end_date", "actual_start_date", "actual_end_date", "planned_creator_count", "live_creator_count", "completed_creator_count", "status", "waiting_on", "notes"]
        return self._update_content_child("campaign_ops_influencer_creator_waves", InfluencerCreatorWaveRecord, wave_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_creator_wave(self, wave_id: str) -> None:
        self._execute("update campaign_ops_influencer_creator_waves set is_active = false where id = %s and is_active = true", (wave_id,))

    def reactivate_influencer_creator_wave(self, wave_id: str) -> InfluencerCreatorWaveRecord:
        return self._write_returning("update campaign_ops_influencer_creator_waves set is_active = true where id = %s and is_active = false returning *", (wave_id,), InfluencerCreatorWaveRecord)

    def create_influencer_live_creator(self, influencer_campaign_id: str, creator_name: str, **kwargs: Any) -> InfluencerLiveCreatorRecord:
        fields = ["influencer_campaign_id", "wave_id", "creator_name", "creator_handle", "platform", "live_status", "draft_status", "approval_status", "scheduled_live_date", "actual_live_date", "paid_live_end_date", "content_url", "click2cart_url", "retailer_url", "impressions_reporting_required", "latest_impressions", "last_impressions_update_date", "waiting_on", "exception_status", "exception_notes"]
        return self._create_content_child("campaign_ops_influencer_live_creators", InfluencerLiveCreatorRecord, fields, (influencer_campaign_id, kwargs.get("wave_id"), require_text(creator_name, "creator_name"), kwargs.get("creator_handle"), kwargs.get("platform"), kwargs.get("live_status"), kwargs.get("draft_status"), kwargs.get("approval_status"), kwargs.get("scheduled_live_date"), kwargs.get("actual_live_date"), kwargs.get("paid_live_end_date"), kwargs.get("content_url"), kwargs.get("click2cart_url"), kwargs.get("retailer_url"), bool(kwargs.get("impressions_reporting_required", False)), kwargs.get("latest_impressions"), kwargs.get("last_impressions_update_date"), kwargs.get("waiting_on"), kwargs.get("exception_status"), kwargs.get("exception_notes")))

    def list_influencer_live_creators(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveCreatorRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_live_creators where influencer_campaign_id = %s {clause} order by scheduled_live_date asc nulls last, creator_name asc", (influencer_campaign_id,), InfluencerLiveCreatorRecord)

    def update_influencer_live_creator(self, creator_id: str, **kwargs: Any) -> InfluencerLiveCreatorRecord:
        fields = ["wave_id", "creator_name", "creator_handle", "platform", "live_status", "draft_status", "approval_status", "scheduled_live_date", "actual_live_date", "paid_live_end_date", "content_url", "click2cart_url", "retailer_url", "impressions_reporting_required", "latest_impressions", "last_impressions_update_date", "waiting_on", "exception_status", "exception_notes"]
        return self._update_content_child("campaign_ops_influencer_live_creators", InfluencerLiveCreatorRecord, creator_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_live_creator(self, creator_id: str) -> None:
        self._execute("update campaign_ops_influencer_live_creators set is_active = false where id = %s and is_active = true", (creator_id,))

    def reactivate_influencer_live_creator(self, creator_id: str) -> InfluencerLiveCreatorRecord:
        return self._write_returning("update campaign_ops_influencer_live_creators set is_active = true where id = %s and is_active = false returning *", (creator_id,), InfluencerLiveCreatorRecord)

    def create_influencer_live_exception(self, influencer_campaign_id: str, exception_title: str, **kwargs: Any) -> InfluencerLiveExceptionRecord:
        fields = ["influencer_campaign_id", "live_creator_id", "exception_type", "exception_title", "description", "status", "owner_user_id", "opened_date", "due_date", "resolved_date", "resolution_notes", "is_highlighted"]
        return self._create_content_child("campaign_ops_influencer_live_exceptions", InfluencerLiveExceptionRecord, fields, (influencer_campaign_id, kwargs.get("live_creator_id"), kwargs.get("exception_type"), require_text(exception_title, "exception_title"), kwargs.get("description"), kwargs.get("status"), kwargs.get("owner_user_id"), kwargs.get("opened_date"), kwargs.get("due_date"), kwargs.get("resolved_date"), kwargs.get("resolution_notes"), bool(kwargs.get("is_highlighted", False))))

    def list_influencer_live_exceptions(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerLiveExceptionRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_live_exceptions where influencer_campaign_id = %s {clause} order by is_highlighted desc, due_date asc nulls last, created_at desc", (influencer_campaign_id,), InfluencerLiveExceptionRecord)

    def update_influencer_live_exception(self, exception_id: str, **kwargs: Any) -> InfluencerLiveExceptionRecord:
        fields = ["live_creator_id", "exception_type", "exception_title", "description", "status", "owner_user_id", "opened_date", "due_date", "resolved_date", "resolution_notes", "is_highlighted"]
        return self._update_content_child("campaign_ops_influencer_live_exceptions", InfluencerLiveExceptionRecord, exception_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_live_exception(self, exception_id: str) -> None:
        self._execute("update campaign_ops_influencer_live_exceptions set is_active = false where id = %s and is_active = true", (exception_id,))

    def reactivate_influencer_live_exception(self, exception_id: str) -> InfluencerLiveExceptionRecord:
        return self._write_returning("update campaign_ops_influencer_live_exceptions set is_active = true where id = %s and is_active = false returning *", (exception_id,), InfluencerLiveExceptionRecord)

    def create_or_update_influencer_recap_record(self, influencer_campaign_id: str, **kwargs: Any) -> InfluencerRecapRecord:
        fields = [
            "recap_status", "latest_update", "waiting_on", "reporting_due_date", "draft_recap_due_date",
            "internal_review_date", "client_review_date", "client_recap_date", "recap_delivered_date",
            "final_close_date", "final_invoice_sent_date", "sales_lift_analysis_required", "sales_lift_analysis_status",
            "final_performance_data_status", "creator_closeout_status", "eop_survey_status", "invoice_status",
            "financial_close_status", "lessons_learned", "is_active",
        ]
        return self._write_returning(
            f"""
            insert into campaign_ops_influencer_recap_records (influencer_campaign_id, {', '.join(fields)})
            values (%s, {', '.join(['%s'] * len(fields))})
            on conflict (influencer_campaign_id) do update set {', '.join(f'{field} = excluded.{field}' for field in fields)}
            returning *
            """,
            (
                influencer_campaign_id,
                *tuple(
                    False if field == "sales_lift_analysis_required" and field not in kwargs
                    else True if field == "is_active" and field not in kwargs
                    else kwargs.get(field)
                    for field in fields
                ),
            ),
            InfluencerRecapRecord,
        )

    def get_influencer_recap_record(self, influencer_campaign_id: str) -> InfluencerRecapRecord | None:
        return self._fetch_one(
            "select * from campaign_ops_influencer_recap_records where influencer_campaign_id = %s",
            (influencer_campaign_id,),
            InfluencerRecapRecord,
        )

    def update_influencer_recap_record(self, recap_record_id: str, **kwargs: Any) -> InfluencerRecapRecord:
        fields = [
            "recap_status", "latest_update", "waiting_on", "reporting_due_date", "draft_recap_due_date",
            "internal_review_date", "client_review_date", "client_recap_date", "recap_delivered_date",
            "final_close_date", "final_invoice_sent_date", "sales_lift_analysis_required", "sales_lift_analysis_status",
            "final_performance_data_status", "creator_closeout_status", "eop_survey_status", "invoice_status",
            "financial_close_status", "lessons_learned", "is_active",
        ]
        return self._update_content_child("campaign_ops_influencer_recap_records", InfluencerRecapRecord, recap_record_id, fields, tuple(kwargs.get(field) for field in fields))

    def _influencer_recap_portfolio_row_from_db(self, row: dict[str, Any]) -> InfluencerRecapPortfolioRow:
        normalized = normalize_row(row)
        return InfluencerRecapPortfolioRow(
            id=str(normalized["id"]), program_id=str(normalized["program_id"]), program_name=str(normalized["program_name"]),
            client_name=normalized.get("client_name"), workstream_id=normalize_id(normalized.get("workstream_id")),
            campaign_title=str(normalized["campaign_title"]), manager_user_id=normalize_id(normalized.get("manager_user_id")),
            manager_display_name=normalized.get("manager_display_name"), influencer_stage=str(normalized["influencer_stage"]),
            recap_record_id=normalize_id(normalized.get("recap_record_id")), recap_status=normalized.get("recap_status"),
            latest_update=normalized.get("recap_latest_update") or normalized.get("latest_update"), waiting_on=normalized.get("recap_waiting_on") or normalized.get("waiting_on"),
            all_creators_live=bool(normalized.get("all_creators_live", False)), creator_closeout_status=normalized.get("creator_closeout_status"),
            eop_survey_status=normalized.get("eop_survey_status"), final_performance_data_status=normalized.get("final_performance_data_status"),
            sales_lift_analysis_required=bool(normalized.get("sales_lift_analysis_required", False)),
            sales_lift_analysis_status=normalized.get("sales_lift_analysis_status"), recap_deck_status=normalized.get("recap_deck_status"),
            client_recap_date=normalized.get("client_recap_date"), invoice_status=normalized.get("recap_invoice_status") or normalized.get("invoice_status"),
            financial_close_status=normalized.get("financial_close_status"), open_requirement_count=int(normalized.get("open_requirement_count") or 0),
            launch_item_count=int(normalized.get("launch_item_count") or 0), open_exception_count=int(normalized.get("open_exception_count") or 0),
            total_creator_count=int(normalized.get("total_creator_count") or 0), live_creator_count=int(normalized.get("live_creator_count") or 0),
            completed_creator_count=int(normalized.get("completed_creator_count") or 0), missing_final_links_count=int(normalized.get("missing_final_links_count") or 0),
            missing_final_impressions_count=int(normalized.get("missing_final_impressions_count") or 0), paid_live_incomplete_count=int(normalized.get("paid_live_incomplete_count") or 0),
            program_status=str(normalized["program_status"]), program_risk=str(normalized["program_risk"]),
            reporting_due_date=normalized.get("reporting_due_date"), next_checkpoint=normalized.get("next_checkpoint"),
            next_checkpoint_due_date=normalized.get("next_checkpoint_due_date"), track_sheet_url=normalized.get("track_sheet_url"),
            influencer_brief_url=normalized.get("influencer_brief_url"), click2cart_link_url=normalized.get("click2cart_link_url"),
            bitly_link_url=normalized.get("bitly_link_url"), invoice_url=normalized.get("invoice_url"), eop_survey_url=normalized.get("eop_survey_url"),
            live_content_tracker_url=normalized.get("live_content_tracker_url"), recap_deck_url=normalized.get("recap_deck_url"),
            final_performance_data_url=normalized.get("final_performance_data_url"), sales_lift_analysis_url=normalized.get("sales_lift_analysis_url"),
            ready_to_close_state=str(normalized.get("ready_to_close_state") or "Not Ready"),
            is_active=bool(normalized.get("is_active", True)), created_at=normalized.get("created_at"), updated_at=normalized.get("updated_at"),
        )

    def list_influencer_recap_campaigns(self, include_inactive: bool = False, manager_user_id: str | None = None) -> list[InfluencerRecapPortfolioRow]:
        clauses = ["ic.influencer_stage in ('recapping','complete')" if include_inactive else "ic.influencer_stage = 'recapping'"]
        params: list[Any] = []
        if not include_inactive:
            clauses.append("ic.is_active = true")
        if manager_user_id:
            clauses.append("ic.manager_user_id = %s")
            params.append(manager_user_id)
        query = f"""
            with next_checkpoint as (
                select distinct on (influencer_campaign_id) influencer_campaign_id, checkpoint_title, due_date
                from campaign_ops_influencer_recap_checkpoints
                where is_active = true and coalesce(status, '') <> 'complete' and completed_date is null
                order by influencer_campaign_id, due_date asc nulls last, sequence_order asc, created_at asc
            ), req_agg as (
                select influencer_campaign_id,
                       count(*) filter (where is_active = true and required = true and coalesce(status, 'not_started') not in ('complete','not_required','cancelled')) as open_requirement_count,
                       max(status) filter (where is_active = true and requirement_type = 'Recap Deck') as recap_deck_status
                from campaign_ops_influencer_recap_requirements group by influencer_campaign_id
            ), launch_agg as (
                select influencer_campaign_id, count(*) filter (where is_active = true) as launch_item_count
                from campaign_ops_influencer_recap_launch_items group by influencer_campaign_id
            ), creator_agg as (
                select influencer_campaign_id,
                       count(*) filter (where is_active = true) as total_creator_count,
                       count(*) filter (where is_active = true and live_status in ('live','paid_live_complete','complete')) as live_creator_count,
                       count(*) filter (where is_active = true and live_status in ('paid_live_complete','complete')) as completed_creator_count,
                       count(*) filter (where is_active = true and (content_url is null or content_url = '')) as missing_final_links_count,
                       count(*) filter (where is_active = true and impressions_reporting_required = true and latest_impressions is null) as missing_final_impressions_count,
                       count(*) filter (where is_active = true and coalesce(live_status, '') not in ('paid_live_complete','complete','cancelled')) as paid_live_incomplete_count
                from campaign_ops_influencer_live_creators group by influencer_campaign_id
            ), exception_agg as (
                select influencer_campaign_id,
                       count(*) filter (where is_active = true and coalesce(status, 'open') not in ('resolved','cancelled')) as open_exception_count
                from campaign_ops_influencer_live_exceptions group by influencer_campaign_id
            ), resource_agg as (
                select program_id,
                    max(url) filter (where resource_type = 'Track Sheet' and is_active = true) as track_sheet_url,
                    max(url) filter (where resource_type = 'Influencer Brief' and is_active = true) as influencer_brief_url,
                    max(url) filter (where resource_type = 'Click2Cart Link' and is_active = true) as click2cart_link_url,
                    max(url) filter (where resource_type = 'Bitly Link' and is_active = true) as bitly_link_url,
                    max(url) filter (where resource_type = 'Invoice' and is_active = true) as invoice_url,
                    max(url) filter (where resource_type = 'EOP Survey' and is_active = true) as eop_survey_url,
                    max(url) filter (where resource_type = 'Live Content Tracker' and is_active = true) as live_content_tracker_url,
                    max(url) filter (where resource_type in ('Recap Deck','Results Deck','Client Recap Deck') and is_active = true) as recap_deck_url,
                    max(url) filter (where resource_type = 'Final Performance Data' and is_active = true) as final_performance_data_url,
                    max(url) filter (where resource_type = 'Sales Lift Analysis' and is_active = true) as sales_lift_analysis_url
                from campaign_ops_resources group by program_id
            )
            select ic.*, rr.id as recap_record_id, rr.recap_status, rr.latest_update as recap_latest_update,
                   rr.waiting_on as recap_waiting_on, rr.reporting_due_date, rr.client_recap_date,
                   rr.sales_lift_analysis_required, rr.sales_lift_analysis_status, rr.final_performance_data_status,
                   rr.creator_closeout_status, rr.eop_survey_status, rr.invoice_status as recap_invoice_status,
                   rr.financial_close_status,
                   p.program_name, p.status as program_status, p.risk_level as program_risk,
                   c.name as client_name, u.display_name as manager_display_name,
                   coalesce(ca.total_creator_count, 0) as total_creator_count,
                   coalesce(ca.live_creator_count, 0) as live_creator_count,
                   coalesce(ca.completed_creator_count, 0) as completed_creator_count,
                   coalesce(ca.missing_final_links_count, 0) as missing_final_links_count,
                   coalesce(ca.missing_final_impressions_count, 0) as missing_final_impressions_count,
                   coalesce(ca.paid_live_incomplete_count, 0) as paid_live_incomplete_count,
                   coalesce(ea.open_exception_count, 0) as open_exception_count,
                   coalesce(req.open_requirement_count, 0) as open_requirement_count,
                   req.recap_deck_status, coalesce(la.launch_item_count, 0) as launch_item_count,
                   nc.checkpoint_title as next_checkpoint, nc.due_date as next_checkpoint_due_date,
                   ra.track_sheet_url, ra.influencer_brief_url, ra.click2cart_link_url, ra.bitly_link_url,
                   ra.invoice_url, ra.eop_survey_url, ra.live_content_tracker_url, ra.recap_deck_url,
                   ra.final_performance_data_url, ra.sales_lift_analysis_url,
                   case
                     when coalesce(ea.open_exception_count, 0) > 0 then 'Needs Attention'
                     when coalesce(req.open_requirement_count, 0) > 0 or coalesce(ca.paid_live_incomplete_count, 0) > 0 then 'Not Ready'
                     when ic.influencer_stage = 'complete' or rr.recap_status = 'complete' then 'Complete'
                     else 'Ready to Close'
                   end as ready_to_close_state
            from campaign_ops_influencer_campaigns ic
            join campaign_ops_programs p on p.id = ic.program_id
            left join campaign_ops_clients c on c.id = p.client_id
            left join campaign_ops_users u on u.id = ic.manager_user_id
            left join campaign_ops_influencer_recap_records rr on rr.influencer_campaign_id = ic.id
            left join req_agg req on req.influencer_campaign_id = ic.id
            left join launch_agg la on la.influencer_campaign_id = ic.id
            left join creator_agg ca on ca.influencer_campaign_id = ic.id
            left join exception_agg ea on ea.influencer_campaign_id = ic.id
            left join next_checkpoint nc on nc.influencer_campaign_id = ic.id
            left join resource_agg ra on ra.program_id = ic.program_id
            where {' and '.join(clauses)}
            order by ic.updated_at desc, ic.campaign_title asc
        """
        return [self._influencer_recap_portfolio_row_from_db(row) for row in self._fetch_raw_all(query, tuple(params))]

    def get_influencer_recap_campaign_detail(self, campaign_id: str) -> InfluencerRecapPortfolioRow | None:
        return next((row for row in self.list_influencer_recap_campaigns(include_inactive=True) if row.id == campaign_id), None)

    def create_influencer_recap_checkpoint(self, influencer_campaign_id: str, checkpoint_title: str, **kwargs: Any) -> InfluencerRecapCheckpointRecord:
        fields = ["influencer_campaign_id", "checkpoint_type", "checkpoint_title", "sequence_order", "responsible_party", "assigned_user_id", "due_date", "completed_date", "status", "waiting_on", "notes", "hard_deadline"]
        return self._create_content_child("campaign_ops_influencer_recap_checkpoints", InfluencerRecapCheckpointRecord, fields, (influencer_campaign_id, kwargs.get("checkpoint_type"), require_text(checkpoint_title, "checkpoint_title"), kwargs.get("sequence_order", 0), kwargs.get("responsible_party"), kwargs.get("assigned_user_id"), kwargs.get("due_date"), kwargs.get("completed_date"), kwargs.get("status"), kwargs.get("waiting_on"), kwargs.get("notes"), bool(kwargs.get("hard_deadline", False))))

    def list_influencer_recap_checkpoints(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapCheckpointRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_recap_checkpoints where influencer_campaign_id = %s {clause} order by sequence_order asc, due_date asc nulls last, created_at asc", (influencer_campaign_id,), InfluencerRecapCheckpointRecord)

    def update_influencer_recap_checkpoint(self, checkpoint_id: str, **kwargs: Any) -> InfluencerRecapCheckpointRecord:
        fields = ["checkpoint_type", "checkpoint_title", "sequence_order", "responsible_party", "assigned_user_id", "due_date", "completed_date", "status", "waiting_on", "notes", "hard_deadline"]
        return self._update_content_child("campaign_ops_influencer_recap_checkpoints", InfluencerRecapCheckpointRecord, checkpoint_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_recap_checkpoint(self, checkpoint_id: str) -> None:
        self._execute("update campaign_ops_influencer_recap_checkpoints set is_active = false where id = %s and is_active = true", (checkpoint_id,))

    def reactivate_influencer_recap_checkpoint(self, checkpoint_id: str) -> InfluencerRecapCheckpointRecord:
        return self._write_returning("update campaign_ops_influencer_recap_checkpoints set is_active = true where id = %s and is_active = false returning *", (checkpoint_id,), InfluencerRecapCheckpointRecord)

    def create_influencer_recap_requirement(self, influencer_campaign_id: str, requirement_type: str, requirement_title: str, **kwargs: Any) -> InfluencerRecapRequirementRecord:
        fields = ["influencer_campaign_id", "requirement_type", "requirement_title", "status", "required", "due_date", "received_date", "completed_date", "waiting_on", "resource_id", "reporting_request_id", "notes"]
        return self._create_content_child("campaign_ops_influencer_recap_requirements", InfluencerRecapRequirementRecord, fields, (influencer_campaign_id, require_text(requirement_type, "requirement_type"), require_text(requirement_title, "requirement_title"), kwargs.get("status"), bool(kwargs.get("required", True)), kwargs.get("due_date"), kwargs.get("received_date"), kwargs.get("completed_date"), kwargs.get("waiting_on"), kwargs.get("resource_id"), kwargs.get("reporting_request_id"), kwargs.get("notes")))

    def list_influencer_recap_requirements(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapRequirementRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_recap_requirements where influencer_campaign_id = %s {clause} order by required desc, due_date asc nulls last, requirement_type asc, created_at asc", (influencer_campaign_id,), InfluencerRecapRequirementRecord)

    def update_influencer_recap_requirement(self, requirement_id: str, **kwargs: Any) -> InfluencerRecapRequirementRecord:
        fields = ["requirement_type", "requirement_title", "status", "required", "due_date", "received_date", "completed_date", "waiting_on", "resource_id", "reporting_request_id", "notes"]
        return self._update_content_child("campaign_ops_influencer_recap_requirements", InfluencerRecapRequirementRecord, requirement_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_recap_requirement(self, requirement_id: str) -> None:
        self._execute("update campaign_ops_influencer_recap_requirements set is_active = false where id = %s and is_active = true", (requirement_id,))

    def reactivate_influencer_recap_requirement(self, requirement_id: str) -> InfluencerRecapRequirementRecord:
        return self._write_returning("update campaign_ops_influencer_recap_requirements set is_active = true where id = %s and is_active = false returning *", (requirement_id,), InfluencerRecapRequirementRecord)

    def create_influencer_recap_launch_item(self, influencer_campaign_id: str, product_name: str, **kwargs: Any) -> InfluencerRecapLaunchItemRecord:
        fields = ["influencer_campaign_id", "group_name", "product_name", "retailer_name", "online_launch_date", "in_store_launch_date", "launch_status", "product_url", "retailer_url", "notes", "sort_order"]
        return self._create_content_child("campaign_ops_influencer_recap_launch_items", InfluencerRecapLaunchItemRecord, fields, (influencer_campaign_id, kwargs.get("group_name"), require_text(product_name, "product_name"), kwargs.get("retailer_name"), kwargs.get("online_launch_date"), kwargs.get("in_store_launch_date"), kwargs.get("launch_status"), kwargs.get("product_url"), kwargs.get("retailer_url"), kwargs.get("notes"), kwargs.get("sort_order", 0)))

    def list_influencer_recap_launch_items(self, influencer_campaign_id: str, include_inactive: bool = False) -> list[InfluencerRecapLaunchItemRecord]:
        clause = "" if include_inactive else "and is_active = true"
        return self._fetch_all(f"select * from campaign_ops_influencer_recap_launch_items where influencer_campaign_id = %s {clause} order by sort_order asc, group_name asc nulls last, product_name asc", (influencer_campaign_id,), InfluencerRecapLaunchItemRecord)

    def update_influencer_recap_launch_item(self, launch_item_id: str, **kwargs: Any) -> InfluencerRecapLaunchItemRecord:
        fields = ["group_name", "product_name", "retailer_name", "online_launch_date", "in_store_launch_date", "launch_status", "product_url", "retailer_url", "notes", "sort_order"]
        return self._update_content_child("campaign_ops_influencer_recap_launch_items", InfluencerRecapLaunchItemRecord, launch_item_id, fields, tuple(kwargs.get(field) for field in fields))

    def deactivate_influencer_recap_launch_item(self, launch_item_id: str) -> None:
        self._execute("update campaign_ops_influencer_recap_launch_items set is_active = false where id = %s and is_active = true", (launch_item_id,))

    def reactivate_influencer_recap_launch_item(self, launch_item_id: str) -> InfluencerRecapLaunchItemRecord:
        return self._write_returning("update campaign_ops_influencer_recap_launch_items set is_active = true where id = %s and is_active = false returning *", (launch_item_id,), InfluencerRecapLaunchItemRecord)

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

    def list_program_activity_with_actor(self, program_id: str) -> list[dict[str, Any]]:
        return self._fetch_raw_all(
            """
            select
                a.*,
                u.display_name as actor_display_name,
                w.workstream_type as workstream_type
            from campaign_ops_activity a
            left join campaign_ops_users u on u.id = a.actor_user_id
            left join campaign_ops_workstreams w on w.id = a.workstream_id
            where a.program_id = %s
            order by a.created_at desc
            """,
            (program_id,),
        )
