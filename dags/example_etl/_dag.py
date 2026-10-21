"""example_etl — reference pipeline for the platform conventions.

Generates synthetic sales data, stages it as Parquet in files/example_etl/,
aggregates it and writes a summary CSV. No external systems needed, so it
doubles as the smoke test of a fresh installation.

What it demonstrates:
- @task.external_python -> heavy work runs in the isolated env, not in Airflow.
- Imports of dataplatform.* and scripts/ INSIDE the task functions.
- Only primitives travel between tasks (paths, dicts); never DataFrames.
- Inputs + staging in files/<dag_id>/ (name identical to the dag_id).
"""

from datetime import timedelta

import pendulum
from airflow.sdk import dag, task

PYTHON_ENV = "/opt/conda/envs/p313/bin/python"
LOCAL_PATH = "/opt/airflow/files/example_etl"

default_args = {
    "owner": "data-team",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    # Uncomment once the smtp_default Connection exists:
    # "on_failure_callback": [task_failure_email_alert(["data-team@example.com"])],
}


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def load_config(local_path: str) -> dict:
    from dataplatform.utils.local_files import read_json

    return read_json(local_path, "config.json")


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def extract(local_path: str, config: dict, ds: str | None = None) -> str:
    import sys

    if "/opt/airflow/dags" not in sys.path:
        sys.path.insert(0, "/opt/airflow/dags")
    from example_etl.scripts.example_etl_etl import extract_to_parquet

    return extract_to_parquet(local_path, config, run_date=ds)


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def transform(parquet_path: str, local_path: str) -> dict:
    import sys

    if "/opt/airflow/dags" not in sys.path:
        sys.path.insert(0, "/opt/airflow/dags")
    from example_etl.scripts.example_etl_etl import summarize

    return summarize(parquet_path, local_path)


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def cleanup(local_path: str, summary: dict) -> list:
    from dataplatform.utils.local_files import clean_dir

    # Keep the input config and the final output; drop intermediate staging.
    return clean_dir(local_path, keep=("config.json", ".gitkeep", summary["output_file"]))


@dag(
    dag_id="example_etl",
    description="Reference ETL: synthetic data -> Parquet staging -> summary CSV",
    default_args=default_args,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["example", "smoke-test"],
)
def example_etl():
    config = load_config(LOCAL_PATH)
    parquet_path = extract(LOCAL_PATH, config)
    summary = transform(parquet_path, LOCAL_PATH)
    cleanup(LOCAL_PATH, summary)


example_etl()
