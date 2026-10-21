"""Business logic of the example_etl DAG.

Runs only inside the isolated environment, so third-party imports (polars)
live at module level here — unlike _dag.py, which the dag-processor parses.
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

import polars as pl


def generate_sales(regions: list[str], rows: int, seed: int = 42) -> pl.DataFrame:
    """Deterministic synthetic sales rows (same seed -> same data)."""
    rng = random.Random(seed)
    return pl.DataFrame(
        {
            "region": [rng.choice(regions) for _ in range(rows)],
            "units": [rng.randint(1, 20) for _ in range(rows)],
            "unit_price": [round(rng.uniform(5, 100), 2) for _ in range(rows)],
        }
    )


def extract_to_parquet(local_path: str, config: dict, run_date: str | None = None) -> str:
    """Generate the day's data and stage it as Parquet. Returns the file path."""
    run_date = run_date or date.today().isoformat()
    df = generate_sales(config["regions"], int(config["rows"]), int(config.get("seed", 42)))
    out = Path(local_path) / f"sales_{run_date}.parquet"
    df.write_parquet(out)
    print(f"Staged {df.height} rows -> {out}")
    return str(out)


def aggregate(df: pl.DataFrame) -> pl.DataFrame:
    """Revenue and units per region, sorted by revenue (desc)."""
    return (
        df.with_columns((pl.col("units") * pl.col("unit_price")).alias("revenue"))
        .group_by("region")
        .agg(pl.col("units").sum(), pl.col("revenue").sum().round(2))
        .sort("revenue", descending=True)
    )


def summarize(parquet_path: str, local_path: str) -> dict:
    """Aggregate the staged file and write a CSV. Returns primitives only."""
    result = aggregate(pl.read_parquet(parquet_path))
    output_file = Path(parquet_path).stem.replace("sales_", "summary_") + ".csv"
    result.write_csv(Path(local_path) / output_file)
    print(result)
    return {
        "output_file": output_file,
        "regions": result.height,
        "total_revenue": float(result["revenue"].sum()),
    }
