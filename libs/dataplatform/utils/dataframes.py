"""Polars helpers for the typical "raw file -> typed table" step.

Imported only inside the isolated environment (polars is not in the Airflow
image). polars is imported lazily so the module can be listed/inspected safely.
"""

from __future__ import annotations

import re
import unicodedata

_TYPE_NAMES = {
    "str": "Utf8",
    "string": "Utf8",
    "int": "Int64",
    "int32": "Int32",
    "int64": "Int64",
    "float": "Float64",
    "float64": "Float64",
    "bool": "Boolean",
    "date": "Date",
    "datetime": "Datetime",
}


def to_snake_case(name: str) -> str:
    """'Tráfico Total (GB)' -> 'trafico_total_gb'."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", ascii_name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", ascii_name).strip("_").lower()


def normalize_columns(df):
    """Rename every column to snake_case ASCII. Fails on resulting duplicates."""
    new = [to_snake_case(c) for c in df.columns]
    dupes = {c for c in new if new.count(c) > 1}
    if dupes:
        raise ValueError(f"Column names collide after normalisation: {sorted(dupes)}")
    return df.rename(dict(zip(df.columns, new, strict=True)))


def apply_rename(df, mapping: dict[str, str], strict: bool = True):
    """Rename with a mapping (e.g. files/<dag_id>/rename.json).

    ``strict=True`` fails if a source column is missing: an upstream format
    change should break the pipeline loudly, not load NULLs silently.
    """
    missing = [c for c in mapping if c not in df.columns]
    if missing and strict:
        raise KeyError(f"Columns missing in source: {missing}")
    return df.rename({k: v for k, v in mapping.items() if k in df.columns})


def cast_schema(df, schema: dict[str, str], strict: bool = False):
    """Cast columns to types given as strings: {"units": "int", "day": "date"}."""
    import polars as pl

    exprs = []
    for column, type_name in schema.items():
        dtype = getattr(pl, _TYPE_NAMES.get(type_name.lower(), type_name))
        if dtype is pl.Date and df.schema.get(column) == pl.Utf8:
            exprs.append(pl.col(column).str.to_date(strict=strict))
        elif dtype is pl.Datetime and df.schema.get(column) == pl.Utf8:
            exprs.append(pl.col(column).str.to_datetime(strict=strict))
        else:
            exprs.append(pl.col(column).cast(dtype, strict=strict))
    return df.with_columns(exprs)
