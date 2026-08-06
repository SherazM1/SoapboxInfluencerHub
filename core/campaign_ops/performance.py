from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import os
from time import perf_counter
from typing import Iterator


PERF_LOG_ENV_VAR = "CAMPAIGN_OPS_PERF_LOG"
DEFAULT_WARNING_THRESHOLD_SECONDS = 2.0

logger = logging.getLogger(__name__)
_active_query_stats: ContextVar["CampaignOpsQueryStats | None"] = ContextVar(
    "campaign_ops_query_stats",
    default=None,
)


@dataclass(slots=True)
class CampaignOpsQueryStats:
    operation: str
    query_count: int = 0
    total_query_seconds: float = 0.0
    row_count: int = 0
    total_seconds: float = 0.0


def _perf_logging_enabled() -> bool:
    return os.environ.get(PERF_LOG_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


def record_query(duration_seconds: float, row_count: int = 0, query_increment: int = 1) -> None:
    stats = _active_query_stats.get()
    if stats is None:
        return
    stats.query_count += query_increment
    stats.total_query_seconds += duration_seconds
    stats.row_count += max(row_count, 0)


@contextmanager
def campaign_ops_query_counter(operation: str) -> Iterator[CampaignOpsQueryStats]:
    stats = CampaignOpsQueryStats(operation=operation)
    token = _active_query_stats.set(stats)
    started = perf_counter()
    try:
        yield stats
    finally:
        stats.total_seconds = perf_counter() - started
        _active_query_stats.reset(token)
        if _perf_logging_enabled() or stats.total_seconds >= DEFAULT_WARNING_THRESHOLD_SECONDS:
            logger.info(
                "campaign_ops_perf operation=%s duration_ms=%.1f query_count=%s query_ms=%.1f row_count=%s",
                stats.operation,
                stats.total_seconds * 1000,
                stats.query_count,
                stats.total_query_seconds * 1000,
                stats.row_count,
            )
