"""example_resource_override — give ONE task more CPU/RAM than the default.

The pod template (k8s/pod_templates) sets conservative defaults for every
task. When a specific task needs more, override its pod with executor_config
instead of raising the global limits. The exception stays explicit and
visible in the code.

It also shows how to throttle a family of tasks with an Airflow pool
(create it first: Admin -> Pools, or `airflow pools set heavy_tasks 1 "..."`).
"""

import pendulum
from airflow.sdk import dag, task
from kubernetes.client import models as k8s

PYTHON_ENV = "/opt/conda/envs/p313/bin/python"

HEAVY_POD = {
    "pod_override": k8s.V1Pod(
        spec=k8s.V1PodSpec(
            containers=[
                k8s.V1Container(
                    name="base",  # must match worker_container_name
                    resources=k8s.V1ResourceRequirements(
                        requests={"cpu": "1", "memory": "2Gi"},
                        limits={"cpu": "4", "memory": "12Gi"},
                    ),
                )
            ]
        )
    )
}


@task.external_python(python=PYTHON_ENV, expect_airflow=True)
def light_task() -> int:
    return sum(range(1_000))


@task.external_python(
    python=PYTHON_ENV,
    expect_airflow=True,
    executor_config=HEAVY_POD,
    pool="default_pool",  # replace with a dedicated pool, e.g. "heavy_tasks"
)
def heavy_task(n: int) -> str:
    import sys

    if "/opt/airflow/dags" not in sys.path:
        sys.path.insert(0, "/opt/airflow/dags")
    from example_resource_override.scripts.compute import sum_of_squares

    # str, not int: XCom travels as msgpack, which rejects ints > 2**64 - 1
    # (OverflowError). This result has ~26 digits.
    return str(sum_of_squares(n))


@dag(
    dag_id="example_resource_override",
    description="Per-task resources with executor_config + pools",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["example"],
)
def example_resource_override():
    heavy_task(light_task())


example_resource_override()
