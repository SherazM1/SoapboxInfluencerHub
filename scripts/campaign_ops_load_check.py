from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.campaign_ops.db import get_campaign_ops_database_url
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.performance import campaign_ops_query_counter
from core.campaign_ops.service import CampaignOpsService


@dataclass(slots=True)
class OperationResult:
    name: str
    ok: bool
    seconds: float
    query_count: int
    error_type: str | None = None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((percentile / 100) * (len(ordered) - 1))))
    return ordered[index]


def _run_operation(name: str, operation: Callable[[], object]) -> OperationResult:
    started = perf_counter()
    try:
        with campaign_ops_query_counter(name) as stats:
            operation()
        return OperationResult(name, True, perf_counter() - started, stats.query_count)
    except Exception as exc:
        return OperationResult(name, False, perf_counter() - started, 0, type(exc).__name__)


def _read_operations() -> list[tuple[str, Callable[[], object]]]:
    service = CampaignOpsService()
    users = {user.display_name: user for user in service.list_active_users()}
    actor = users.get("Bailey") or next(iter(users.values()), None)
    if actor is None:
        raise RuntimeError("No active Campaign Operations users found.")
    programs = service.list_program_portfolio(actor, {})
    program_id = programs[0].id if programs else None

    operations: list[tuple[str, Callable[[], object]]] = [
        ("cross_team", lambda: CampaignOpsService().get_cross_team_dashboard_summary(actor, {"include_test_records": True})),
        ("all_programs", lambda: CampaignOpsService().list_program_portfolio(actor, {})),
        ("my_work", lambda: CampaignOpsService().list_user_tasks(actor, actor.id)),
        ("influencer_live", lambda: CampaignOpsService().list_influencer_live_campaigns(actor, include_inactive=True)),
        ("influencer_recapping", lambda: CampaignOpsService().list_influencer_recap_campaigns(actor, include_inactive=True)),
    ]
    if program_id:
        operations.append(("program_workspace", lambda: CampaignOpsService().get_program_workspace_summary(actor, program_id)))
    return operations


def run_read_simulation(users: int, iterations: int) -> list[OperationResult]:
    operations = _read_operations()
    work = [operations[index % len(operations)] for index in range(users * iterations)]
    with ThreadPoolExecutor(max_workers=users) as executor:
        futures = [executor.submit(_run_operation, name, operation) for name, operation in work]
        return [future.result() for future in as_completed(futures)]


def print_summary(users: int, results: list[OperationResult]) -> None:
    latencies = [result.seconds for result in results]
    successes = [result for result in results if result.ok]
    failures = [result for result in results if not result.ok]
    print(
        "users={users} operations={operations} successes={successes} failures={failures} "
        "avg_ms={avg:.1f} p50_ms={p50:.1f} p95_ms={p95:.1f} max_ms={max_ms:.1f} "
        "queries={queries} errors={errors}".format(
            users=users,
            operations=len(results),
            successes=len(successes),
            failures=len(failures),
            avg=(sum(latencies) / len(latencies) * 1000) if latencies else 0,
            p50=median(latencies) * 1000 if latencies else 0,
            p95=_percentile(latencies, 95) * 1000,
            max_ms=max(latencies) * 1000 if latencies else 0,
            queries=sum(result.query_count for result in successes),
            errors=sorted({result.error_type for result in failures if result.error_type}),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Campaign Operations service-level read load check.")
    parser.add_argument("--users", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()

    if not get_campaign_ops_database_url():
        print("CAMPAIGN_OPS_DATABASE_URL is not configured; live load check skipped.")
        return 0

    for users in args.users:
        try:
            results = run_read_simulation(max(1, users), max(1, args.iterations))
        except CampaignOpsError as exc:
            print(f"users={users} live load check skipped: {type(exc).__name__}")
            continue
        print_summary(users, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
