"""Minimal data-quality gate for polars DataFrames.

Run it right before loading: a failed expectation raises
``DataQualityError`` and fails the task (and triggers your alert callbacks)
instead of loading bad data.

    from dataplatform.quality.checks import expect, run_checks

    run_checks(df, [
        expect.min_rows(1),
        expect.columns(["region", "units"]),
        expect.no_nulls(["region"]),
        expect.unique(["region", "day"]),
        expect.between("units", 0, 10_000),
    ])
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Check = Callable[[object], "CheckResult"]


class DataQualityError(Exception):
    """Raised when at least one expectation fails."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


class expect:  # noqa: N801 — reads as a DSL: expect.no_nulls(...)
    @staticmethod
    def min_rows(n: int) -> Check:
        return lambda df: CheckResult(f"min_rows({n})", df.height >= n, f"rows={df.height}")

    @staticmethod
    def columns(required: list[str]) -> Check:
        def _check(df):
            missing = [c for c in required if c not in df.columns]
            return CheckResult("columns", not missing, f"missing={missing}" if missing else "")

        return _check

    @staticmethod
    def no_nulls(cols: list[str]) -> Check:
        def _check(df):
            nulls = {c: df[c].null_count() for c in cols if df[c].null_count()}
            return CheckResult(f"no_nulls({cols})", not nulls, f"nulls={nulls}" if nulls else "")

        return _check

    @staticmethod
    def unique(cols: list[str]) -> Check:
        def _check(df):
            dupes = int(df.select(cols).is_duplicated().sum())
            return CheckResult(f"unique({cols})", dupes == 0, f"duplicated_rows={dupes}" if dupes else "")

        return _check

    @staticmethod
    def between(col: str, low: float | None = None, high: float | None = None) -> Check:
        def _check(df):
            series = df[col].drop_nulls()
            bad = 0
            if low is not None:
                bad += int((series < low).sum())
            if high is not None:
                bad += int((series > high).sum())
            return CheckResult(f"between({col}, {low}, {high})", bad == 0, f"out_of_range={bad}" if bad else "")

        return _check


def run_checks(df, checks: list[Check], raise_on_failure: bool = True) -> list[CheckResult]:
    """Evaluate every check (not just until the first failure) and report them all."""
    results = [check(df) for check in checks]
    for r in results:
        print(f"[{'PASS' if r.passed else 'FAIL'}] {r.name} {r.detail}".rstrip())
    failed = [r for r in results if not r.passed]
    if failed and raise_on_failure:
        summary = "; ".join(f"{r.name}: {r.detail}" for r in failed)
        raise DataQualityError(f"{len(failed)} data-quality check(s) failed -> {summary}")
    return results
