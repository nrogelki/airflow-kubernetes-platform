import pytest

pl = pytest.importorskip("polars")

from dataplatform.quality.checks import DataQualityError, expect, run_checks  # noqa: E402
from dataplatform.utils import dataframes as dfu  # noqa: E402


def test_to_snake_case():
    assert dfu.to_snake_case("Tráfico Total (GB)") == "trafico_total_gb"
    assert dfu.to_snake_case("cellId") == "cell_id"


def test_normalize_columns_detects_collisions():
    with pytest.raises(ValueError):
        dfu.normalize_columns(pl.DataFrame({"A b": [1], "a_b": [2]}))


def test_apply_rename_strict():
    df = pl.DataFrame({"x": [1]})
    with pytest.raises(KeyError):
        dfu.apply_rename(df, {"missing": "y"})
    assert dfu.apply_rename(df, {"x": "y"}).columns == ["y"]


def test_cast_schema():
    df = pl.DataFrame({"n": ["1", "2"], "d": ["2026-01-01", "2026-01-02"]})
    out = dfu.cast_schema(df, {"n": "int", "d": "date"})
    assert out.schema["n"] == pl.Int64 and out.schema["d"] == pl.Date


def test_quality_checks():
    df = pl.DataFrame({"k": [1, 1, None], "v": [5, 50, 500]})
    results = run_checks(
        df,
        [expect.min_rows(1), expect.no_nulls(["k"]), expect.unique(["k"]), expect.between("v", 0, 100)],
        raise_on_failure=False,
    )
    assert [r.passed for r in results] == [True, False, False, False]
    with pytest.raises(DataQualityError, match="3 data-quality"):
        run_checks(df, [expect.no_nulls(["k"]), expect.unique(["k"]), expect.between("v", 0, 100)])
