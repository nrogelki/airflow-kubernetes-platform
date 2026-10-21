"""Date helpers for partitioned / incremental pipelines. Standard library only.

Airflow passes ``ds`` ("YYYY-MM-DD", the logical date) to tasks. These helpers
cover the recurring needs: "N days before ds", backfill ranges, month windows
and Hive-style partition paths.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

ISO = "%Y-%m-%d"


def to_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value[:10], ISO).date()


def ds_add(ds: str, days: int) -> str:
    """``ds_add("2026-03-01", -1) -> "2026-02-28"`` (same as the Airflow macro)."""
    return (to_date(ds) + timedelta(days=days)).strftime(ISO)


def date_range(start: str | date, end: str | date, step_days: int = 1) -> Iterator[str]:
    """Inclusive range of ISO dates, e.g. for manual backfills inside one task."""
    current, last = to_date(start), to_date(end)
    if step_days <= 0:
        raise ValueError("step_days must be positive")
    while current <= last:
        yield current.strftime(ISO)
        current += timedelta(days=step_days)


def month_bounds(ds: str | date) -> tuple[str, str]:
    """First and last day of the month containing ``ds``."""
    d = to_date(ds)
    first = d.replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return first.strftime(ISO), (next_month - timedelta(days=1)).strftime(ISO)


def partition_path(base: str, ds: str | date, pattern: str = "year=%Y/month=%m/day=%d") -> str:
    """Hive-style partition folder: ``base/year=2026/month=03/day=01``."""
    return f"{base.rstrip('/')}/{to_date(ds).strftime(pattern)}"
