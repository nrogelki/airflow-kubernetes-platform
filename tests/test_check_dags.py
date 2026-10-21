from pathlib import Path

import check_dags


def _make_repo(tmp_path: Path, dag_src: str, dag_id: str = "my_dag") -> Path:
    (tmp_path / "libs" / "dataplatform" / "utils").mkdir(parents=True)
    (tmp_path / "libs" / "dataplatform" / "utils" / "local_files.py").write_text("")
    dag_dir = tmp_path / "dags" / dag_id
    (dag_dir / "scripts").mkdir(parents=True)
    (dag_dir / "scripts" / "__init__.py").write_text("")
    (dag_dir / "scripts" / "logic.py").write_text("def f():\n    return 1\n")
    (dag_dir / "README.md").write_text("# x")
    (dag_dir / "_dag.py").write_text(dag_src)
    (tmp_path / "files" / dag_id).mkdir(parents=True)
    return tmp_path


GOOD = """
from airflow.sdk import dag, task

@task.external_python(python="/x")
def t():
    from dataplatform.utils.local_files import read_json
    from my_dag.scripts.logic import f

@dag(dag_id="my_dag")
def my_dag():
    t()
"""


def test_repo_example_dags_pass():
    for dag_id in check_dags.discover():
        assert check_dags.check_dag(dag_id).status == "OK", dag_id


def test_good_dag_is_ok(tmp_path):
    repo = _make_repo(tmp_path, GOOD)
    assert check_dags.check_dag("my_dag", repo).status == "OK"


def test_syntax_error_fails(tmp_path):
    repo = _make_repo(tmp_path, "def broken(:\n")
    assert "does not parse" in check_dags.check_dag("my_dag", repo).errors[0]


def test_unresolved_lib_import_fails(tmp_path):
    repo = _make_repo(tmp_path, GOOD.replace("utils.local_files", "utils.nope"))
    res = check_dags.check_dag("my_dag", repo)
    assert any("dataplatform.utils.nope" in e for e in res.errors)


def test_heavy_top_level_import_fails(tmp_path):
    repo = _make_repo(tmp_path, "import pandas as pd\n" + GOOD)
    res = check_dags.check_dag("my_dag", repo)
    assert any("pandas" in e for e in res.errors)


def test_dag_id_must_match_folder(tmp_path):
    repo = _make_repo(tmp_path, GOOD.replace('dag_id="my_dag"', 'dag_id="other"'))
    res = check_dags.check_dag("my_dag", repo)
    assert any("differs from folder" in e for e in res.errors)


def test_missing_readme_warns(tmp_path):
    repo = _make_repo(tmp_path, GOOD)
    (repo / "dags" / "my_dag" / "README.md").unlink()
    assert check_dags.check_dag("my_dag", repo).status == "WARN"
