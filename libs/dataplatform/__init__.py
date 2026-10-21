"""dataplatform — shared building blocks for every DAG of the platform.

Lives in libs/ and is importable from any DAG because PYTHONPATH includes
/opt/airflow/libs. Only put here code used by TWO OR MORE DAGs; logic that
belongs to a single pipeline stays in dags/<dag_id>/scripts/.
"""

__version__ = "1.0.0"
