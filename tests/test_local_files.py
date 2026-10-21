import json

import pytest

from dataplatform.utils import local_files as lf


def test_dag_files_path():
    assert str(lf.dag_files_path("abc", "/opt/airflow/files")) == "/opt/airflow/files/abc"


def test_read_json(tmp_path):
    (tmp_path / "c.json").write_text(json.dumps({"a": 1}))
    assert lf.read_json(tmp_path, "c.json") == {"a": 1}


def test_read_json_missing_has_helpful_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="dag_id"):
        lf.read_json(tmp_path, "nope.json")


def test_clean_dir_keeps_inputs(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "stage.parquet").write_text("x")
    (tmp_path / "sub").mkdir()
    assert lf.clean_dir(tmp_path, keep=("config.json",)) == ["stage.parquet", "sub"]
    assert [p.name for p in tmp_path.iterdir()] == ["config.json"]
