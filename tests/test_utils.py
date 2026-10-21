import pytest

from dataplatform.utils import dates, retry, sql


def test_ds_add_and_month_bounds():
    assert dates.ds_add("2026-03-01", -1) == "2026-02-28"
    assert dates.month_bounds("2024-02-10") == ("2024-02-01", "2024-02-29")


def test_date_range_inclusive():
    assert list(dates.date_range("2026-01-30", "2026-02-02")) == [
        "2026-01-30",
        "2026-01-31",
        "2026-02-01",
        "2026-02-02",
    ]


def test_partition_path():
    assert dates.partition_path("s3://b/sales/", "2026-03-01") == "s3://b/sales/year=2026/month=03/day=01"


def test_retry_succeeds_after_failures():
    calls = {"n": 0}

    @retry.retry(times=2, exceptions=(ValueError,), sleep=lambda s: None)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("again")
        return "ok"

    assert flaky() == "ok" and calls["n"] == 3


def test_retry_gives_up():
    @retry.retry(times=1, sleep=lambda s: None)
    def always():
        raise RuntimeError("no")

    with pytest.raises(RuntimeError):
        always()


def test_load_sql(tmp_path):
    (tmp_path / "d" / "sql").mkdir(parents=True)
    (tmp_path / "d" / "sql" / "q.sql").write_text("DELETE FROM $table WHERE day = '$ds';")
    assert sql.load_sql("d", "q", {"table": "s.t", "ds": "2026-01-01"}, root=tmp_path) == (
        "DELETE FROM s.t WHERE day = '2026-01-01';"
    )
    with pytest.raises(ValueError):
        sql.load_sql("d", "q", {"table": "t; DROP TABLE x", "ds": "1"}, root=tmp_path)


def test_split_statements():
    assert sql.split_statements("-- c\nSELECT 1;\n\nSELECT 2;") == ["SELECT 1", "SELECT 2"]
