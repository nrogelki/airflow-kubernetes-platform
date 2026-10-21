import pytest

pl = pytest.importorskip("polars")

from example_etl.scripts import example_etl_etl as etl  # noqa: E402


def test_generate_is_deterministic():
    a = etl.generate_sales(["n", "s"], 50, seed=1)
    b = etl.generate_sales(["n", "s"], 50, seed=1)
    assert a.equals(b)


def test_end_to_end(tmp_path):
    cfg = {"regions": ["n", "s"], "rows": 100, "seed": 7}
    parquet = etl.extract_to_parquet(str(tmp_path), cfg, run_date="2026-01-01")
    summary = etl.summarize(parquet, str(tmp_path))
    assert summary["output_file"] == "summary_2026-01-01.csv"
    assert summary["regions"] == 2
    assert summary["total_revenue"] > 0
    assert (tmp_path / summary["output_file"]).is_file()
